import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from config import Config
import logging

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер подключений к базе данных с поддержкой threading"""

    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
        self._local = threading.local()
        self._setup_adapters()

    def _setup_adapters(self):
        """Настройка адаптеров для работы с datetime"""

        def adapt_datetime(dt):
            return dt.strftime('%Y-%m-%d %H:%M:%S.%f')

        def convert_datetime(s):
            try:
                return datetime.strptime(s.decode('utf-8'), '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                try:
                    return datetime.strptime(s.decode('utf-8'), '%Y-%m-%d %H:%M:%S')
                except:
                    return datetime.now()

        sqlite3.register_adapter(datetime, adapt_datetime)
        sqlite3.register_converter("timestamp", convert_datetime)

    @contextmanager
    def get_connection(self):
        """Получение соединения с автоматическим закрытием"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row

        try:
            yield self._local.connection
        except Exception as e:
            self._local.connection.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            pass  # Соединение остается открытым для повторного использования

    def close_connection(self):
        """Закрытие соединения для текущего потока"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')


# Глобальный экземпляр менеджера БД
db_manager = DatabaseManager()