import uuid
import random
import string
from config import Config


def generate_user_email(telegram_id: str) -> str:
    """Генерация email для пользователя на основе Telegram ID"""
    # Берем последние 5 цифр из telegram_id
    last_digits = telegram_id[-5:] if len(telegram_id) >= 5 else telegram_id

    # Генерируем случайные буквы
    random_letters = ''.join(random.choices(string.ascii_lowercase, k=4))

    return f"{last_digits}{random_letters}@{Config.EMAIL_DOMAIN}"


def generate_uuid() -> str:
    """Генерация UUID для пользователя"""
    return str(uuid.uuid4())


def format_duration(seconds: int) -> str:
    """Форматирование продолжительности в читаемый вид"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} мин"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours} ч"
    else:
        days = seconds // 86400
        return f"{days} дн"


def seconds_to_human_readable(seconds: int) -> str:
    """Преобразование секунд в человекочитаемый формат"""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days > 0:
        parts.append(f"{days}д")
    if hours > 0:
        parts.append(f"{hours}ч")
    if minutes > 0:
        parts.append(f"{minutes}м")
    if secs > 0 or not parts:
        parts.append(f"{secs}с")

    return " ".join(parts)