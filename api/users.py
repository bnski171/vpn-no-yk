from flask import Blueprint, request, jsonify
from services.user_service import UserService
from services.subscription_service import SubscriptionService
from utils.validators import validate_telegram_id, validate_subscription_duration
import logging

logger = logging.getLogger(__name__)

users_bp = Blueprint('users', __name__, url_prefix='/api/users')


@users_bp.route('/check/<telegram_id>', methods=['GET'])
def check_user_exists(telegram_id):
    """Проверка существования пользователя"""
    try:
        if not validate_telegram_id(telegram_id):
            return jsonify({
                "success": False,
                "error": "Некорректный Telegram ID"
            }), 400

        user = UserService.get_user_by_telegram_id(telegram_id)

        return jsonify({
            "success": True,
            "exists": user is not None,
            "user_id": user['id'] if user else None
        })

    except Exception as e:
        logger.error(f"Ошибка проверки пользователя: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@users_bp.route('/register', methods=['POST'])
def register_user():
    """Регистрация нового пользователя"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Отсутствуют данные запроса"
            }), 400

        telegram_id = data.get('telegram_id')
        subscription_seconds = data.get('subscription_seconds', 0)

        if not validate_telegram_id(telegram_id):
            return jsonify({
                "success": False,
                "error": "Некорректный Telegram ID"
            }), 400

        if not validate_subscription_duration(subscription_seconds):
            return jsonify({
                "success": False,
                "error": "Некорректная продолжительность подписки"
            }), 400

        success, message, user_data = UserService.create_user(telegram_id, subscription_seconds)

        if success:
            return jsonify({
                "success": True,
                "message": message,
                "user": user_data
            })
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400

    except Exception as e:
        logger.error(f"Ошибка регистрации пользователя: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@users_bp.route('/info/<telegram_id>', methods=['GET'])
def get_user_info(telegram_id):
    """Получение информации о пользователе"""
    try:
        if not validate_telegram_id(telegram_id):
            return jsonify({
                "success": False,
                "error": "Некорректный Telegram ID"
            }), 400

        user = UserService.get_user_by_telegram_id(telegram_id)

        if not user:
            return jsonify({
                "success": False,
                "error": "Пользователь не найден"
            }), 404

        # Получаем VPN конфигурацию если подписка активна
        vpn_config = None
        if user['is_subscription_active']:
            success, message, config = UserService.get_user_vpn_config(telegram_id)
            if success:
                vpn_config = config

        return jsonify({
            "success": True,
            "user": {
                "telegram_id": user['telegram_id'],
                "email": user['email'],
                "subscription_end": user['subscription_end'].isoformat(),
                "is_subscription_active": user['is_subscription_active'],
                "server_name": user.get('server_name'),
                "server_domain": user.get('server_domain'),
                "vpn_config": vpn_config,
                "created_at": user['created_at'].isoformat()
            }
        })

    except Exception as e:
        logger.error(f"Ошибка получения информации о пользователе: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@users_bp.route('/subscription/extend', methods=['POST'])
def extend_subscription():
    """Продление подписки пользователя"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Отсутствуют данные запроса"
            }), 400

        telegram_id = data.get('telegram_id')
        additional_seconds = data.get('additional_seconds')

        if not validate_telegram_id(telegram_id):
            return jsonify({
                "success": False,
                "error": "Некорректный Telegram ID"
            }), 400

        if not validate_subscription_duration(additional_seconds):
            return jsonify({
                "success": False,
                "error": "Некорректная продолжительность продления"
            }), 400

        success, message = UserService.update_subscription(telegram_id, additional_seconds)

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
        logger.error(f"Ошибка продления подписки: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@users_bp.route('/vpn-config/<telegram_id>', methods=['GET'])
def get_vpn_config(telegram_id):
    """Получение VPN конфигурации пользователя"""
    try:
        if not validate_telegram_id(telegram_id):
            return jsonify({
                "success": False,
                "error": "Некорректный Telegram ID"
            }), 400

        success, message, config = UserService.get_user_vpn_config(telegram_id)

        if success:
            return jsonify({
                "success": True,
                "vpn_config": config,
                "message": message
            })
        else:
            return jsonify({
                "success": False,
                "error": message
            }), 400

    except Exception as e:
        logger.error(f"Ошибка получения VPN конфигурации: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@users_bp.route('/promocode/activate', methods=['POST'])
def activate_promocode():
    """Активация промокода"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Отсутствуют данные запроса"
            }), 400

        telegram_id = data.get('telegram_id')
        code = data.get('code', '').strip().upper()

        if not validate_telegram_id(telegram_id):
            return jsonify({
                "success": False,
                "error": "Некорректный Telegram ID"
            }), 400

        if not code:
            return jsonify({
                "success": False,
                "error": "Промокод не указан"
            }), 400

        success, message = SubscriptionService.activate_promocode(telegram_id, code)

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
        logger.error(f"Ошибка активации промокода: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500