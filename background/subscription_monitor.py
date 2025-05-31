import time
import threading
from datetime import datetime
from typing import Set
from services.user_service import UserService
from services.server_service import ServerService
from database.connection import db_manager
from config import Config
import logging

logger = logging.getLogger(__name__)


class SubscriptionMonitor:
    """Мониторинг активности подписок пользователей"""

    def __init__(self):
        self.running = False
        self.thread = None
        self._active_users_cache: Set[int] = set()
        self._last_check = datetime.now()

    def start(self):
        """Запуск мониторинга"""
        if self.running:
            logger.warning("Мониторинг уже запущен")
            return

        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logger.info("Мониторинг подписок запущен")

    def stop(self):
        """Остановка мониторинга"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Мониторинг подписок остановлен")

    def _monitor_loop(self):
        """Основной цикл мониторинга"""
        logger.info("Начат цикл мониторинга подписок")

        while self.running:
            try:
                self._check_subscriptions()
                time.sleep(Config.SUBSCRIPTION_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(Config.SUBSCRIPTION_CHECK_INTERVAL * 2)  # Увеличиваем интервал при ошибке

    def _check_subscriptions(self):
        """Проверка состояния подписок и синхронизация с VPN серверами"""
        try:
            current_time = datetime.now()

            # Получаем пользователей с активными подписками
            active_users = UserService.get_users_by_subscription_status(active=True)
            current_active_ids = {user['id'] for user in active_users}

            # Получаем пользователей с истекшими подписками
            expired_users = UserService.get_users_by_subscription_status(active=False)
            current_expired_ids = {user['id'] for user in expired_users}

            # Находим изменения статуса
            newly_active = current_active_ids - self._active_users_cache
            newly_expired = self._active_users_cache & current_expired_ids

            # Обрабатываем новых активных пользователей
            for user in active_users:
                if user['id'] in newly_active:
                    self._handle_user_activation(user)

            # Обрабатываем истекших пользователей
            for user in expired_users:
                if user['id'] in newly_expired:
                    self._handle_user_deactivation(user)

            # Обновляем кэш
            self._active_users_cache = current_active_ids

            # Логируем статистику каждые 60 секунд
            if (current_time - self._last_check).total_seconds() >= 60:
                logger.info(f"Статус подписок: {len(current_active_ids)} активных, "
                            f"{len(current_expired_ids)} истекших пользователей")
                self._last_check = current_time

        except Exception as e:
            logger.error(f"Ошибка проверки подписок: {e}")

    def _handle_user_activation(self, user: dict):
        """Обработка активации пользователя"""
        try:
            if not user.get('server_id'):
                logger.warning(f"Пользователь {user['telegram_id']} не имеет назначенного сервера")
                return

            server = {
                'name': user.get('server_name', 'Unknown'),
                'api_url': user['api_url'],
                'api_token': user['api_token']
            }

            # Проверяем наличие пользователя на сервере
            vpn_user = ServerService.get_user_from_vpn_server(server, user['uuid'])

            if not vpn_user:
                # Добавляем пользователя на сервер
                result = ServerService.add_user_to_vpn_server(server, user['uuid'], user['email'])
                if result:
                    logger.info(f"Активирован пользователь {user['email']} на сервере {server['name']}")
                    self._log_user_activity(user['id'], "VPN_ACTIVATED", f"Added to server {server['name']}")
                else:
                    logger.error(f"Не удалось активировать пользователя {user['email']} на сервере {server['name']}")
            else:
                logger.debug(f"Пользователь {user['email']} уже активен на сервере {server['name']}")

        except Exception as e:
            logger.error(f"Ошибка активации пользователя {user.get('telegram_id', 'unknown')}: {e}")

    def _handle_user_deactivation(self, user: dict):
        """Обработка деактивации пользователя"""
        try:
            if not user.get('server_id'):
                return

            server = {
                'name': user.get('server_name', 'Unknown'),
                'api_url': user['api_url'],
                'api_token': user['api_token']
            }

            # Удаляем пользователя с сервера
            success = ServerService.remove_user_from_vpn_server(server, user['uuid'])

            if success:
                logger.info(f"Деактивирован пользователь {user['email']} на сервере {server['name']}")
                self._log_user_activity(user['id'], "VPN_DEACTIVATED", f"Removed from server {server['name']}")
            else:
                logger.warning(f"Не удалось деактивировать пользователя {user['email']} на сервере {server['name']}")

        except Exception as e:
            logger.error(f"Ошибка деактивации пользователя {user.get('telegram_id', 'unknown')}: {e}")

    def _log_user_activity(self, user_id: int, action: str, details: str):
        """Логирование активности пользователя в БД"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_activity_log (user_id, action, details)
                    VALUES (?, ?, ?)
                ''', (user_id, action, details))
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка логирования активности: {e}")


# Глобальный экземпляр монитора - это то, что было пропущено!
subscription_monitor = SubscriptionMonitor()