from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database.connection import db_manager
from services.server_service import ServerService
from utils.helpers import generate_user_email, generate_uuid
import logging

logger = logging.getLogger(__name__)


class UserService:
    """Сервис для управления пользователями VPN"""

    @staticmethod
    def get_all_users() -> List[Dict]:
        """Получение списка всех пользователей с информацией о серверах"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.*, s.name as server_name, s.domain as server_domain
                FROM users u
                LEFT JOIN servers s ON u.server_id = s.id
                ORDER BY u.created_at DESC
            ''')

            users = []
            for row in cursor.fetchall():
                user = dict(row)
                user['is_subscription_active'] = user['subscription_end'] > datetime.now()
                users.append(user)

            return users

    @staticmethod
    def get_user_by_telegram_id(telegram_id: str) -> Optional[Dict]:
        """Получение пользователя по Telegram ID"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.*, s.name as server_name, s.domain as server_domain,
                       s.api_url, s.api_token
                FROM users u
                LEFT JOIN servers s ON u.server_id = s.id
                WHERE u.telegram_id = ?
            ''', (telegram_id,))

            row = cursor.fetchone()
            if row:
                user = dict(row)
                user['is_subscription_active'] = user['subscription_end'] > datetime.now()
                return user
            return None

    @staticmethod
    def get_user_by_id(user_id: int) -> Optional[Dict]:
        """Получение пользователя по ID"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.*, s.name as server_name, s.domain as server_domain,
                       s.api_url, s.api_token
                FROM users u
                LEFT JOIN servers s ON u.server_id = s.id
                WHERE u.id = ?
            ''', (user_id,))

            row = cursor.fetchone()
            if row:
                user = dict(row)
                user['is_subscription_active'] = user['subscription_end'] > datetime.now()
                return user
            return None

    @staticmethod
    def create_user(telegram_id: str, subscription_seconds: int = 0) -> Tuple[bool, str, Optional[Dict]]:
        """Создание нового пользователя"""
        try:
            # Проверяем существование пользователя
            if UserService.get_user_by_telegram_id(telegram_id):
                return False, "Пользователь уже существует", None

            # Получаем наименее загруженный сервер
            server = ServerService.get_least_loaded_server()
            if not server:
                return False, "Нет доступных серверов", None

            # Генерируем данные пользователя
            email = generate_user_email(telegram_id)
            user_uuid = generate_uuid()
            subscription_end = datetime.now() + timedelta(seconds=subscription_seconds)

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Создаем пользователя в БД
                cursor.execute('''
                    INSERT INTO users (telegram_id, email, uuid, server_id, subscription_end)
                    VALUES (?, ?, ?, ?, ?)
                ''', (telegram_id, email, user_uuid, server['id'], subscription_end))

                user_id = cursor.lastrowid

                # Логируем создание
                cursor.execute('''
                    INSERT INTO user_activity_log (user_id, action, details)
                    VALUES (?, ?, ?)
                ''', (user_id, "USER_CREATED", f"Server: {server['name']}"))

                conn.commit()

                # Если есть подписка, добавляем на VPN сервер
                if subscription_seconds > 0:
                    vpn_result = ServerService.add_user_to_vpn_server(server, user_uuid, email)
                    if not vpn_result:
                        logger.warning(f"Не удалось добавить пользователя {email} на VPN сервер")

                user_data = UserService.get_user_by_id(user_id)
                logger.info(f"Создан пользователь {telegram_id} на сервере {server['name']}")

                return True, "Пользователь успешно создан", user_data

        except Exception as e:
            logger.error(f"Ошибка создания пользователя: {e}")
            return False, str(e), None

    @staticmethod
    def update_subscription(telegram_id: str, additional_seconds: int) -> Tuple[bool, str]:
        """Продление подписки пользователя"""
        try:
            user = UserService.get_user_by_telegram_id(telegram_id)
            if not user:
                return False, "Пользователь не найден"

            # Рассчитываем новую дату окончания подписки
            current_end = user['subscription_end']
            if current_end < datetime.now():
                new_end = datetime.now() + timedelta(seconds=additional_seconds)
            else:
                new_end = current_end + timedelta(seconds=additional_seconds)

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET subscription_end = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_id = ?
                ''', (new_end, telegram_id))

                # Логируем продление
                cursor.execute('''
                    INSERT INTO user_activity_log (user_id, action, details)
                    VALUES (?, ?, ?)
                ''', (user['id'], "SUBSCRIPTION_EXTENDED",
                      f"Added {additional_seconds} seconds, new end: {new_end}"))

                conn.commit()

                logger.info(f"Подписка пользователя {telegram_id} продлена до {new_end}")
                return True, f"Подписка продлена до {new_end.strftime('%Y-%m-%d %H:%M:%S')}"

        except Exception as e:
            logger.error(f"Ошибка продления подписки: {e}")
            return False, str(e)

    @staticmethod
    def delete_user(user_id: int) -> Tuple[bool, str]:
        """Удаление пользователя"""
        try:
            user = UserService.get_user_by_id(user_id)
            if not user:
                return False, "Пользователь не найден"

            # Удаляем с VPN сервера если есть доступ
            if user['server_id'] and user['api_url']:
                server = {
                    'name': user['server_name'],
                    'api_url': user['api_url'],
                    'api_token': user['api_token']
                }
                ServerService.remove_user_from_vpn_server(server, user['uuid'])

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Удаляем активации промокодов
                cursor.execute("DELETE FROM promocode_activations WHERE user_id = ?", (user_id,))

                # Удаляем логи активности
                cursor.execute("DELETE FROM user_activity_log WHERE user_id = ?", (user_id,))

                # Удаляем пользователя
                cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))

                conn.commit()

                logger.info(f"Удален пользователь {user['telegram_id']}")
                return True, "Пользователь успешно удален"

        except Exception as e:
            logger.error(f"Ошибка удаления пользователя: {e}")
            return False, str(e)

    @staticmethod
    def get_user_vpn_config(telegram_id: str) -> Tuple[bool, str, Optional[str]]:
        """Получение VPN конфигурации пользователя"""
        try:
            user = UserService.get_user_by_telegram_id(telegram_id)
            if not user:
                return False, "Пользователь не найден", None

            if not user['is_subscription_active']:
                return False, "Подписка неактивна", None

            if not user['server_id']:
                return False, "Сервер не назначен", None

            server = {
                'name': user['server_name'],
                'api_url': user['api_url'],
                'api_token': user['api_token']
            }

            # Получаем конфигурацию с сервера
            vpn_data = ServerService.get_user_from_vpn_server(server, user['uuid'])

            if not vpn_data:
                # Если пользователя нет на сервере, добавляем его
                vpn_data = ServerService.add_user_to_vpn_server(server, user['uuid'], user['email'])
                if not vpn_data:
                    return False, "Не удалось получить VPN конфигурацию", None

            # Извлекаем ключ конфигурации
            vless_key = (vpn_data.get('link_xtls') or
                         vpn_data.get('link_ws') or
                         vpn_data.get('link', ''))

            if not vless_key:
                return False, "VPN ключ недоступен", None

            return True, "VPN конфигурация получена", vless_key

        except Exception as e:
            logger.error(f"Ошибка получения VPN конфигурации: {e}")
            return False, str(e), None

    @staticmethod
    def get_users_by_subscription_status(active: bool) -> List[Dict]:
        """Получение пользователей по статусу подписки"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            now = datetime.now()
            if active:
                cursor.execute('''
                    SELECT u.*, s.name as server_name, s.api_url, s.api_token
                    FROM users u
                    LEFT JOIN servers s ON u.server_id = s.id
                    WHERE u.subscription_end > ?
                ''', (now,))
            else:
                cursor.execute('''
                    SELECT u.*, s.name as server_name, s.api_url, s.api_token
                    FROM users u
                    LEFT JOIN servers s ON u.server_id = s.id
                    WHERE u.subscription_end <= ?
                ''', (now,))

            return [dict(row) for row in cursor.fetchall()]