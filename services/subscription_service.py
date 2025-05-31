from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database.connection import db_manager
from services.user_service import UserService
import logging

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Сервис для управления подписками и промокодами"""

    @staticmethod
    def get_all_promocodes() -> List[Dict]:
        """Получение всех промокодов"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_active_promocodes() -> List[Dict]:
        """Получение активных промокодов"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM promocodes 
                WHERE is_active = TRUE AND current_activations < max_activations
                ORDER BY created_at DESC
            ''')
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def create_promocode(code: str, duration_seconds: int, max_activations: int) -> Tuple[bool, str]:
        """Создание нового промокода"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем уникальность кода
                cursor.execute("SELECT id FROM promocodes WHERE code = ?", (code,))
                if cursor.fetchone():
                    return False, "Промокод с таким кодом уже существует"

                cursor.execute('''
                    INSERT INTO promocodes (code, duration_seconds, max_activations)
                    VALUES (?, ?, ?)
                ''', (code, duration_seconds, max_activations))

                conn.commit()
                logger.info(f"Создан промокод {code} на {duration_seconds} секунд")
                return True, "Промокод успешно создан"

        except Exception as e:
            logger.error(f"Ошибка создания промокода: {e}")
            return False, str(e)

    @staticmethod
    def activate_promocode(telegram_id: str, code: str) -> Tuple[bool, str]:
        """Активация промокода пользователем"""
        try:
            user = UserService.get_user_by_telegram_id(telegram_id)
            if not user:
                return False, "Пользователь не найден"

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Получаем промокод
                cursor.execute('''
                    SELECT * FROM promocodes 
                    WHERE code = ? AND is_active = TRUE
                ''', (code,))

                promocode = cursor.fetchone()
                if not promocode:
                    return False, "Промокод не найден или неактивен"

                promocode = dict(promocode)

                # Проверяем лимит активаций
                if promocode['current_activations'] >= promocode['max_activations']:
                    return False, "Превышен лимит активаций промокода"

                # Проверяем, не использовал ли пользователь этот промокод
                cursor.execute('''
                    SELECT id FROM promocode_activations 
                    WHERE promocode_id = ? AND user_id = ?
                ''', (promocode['id'], user['id']))

                if cursor.fetchone():
                    return False, "Вы уже использовали этот промокод"

                # Продлеваем подписку
                success, message = UserService.update_subscription(
                    telegram_id, promocode['duration_seconds']
                )

                if not success:
                    return False, f"Ошибка продления подписки: {message}"

                # Регистрируем активацию
                cursor.execute('''
                    INSERT INTO promocode_activations (promocode_id, user_id)
                    VALUES (?, ?)
                ''', (promocode['id'], user['id']))

                # Увеличиваем счетчик активаций
                cursor.execute('''
                    UPDATE promocodes 
                    SET current_activations = current_activations + 1
                    WHERE id = ?
                ''', (promocode['id'],))

                # Логируем активацию
                cursor.execute('''
                    INSERT INTO user_activity_log (user_id, action, details)
                    VALUES (?, ?, ?)
                ''', (user['id'], "PROMOCODE_ACTIVATED",
                      f"Code: {code}, Duration: {promocode['duration_seconds']} seconds"))

                conn.commit()

                duration_hours = promocode['duration_seconds'] / 3600
                logger.info(f"Пользователь {telegram_id} активировал промокод {code}")

                return True, f"Промокод активирован! Подписка продлена на {duration_hours:.1f} часов"

        except Exception as e:
            logger.error(f"Ошибка активации промокода: {e}")
            return False, str(e)

    @staticmethod
    def delete_promocode(promocode_id: int) -> Tuple[bool, str]:
        """Удаление промокода"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем существование
                cursor.execute("SELECT code FROM promocodes WHERE id = ?", (promocode_id,))
                row = cursor.fetchone()
                if not row:
                    return False, "Промокод не найден"

                code = row['code']

                # Удаляем активации
                cursor.execute("DELETE FROM promocode_activations WHERE promocode_id = ?", (promocode_id,))

                # Удаляем промокод
                cursor.execute("DELETE FROM promocodes WHERE id = ?", (promocode_id,))

                conn.commit()
                logger.info(f"Удален промокод {code}")
                return True, "Промокод успешно удален"

        except Exception as e:
            logger.error(f"Ошибка удаления промокода: {e}")
            return False, str(e)

    @staticmethod
    def toggle_promocode_status(promocode_id: int) -> Tuple[bool, str]:
        """Переключение статуса промокода"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT is_active, code FROM promocodes WHERE id = ?", (promocode_id,))
                row = cursor.fetchone()
                if not row:
                    return False, "Промокод не найден"

                new_status = not row['is_active']
                code = row['code']

                cursor.execute("UPDATE promocodes SET is_active = ? WHERE id = ?", (new_status, promocode_id))
                conn.commit()

                status_text = "активирован" if new_status else "деактивирован"
                logger.info(f"Промокод {code} {status_text}")
                return True, f"Промокод {status_text}"

        except Exception as e:
            logger.error(f"Ошибка изменения статуса промокода: {e}")
            return False, str(e)

    @staticmethod
    def get_user_promocode_history(telegram_id: str) -> List[Dict]:
        """Получение истории активации промокодов пользователя"""
        try:
            user = UserService.get_user_by_telegram_id(telegram_id)
            if not user:
                return []

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT p.code, p.duration_seconds, pa.activated_at
                    FROM promocode_activations pa
                    JOIN promocodes p ON pa.promocode_id = p.id
                    WHERE pa.user_id = ?
                    ORDER BY pa.activated_at DESC
                ''', (user['id'],))

                return [dict(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"Ошибка получения истории промокодов: {e}")
            return []