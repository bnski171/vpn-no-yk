from datetime import datetime, timedelta
from database.connection import db_manager
import logging

logger = logging.getLogger(__name__)


class DatabaseInitializer:
    """Инициализация структуры базы данных"""

    @staticmethod
    def init_database():
        """Создание всех необходимых таблиц"""
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # Таблица серверов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    api_url TEXT NOT NULL,
                    api_token TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    uuid TEXT NOT NULL UNIQUE,
                    server_id INTEGER,
                    subscription_end TIMESTAMP NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_refuse_payment BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (server_id) REFERENCES servers(id)
                )
            ''')

            # Таблица промокодов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS promocodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    duration_seconds INTEGER NOT NULL,
                    max_activations INTEGER NOT NULL,
                    current_activations INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица активаций промокодов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS promocode_activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    promocode_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (promocode_id) REFERENCES promocodes(id),
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    UNIQUE(promocode_id, user_id)
                )
            ''')

            # Таблица истории активности пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            ''')

            # Таблица оплат
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id INTEGER NOT NULL,
                    payment_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    amount FLOAT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );
            ''')

            # Создание индексов для оптимизации
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_subscription_end ON users(subscription_end)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_server_id ON users(server_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_promocodes_code ON promocodes(code)')

            conn.commit()
            DatabaseInitializer._create_default_data(cursor, conn)

            logger.info("База данных успешно инициализирована")

    @staticmethod
    def _create_default_data(cursor, conn):
        """Создание данных по умолчанию"""
        # Создание тестового промокода на 3 дня
        cursor.execute(
            "SELECT COUNT(*) FROM promocodes WHERE code = ?", ('TRIAL3DAYS',)
        )
        if cursor.fetchone()[0] == 0:
            cursor.execute('''
                INSERT INTO promocodes (code, duration_seconds, max_activations, is_active)
                VALUES (?, ?, ?, ?)
            ''', ('TRIAL3DAYS', 3 * 24 * 60 * 60, 999999, True))
            logger.info("Создан промокод TRIAL3DAYS на 3 дня")

        conn.commit()
