import os
from datetime import timedelta


class Config:
    """Конфигурация VPN сервиса"""

    # База данных
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'vpn_service.db')

    # Настройки мониторинга подписок
    SUBSCRIPTION_CHECK_INTERVAL = 1  # Проверка каждую секунду
    SUBSCRIPTION_BUFFER_SECONDS = 5  # Буфер для обработки

    # Настройки логирования
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'vpn_service.log'

    # API настройки
    API_HOST = '0.0.0.0'
    API_PORT = 5000
    API_DEBUG = True

    # Секретный ключ для сессий
    SECRET_KEY = os.urandom(24).hex()

    # Настройки генерации пользователей
    EMAIL_DOMAIN = 'vpnservice.local'