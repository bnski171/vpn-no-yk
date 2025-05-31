from flask import Blueprint, request, jsonify
from services.server_service import ServerService
from utils.validators import validate_server_data
import logging

logger = logging.getLogger(__name__)

servers_bp = Blueprint('servers', __name__, url_prefix='/api/servers')


@servers_bp.route('/', methods=['GET'])
def get_all_servers():
    """Получение списка всех серверов"""
    try:
        servers = ServerService.get_all_servers()

        # Добавляем статистику для каждого сервера
        for server in servers:
            status = ServerService.get_server_status(server)
            server['status'] = status

            # Подсчитываем количество пользователей на сервере
            from database.connection import db_manager
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM users WHERE server_id = ?", (server['id'],))
                server['user_count'] = cursor.fetchone()[0]

        return jsonify({
            "success": True,
            "servers": servers
        })

    except Exception as e:
        logger.error(f"Ошибка получения списка серверов: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@servers_bp.route('/active', methods=['GET'])
def get_active_servers():
    """Получение списка активных серверов"""
    try:
        servers = ServerService.get_active_servers()

        return jsonify({
            "success": True,
            "servers": servers
        })

    except Exception as e:
        logger.error(f"Ошибка получения активных серверов: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@servers_bp.route('/<int:server_id>', methods=['GET'])
def get_server(server_id):
    """Получение информации о сервере"""
    try:
        server = ServerService.get_server_by_id(server_id)

        if not server:
            return jsonify({
                "success": False,
                "error": "Сервер не найден"
            }), 404

        # Получаем статус сервера
        status = ServerService.get_server_status(server)
        server['status'] = status

        # Подсчитываем количество пользователей
        from database.connection import db_manager
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users WHERE server_id = ?", (server_id,))
            server['user_count'] = cursor.fetchone()[0]

        return jsonify({
            "success": True,
            "server": server
        })

    except Exception as e:
        logger.error(f"Ошибка получения сервера: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@servers_bp.route('/', methods=['POST'])
def create_server():
    """Создание нового сервера"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Отсутствуют данные запроса"
            }), 400

        name = data.get('name', '').strip()
        domain = data.get('domain', '').strip()
        api_url = data.get('api_url', '').strip()
        api_token = data.get('api_token', '').strip()

        # Валидация данных
        is_valid, validation_message = validate_server_data(name, domain, api_url, api_token)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": validation_message
            }), 400

        success, message = ServerService.create_server(name, domain, api_url, api_token)

        if success:
            return jsonify({
                "success": True,
                "message": message
            }), 201
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400

    except Exception as e:
        logger.error(f"Ошибка создания сервера: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@servers_bp.route('/<int:server_id>', methods=['PUT'])
def update_server(server_id):
    """Обновление сервера"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Отсутствуют данные запроса"
            }), 400

        name = data.get('name', '').strip()
        domain = data.get('domain', '').strip()
        api_url = data.get('api_url', '').strip()
        api_token = data.get('api_token', '').strip()

        # Валидация данных
        is_valid, validation_message = validate_server_data(name, domain, api_url, api_token)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": validation_message
            }), 400

        success, message = ServerService.update_server(server_id, name, domain, api_url, api_token)

        if success:
            return jsonify({
                "success": True,
                "message": message
            })
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400

    except Exception as e:
        logger.error(f"Ошибка обновления сервера: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@servers_bp.route('/<int:server_id>', methods=['DELETE'])
def delete_server(server_id):
    """Удаление сервера"""
    try:
        success, message = ServerService.delete_server(server_id)

        if success:
            return jsonify({
                "success": True,
                "message": message
            })
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400

    except Exception as e:
        logger.error(f"Ошибка удаления сервера: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@servers_bp.route('/<int:server_id>/toggle', methods=['PATCH'])
def toggle_server_status(server_id):
    """Переключение статуса сервера"""
    try:
        success, message = ServerService.toggle_server_status(server_id)

        if success:
            return jsonify({
                "success": True,
                "message": message
            })
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400

    except Exception as e:
        logger.error(f"Ошибка переключения статуса сервера: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@servers_bp.route('/<int:server_id>/status', methods=['GET'])
def get_server_status(server_id):
    """Получение статуса сервера"""
    try:
        server = ServerService.get_server_by_id(server_id)

        if not server:
            return jsonify({
                "success": False,
                "error": "Сервер не найден"
            }), 404

        status = ServerService.get_server_status(server)

        return jsonify({
            "success": True,
            "server_id": server_id,
            "server_name": server['name'],
            "status": status
        })

    except Exception as e:
        logger.error(f"Ошибка получения статуса сервера: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@servers_bp.route('/least-loaded', methods=['GET'])
def get_least_loaded_server():
    """Получение наименее загруженного сервера"""
    try:
        server = ServerService.get_least_loaded_server()

        if not server:
            return jsonify({
                "success": False,
                "error": "Нет доступных серверов"
            }), 404

        return jsonify({
            "success": True,
            "server": server
        })

    except Exception as e:
        logger.error(f"Ошибка получения наименее загруженного сервера: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500