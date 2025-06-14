"""
API модули для VPN сервиса
"""

from .users import users_bp
from .servers import servers_bp
from .subscriptions import subscriptions_bp
from .payments import payments_bp

__all__ = ['users_bp', 'servers_bp', 'subscriptions_bp', 'payments_bp']
