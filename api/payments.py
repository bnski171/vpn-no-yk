import json

from flask import Blueprint, request, jsonify
import logging

from payments import PaymentYK, PaymentDB
from config import Config

logger = logging.getLogger(__name__)

payments_bp = Blueprint('payments', __name__, url_prefix='/api/payments')


@payments_bp.route('/pay-link', methods=['POST'])
def get_pay_url():
    """Создаёт ссылку на оплату"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "Отсутствуют данные запроса"
            }), 400

        duration = int(data.get('duration', 0))
        amount = int(data.get('amount', 0))
        user_id = int(data.get('user_id', 0))
        return_url = int(data.get('return_url'))

        # получаем данные  пользователя
        user = PaymentDB.get_user(user_id)

        # Создаём платёж с сохранением карты для будущих автосписаний, прописываем следующий платёж
        payment = PaymentYK.get_pay_link(
            user_id=user_id,
            duration_days=duration,
            email=user['email'],
            next_amount=amount,
            return_url=return_url
        )

        return jsonify({
            'confirmation_url': payment.confirmation.confirmation_url,
            'payment_id': payment.id
        })

    except Exception as e:
        logger.warning(e, exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@payments_bp.route('/success', methods=['POST'])
def success_payment():
    """Принимает успешную оплату"""
    try:
        data = request.get_json()
        payment_data: dict = data.get("object")
        if not payment_data:
            return jsonify({"success": False, "error": "Отсутствуют данные запроса"}), 400

        payment_id = payment_data['id']
        status = payment_data['status']
        amount = payment_data['amount']['value']
        metadata: dict = payment_data.get('metadata')
        if not payment_data:
            return jsonify({"success": False, "error": "Отсутствует metadata"}), 400

        is_trial = bool(int(metadata['is_trial']))

        user_id = int(metadata['user_id'])
        email = metadata['email']
        duration_days = int(metadata['duration_days'])
        next_amount = float(metadata['next_amount'])

        # обновляем статус платежа
        PaymentDB.save_payment(
            user_id=user_id,
            payment_id=payment_id,
            duration_days=Config.TRIAL if is_trial else duration_days,
            amount=amount,
            status=status
        )

        #  Обновляем срок подписки
        subscription_end = PaymentDB.prolong_subscription(user_id, duration_days)
        PaymentYK.schedule_check_payment(
            payment_id=payment_id,
            next_date=subscription_end,
            amount=next_amount,
            email=email,
            duration_days=duration_days,
            user_id=user_id
        )
        if is_trial:
            logger.info(f'Пробный период подключён юзер {user_id}')
        else:
            logger.info(f'Успешное спсиание рекурента {payment_id}')

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.warning(e, exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@payments_bp.route('/refuse-recurrent/<int:user_id>', methods=['GET'])
def refuse_recurent(user_id: int):
    """Принимает отказ от оплаты"""
    try:
        PaymentDB.resufe_user_recurrent(user_id)

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.warning(e, exc_info=True)
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500



