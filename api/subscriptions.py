from flask import Blueprint, request, jsonify
from services.subscription_service import SubscriptionService
from utils.validators import validate_promocode_data, validate_telegram_id
from utils.helpers import seconds_to_human_readable
import logging

logger = logging.getLogger(__name__)

subscriptions_bp = Blueprint('subscriptions', __name__, url_prefix='/api/subscriptions')


@subscriptions_bp.route('/promocodes', methods=['GET'])
def get_all_promocodes():
    """Получение списка всех промокодов"""
    try:
        promocodes = SubscriptionService.get_all_promocodes()

        # Добавляем человекочитаемую продолжительность
        for promo in promocodes:
            promo['duration_human'] = seconds_to_human_readable(promo['duration_seconds'])
            promo['remaining_activations'] = promo['max_activations'] - promo['current_activations']

        return jsonify({
            "success": True,
            "promocodes": promocodes
        })

    except Exception as e:
        logger.error(f"Ошибка получения промокодов: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@subscriptions_bp.route('/promocodes/active', methods=['GET'])
def get_active_promocodes():
    """Получение списка активных промокодов"""
    try:
        promocodes = SubscriptionService.get_active_promocodes()

        # Добавляем человекочитаемую продолжительность
        for promo in promocodes:
            promo['duration_human'] = seconds_to_human_readable(promo['duration_seconds'])
            promo['remaining_activations'] = promo['max_activations'] - promo['current_activations']

        return jsonify({
            "success": True,
            "promocodes": promocodes
        })

    except Exception as e:
        logger.error(f"Ошибка получения активных промокодов: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@subscriptions_bp.route('/promocodes', methods=['POST'])
def create_promocode():
    """Создание нового промокода"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Отсутствуют данные запроса"
            }), 400

        code = data.get('code', '').strip().upper()
        duration_seconds = data.get('duration_seconds')
        max_activations = data.get('max_activations')

        # Валидация данных
        is_valid, validation_message = validate_promocode_data(code, duration_seconds, max_activations)
        if not is_valid:
            return jsonify({
                "success": False,
                "error": validation_message
            }), 400

        success, message = SubscriptionService.create_promocode(code, duration_seconds, max_activations)

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
        logger.error(f"Ошибка создания промокода: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@subscriptions_bp.route('/promocodes/<int:promocode_id>', methods=['DELETE'])
def delete_promocode(promocode_id):
    """Удаление промокода"""
    try:
        success, message = SubscriptionService.delete_promocode(promocode_id)

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
        logger.error(f"Ошибка удаления промокода: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@subscriptions_bp.route('/promocodes/<int:promocode_id>/toggle', methods=['PATCH'])
def toggle_promocode_status(promocode_id):
    """Переключение статуса промокода"""
    try:
        success, message = SubscriptionService.toggle_promocode_status(promocode_id)

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
        logger.error(f"Ошибка переключения статуса промокода: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@subscriptions_bp.route('/promocodes/activate', methods=['POST'])
def activate_promocode():
    """Активация промокода пользователем"""
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


@subscriptions_bp.route('/history/<telegram_id>', methods=['GET'])
def get_user_subscription_history(telegram_id):
    """Получение истории активации промокодов пользователя"""
    try:
        if not validate_telegram_id(telegram_id):
            return jsonify({
                "success": False,
                "error": "Некорректный Telegram ID"
            }), 400

        history = SubscriptionService.get_user_promocode_history(telegram_id)

        # Добавляем человекочитаемую продолжительность
        for record in history:
            record['duration_human'] = seconds_to_human_readable(record['duration_seconds'])

        return jsonify({
            "success": True,
            "history": history
        })

    except Exception as e:
        logger.error(f"Ошибка получения истории подписок: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500


@subscriptions_bp.route('/validate-code/<code>', methods=['GET'])
def validate_promocode(code):
    """Проверка валидности промокода без активации"""
    try:
        code = code.strip().upper()

        from database.connection import db_manager
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM promocodes 
                WHERE code = ? AND is_active = TRUE
            ''', (code,))

            promocode = cursor.fetchone()

            if not promocode:
                return jsonify({
                    "success": False,
                    "valid": False,
                    "error": "Промокод не найден или неактивен"
                })

            promocode = dict(promocode)

            # Проверяем лимит активаций
            if promocode['current_activations'] >= promocode['max_activations']:
                return jsonify({
                    "success": False,
                    "valid": False,
                    "error": "Превышен лимит активаций промокода"
                })

            return jsonify({
                "success": True,
                "valid": True,
                "promocode": {
                    "code": promocode['code'],
                    "duration_seconds": promocode['duration_seconds'],
                    "duration_human": seconds_to_human_readable(promocode['duration_seconds']),
                    "remaining_activations": promocode['max_activations'] - promocode['current_activations']
                }
            })

    except Exception as e:
        logger.error(f"Ошибка валидации промокода: {e}")
        return jsonify({
            "success": False,
            "error": "Внутренняя ошибка сервера"
        }), 500