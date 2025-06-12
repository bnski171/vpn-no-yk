from database.connection import db_manager
from datetime import datetime, timedelta

import logging

logger = logging.getLogger(__name__)


class PaymentDB:
    """Работа с бд для оплат"""

    @classmethod
    def get_tariff(cls, tariff_id: int) -> dict | None:
        """Получение Тарифа"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tariffs where id = ?", (tariff_id, ))
            row = cursor.fetchone()
            return dict(row) if row else None


    @staticmethod
    def get_user(user_id: int) -> dict | None:
        """Получение данных пользователя"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users where id = ?", (user_id, ))
            row = cursor.fetchone()

            return dict(row) if row else None

    @staticmethod
    def save_payment(
        user_id: int,
        payment_id: str,
        duration_days: int,
        amount: float,
        status: str = "new"
    ) -> int:
        """Сохраняет платёж"""

        with db_manager.get_connection() as conn:
            cursor = conn.execute(
                '''
                INSERT INTO payments (user_id, payment_id, status, duration_days, amount, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''',
                (user_id, payment_id, status, duration_days, amount)
            )
            return cursor.lastrowid

    @staticmethod
    def update_payment_status(payment_id: str, status: str) -> None:
        """Обновляет статус платежа платёж"""

        with db_manager.get_connection() as conn:
            cursor = conn.execute(
                '''
                UPDATE payments
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE payment_id = ?
                ''',
                (status, payment_id)
            )
            return cursor.rowcount

    @staticmethod
    def resufe_user_recurrent(user_id: int) -> None:
        """Отменяет автоплатёж"""

        with db_manager.get_connection() as conn:
            cursor = conn.execute(
                '''
                UPDATE payments
                SET is_refuse_payment = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                ''',
                (True, user_id)
            )

    @staticmethod
    def prolong_subscription(user_id: int, duration_days: int) -> datetime:
        """
        Продлевает подписку пользователя.
        Если подписка уже истекла — стартует с текущего момента.
        Если подписка ещё активна — прибавляет срок к существующей дате.
        Возвращает новый срок подписки в ISO-формате.
        """
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # 1. Извлекаем пользователя
            cursor.execute("SELECT subscription_end, is_active FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Пользователь с id={user_id} не найден")

            subscription_end_str, is_active = row
            if not is_active:
                raise ValueError(f"У пользователя id={user_id} неактивен аккаунт (is_active=0)")

            # 2. Проверяем текущий срок
            now = datetime.now()
            try:
                subscription_end = datetime.fromisoformat(subscription_end_str)
            except Exception:
                # Если вдруг в БД некорректный формат — начинаем с текущей даты
                subscription_end = now

            # 3. Считаем новую дату окончания подписки
            if subscription_end < now:
                new_end = now + timedelta(days=duration_days)
            else:
                new_end = subscription_end + timedelta(days=duration_days)

            new_end_str = new_end.strftime('%Y-%m-%d %H:%M:%S')

            # 4. Обновляем в БД
            cursor.execute(
                "UPDATE users SET subscription_end = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_end_str, user_id)
            )
            conn.commit()
            return new_end



