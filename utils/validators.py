import re


def validate_telegram_id(telegram_id: str) -> bool:
    """Валидация Telegram ID"""
    if not telegram_id or not isinstance(telegram_id, str):
        return False

    # Telegram ID должен содержать только цифры и быть длиной от 5 до 15 символов
    return re.match(r'^\d{5,15}$', telegram_id) is not None


def validate_subscription_duration(seconds: int) -> bool:
    """Валидация продолжительности подписки в секундах"""
    if not isinstance(seconds, int):
        return False

    # Минимум 0 секунд, максимум 10 лет
    return 0 <= seconds <= 10 * 365 * 24 * 60 * 60


def validate_server_data(name: str, domain: str, api_url: str, api_token: str) -> tuple[bool, str]:
    """Валидация данных сервера"""
    if not all([name, domain, api_url, api_token]):
        return False, "Все поля обязательны для заполнения"

    if len(name) < 3 or len(name) > 50:
        return False, "Имя сервера должно быть от 3 до 50 символов"

    if not re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', domain):
        return False, "Некорректный формат домена"

    if not re.match(r'^https?://[a-zA-Z0-9.-]+(?::\d+)?$', api_url):
        return False, "Некорректный формат URL API"

    if len(api_token) < 10:
        return False, "API токен слишком короткий"

    return True, "Валидация пройдена"


def validate_promocode_data(code: str, duration_seconds: int, max_activations: int) -> tuple[bool, str]:
    """Валидация данных промокода"""
    if not code or not isinstance(code, str):
        return False, "Код промокода обязателен"

    if not re.match(r'^[A-Z0-9_-]{3,20}$', code):
        return False, "Код может содержать только заглавные буквы, цифры, дефисы и подчеркивания (3-20 символов)"

    if not validate_subscription_duration(duration_seconds):
        return False, "Некорректная продолжительность промокода"

    if not isinstance(max_activations, int) or max_activations < 1:
        return False, "Количество активаций должно быть положительным числом"

    return True, "Валидация пройдена"