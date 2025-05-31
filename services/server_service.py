import requests
import json
from typing import Dict, List, Optional, Tuple
from database.connection import db_manager
from utils.helpers import generate_user_email, generate_uuid
import logging

logger = logging.getLogger(__name__)


class ServerService:
    """Сервис для управления VPN серверами"""

    @staticmethod
    def get_all_servers() -> List[Dict]:
        """Получение списка всех серверов"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM servers ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_active_servers() -> List[Dict]:
        """Получение списка активных серверов"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM servers WHERE is_active = TRUE ORDER BY name")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_server_by_id(server_id: int) -> Optional[Dict]:
        """Получение сервера по ID"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM servers WHERE id = ?", (server_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def create_server(name: str, domain: str, api_url: str, api_token: str) -> Tuple[bool, str]:
        """Создание нового сервера"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO servers (name, domain, api_url, api_token)
                    VALUES (?, ?, ?, ?)
                ''', (name, domain, api_url, api_token))
                conn.commit()
                logger.info(f"Создан новый сервер: {name}")
                return True, "Сервер успешно создан"
        except Exception as e:
            logger.error(f"Ошибка создания сервера: {e}")
            return False, str(e)

    @staticmethod
    def update_server(server_id: int, name: str, domain: str, api_url: str, api_token: str) -> Tuple[bool, str]:
        """Обновление сервера"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE servers 
                    SET name = ?, domain = ?, api_url = ?, api_token = ?
                    WHERE id = ?
                ''', (name, domain, api_url, api_token, server_id))

                if cursor.rowcount == 0:
                    return False, "Сервер не найден"

                conn.commit()
                logger.info(f"Обновлен сервер ID {server_id}")
                return True, "Сервер успешно обновлен"
        except Exception as e:
            logger.error(f"Ошибка обновления сервера: {e}")
            return False, str(e)

    @staticmethod
    def delete_server(server_id: int) -> Tuple[bool, str]:
        """Удаление сервера"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                # Проверяем наличие пользователей на сервере
                cursor.execute("SELECT COUNT(*) FROM users WHERE server_id = ?", (server_id,))
                user_count = cursor.fetchone()[0]

                if user_count > 0:
                    return False, f"Нельзя удалить сервер с {user_count} пользователями"

                cursor.execute("DELETE FROM servers WHERE id = ?", (server_id,))

                if cursor.rowcount == 0:
                    return False, "Сервер не найден"

                conn.commit()
                logger.info(f"Удален сервер ID {server_id}")
                return True, "Сервер успешно удален"
        except Exception as e:
            logger.error(f"Ошибка удаления сервера: {e}")
            return False, str(e)

    @staticmethod
    def toggle_server_status(server_id: int) -> Tuple[bool, str]:
        """Переключение статуса сервера (активен/неактивен)"""
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT is_active FROM servers WHERE id = ?", (server_id,))
                row = cursor.fetchone()

                if not row:
                    return False, "Сервер не найден"

                new_status = not row['is_active']
                cursor.execute("UPDATE servers SET is_active = ? WHERE id = ?", (new_status, server_id))
                conn.commit()

                status_text = "активирован" if new_status else "деактивирован"
                logger.info(f"Сервер ID {server_id} {status_text}")
                return True, f"Сервер {status_text}"
        except Exception as e:
            logger.error(f"Ошибка изменения статуса сервера: {e}")
            return False, str(e)

    @staticmethod
    def get_least_loaded_server() -> Optional[Dict]:
        """Получение наименее загруженного активного сервера"""
        try:
            servers = ServerService.get_active_servers()
            if not servers:
                return None

            server_loads = []

            with db_manager.get_connection() as conn:
                cursor = conn.cursor()

                for server in servers:
                    cursor.execute("SELECT COUNT(*) FROM users WHERE server_id = ?", (server['id'],))
                    user_count = cursor.fetchone()[0]
                    server_loads.append((server, user_count))

            # Сортируем по загрузке и возвращаем наименее загруженный
            server_loads.sort(key=lambda x: x[1])
            return server_loads[0][0] if server_loads else None

        except Exception as e:
            logger.error(f"Ошибка получения наименее загруженного сервера: {e}")
            return None

    @staticmethod
    def get_server_status(server: Dict) -> Dict:
        """Получение статуса сервера через API"""
        try:
            response = requests.get(
                f"{server['api_url']}/api/server/status",
                headers={"X-API-Token": server['api_token']},
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"HTTP {response.status_code}"}

        except requests.exceptions.ConnectionError:
            return {"error": "Сервер недоступен"}
        except requests.exceptions.Timeout:
            return {"error": "Таймаут соединения"}
        except Exception as e:
            return {"error": f"Ошибка: {str(e)}"}

    @staticmethod
    def add_user_to_vpn_server(server: Dict, user_uuid: str, email: str) -> Optional[Dict]:
        """Добавление пользователя на VPN сервер"""
        try:
            response = requests.post(
                f"{server['api_url']}/api/clients/generate",
                headers={
                    "X-API-Token": server['api_token'],
                    "Content-Type": "application/json"
                },
                json={
                    "email": email,
                    "id": user_uuid,
                    "flow": "xtls-rprx-vision"
                },
                timeout=10
            )

            if response.status_code == 200:
                logger.info(f"Пользователь {email} добавлен на сервер {server['name']}")
                return response.json()
            else:
                logger.error(f"Ошибка добавления пользователя {email}: HTTP {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Исключение при добавлении пользователя {email}: {e}")
            return None

    @staticmethod
    def remove_user_from_vpn_server(server: Dict, user_uuid: str) -> bool:
        """Удаление пользователя с VPN сервера"""
        try:
            response = requests.delete(
                f"{server['api_url']}/api/clients/{user_uuid}",
                headers={"X-API-Token": server['api_token']},
                timeout=10
            )

            success = response.status_code == 200
            if success:
                logger.info(f"Пользователь {user_uuid} удален с сервера {server['name']}")
            else:
                logger.error(f"Ошибка удаления пользователя {user_uuid}: HTTP {response.status_code}")

            return success

        except Exception as e:
            logger.error(f"Исключение при удалении пользователя {user_uuid}: {e}")
            return False

    @staticmethod
    def get_user_from_vpn_server(server: Dict, user_uuid: str) -> Optional[Dict]:
        """Получение информации о пользователе с VPN сервера"""
        try:
            response = requests.get(
                f"{server['api_url']}/api/clients/{user_uuid}",
                headers={"X-API-Token": server['api_token']},
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            else:
                return None

        except Exception as e:
            logger.error(f"Исключение при получении пользователя {user_uuid}: {e}")
            return None