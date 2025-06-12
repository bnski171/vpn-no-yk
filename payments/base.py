from yookassa import Payment
from yookassa import Configuration
from yookassa.payment import PaymentResponse
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from datetime import datetime, timedelta

import logging

from config import Config
from .utils import PaymentDB

logger = logging.getLogger(__name__)

Configuration.account_id = Config.YOOKASSA_SHOP_ID
Configuration.secret_key = Config.YOOKASSA_SECRET_KEY

# планировщик с отдельной бд
scheduler = BackgroundScheduler(
    jobstores={
        'default': SQLAlchemyJobStore(url='sqlite:///jobs.db')
    }
)
scheduler.start()


class PaymentYK:
    "Для управления оплатой"
    @staticmethod
    def get_pay_link(
            user_id: int,
            duration_days: int,
            return_url: str = None,
            email: str = Config.DEFAULT_PAY_EMAIL,
            amount: int = 1,
            next_amount: int = None,
    ) -> PaymentResponse:
        description = 'Подключение пробного периода'
        return Payment.create({
            "amount": {
                "value": str(amount),
                "currency": 'RUB'
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url or Config.RETURN_URL
            },
            "capture": True,
            "description": description,
            "save_payment_method": True,
            "metadata": {
                "is_trial": 1,
                "user_id": user_id,
                "duration_days": duration_days,
                "next_amount": next_amount,
                "email": email,
            },
            "receipt": {
                "customer": {
                    "email": email
                },
                "items": [
                    {
                        "description": description,
                        "quantity": "1.00",
                        "amount": {
                            "value": amount,
                            "currency": "RUB"
                        },
                        "vat_code": "1",
                        "payment_mode": "full_payment",
                        "payment_subject": "service"
                    }
                ]
            },
        })

    @classmethod
    def recurrent_payment(
            cls,
            amount: float,
            last_pay_id: str,
            email: str,
            duration_days: int,
            user_id: int
    ):
        user = PaymentDB.get_user(user_id)
        # если пользовател отказался - блокируем рекурент
        if user.get('is_refuse_payment'):
            logger.info(f'Блокирована оплата пользователя отказ от подписки')
            return

        description = 'Оплата подписки'

        payment = Payment.create({
            "amount": {
                "value": amount,
                "currency": "RUB"
            },
            'save_payment_method': True,
            "capture": True,
            "payment_method_id": last_pay_id,
            "description": description,
            "confirmation": {
                "type": "redirect",
                "return_url": Config.RETURN_URL
            },

            "metadata": {
                "is_trial": 0,
                "user_id": user_id,
                "duration_days": duration_days,
                "next_amount": amount,
                "email": email,
            },
            "receipt": {
                "customer": {
                    "email": email
                },
                "items": [
                    {
                        "description": description,
                        "quantity": "1.00",
                        "amount": {
                            "value": amount,
                            "currency": "RUB"
                        },
                        "vat_code": "1",
                        "payment_mode": "full_payment",
                        "pament_subject": "service"
                    }
                ]
            },
        })
        logger.info(f'Создал списание {payment.id}')

    @classmethod
    def schedule_check_payment(
            cls,
            payment_id: str,
            next_date: datetime,
            amount: float,
            email: str,
            duration_days: int,
            user_id: int
    ):
        """
        Ставит план на следующее списание
        """
        next_date = datetime.now() + timedelta(minutes=1)
        logger.info(f'Автосписание для пользователя: {user_id} След запуск: {next_date}')
        scheduler.add_job(
            cls.recurrent_payment,
            trigger='date',
            run_date=next_date,
            args=[amount, payment_id, email, duration_days, user_id],
            id=f"recurrent_payment_{payment_id}"
        )

