"""
Фоновые задачи для VPN сервиса
"""

from .subscription_monitor import subscription_monitor, SubscriptionMonitor

__all__ = ['subscription_monitor', 'SubscriptionMonitor']