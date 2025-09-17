#!/usr/bin/env python3
"""
Alert System - система алертов и уведомлений для TgGIFT Bot
"""

import logging
import asyncio
import smtplib
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from enum import Enum
import json

from health_monitor import HealthStatus, HealthCheck

logger = logging.getLogger(__name__)

class AlertLevel(Enum):
    """Уровни алертов"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

@dataclass
class Alert:
    """Структура алерта"""
    component: str
    level: AlertLevel
    message: str
    timestamp: datetime
    details: Dict[str, Any] = None
    resolved: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'component': self.component,
            'level': self.level.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'details': self.details or {},
            'resolved': self.resolved
        }

class AlertSystem:
    """Система алертов и уведомлений"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.active_alerts = {}  # Активные алерты
        self.alert_history = []  # История алертов
        self.notification_handlers = {}  # Обработчики уведомлений
        self.cooldown_periods = {}  # Периоды cooldown для алертов
        
        # Настройки по умолчанию
        self.default_cooldown = 300  # 5 минут
        self.max_history = 1000
        
        # Регистрируем стандартные обработчики
        self._register_default_handlers()
        
        logger.info("Alert System инициализирован")
    
    def _register_default_handlers(self):
        """Регистрация стандартных обработчиков уведомлений"""
        if self.config.get('telegram', {}).get('enabled'):
            self.register_handler('telegram', self._send_telegram_alert)
        
        if self.config.get('email', {}).get('enabled'):
            self.register_handler('email', self._send_email_alert)
        
        if self.config.get('webhook', {}).get('enabled'):
            self.register_handler('webhook', self._send_webhook_alert)
    
    def register_handler(self, name: str, handler: Callable):
        """Регистрация обработчика уведомлений"""
        self.notification_handlers[name] = handler
        logger.info(f"Зарегистрирован обработчик уведомлений: {name}")
    
    async def trigger_alert(self, component: str, level: AlertLevel, message: str, 
                          details: Dict[str, Any] = None) -> bool:
        """Создание алерта"""
        alert_key = f"{component}:{level.value}:{message}"
        
        # Проверяем cooldown
        if self._is_in_cooldown(alert_key):
            logger.debug(f"Алерт {alert_key} в cooldown, пропускаем")
            return False
        
        alert = Alert(
            component=component,
            level=level,
            message=message,
            timestamp=datetime.now(),
            details=details
        )
        
        # Сохраняем активный алерт
        self.active_alerts[alert_key] = alert
        
        # Добавляем в историю
        self.alert_history.append(alert)
        if len(self.alert_history) > self.max_history:
            self.alert_history = self.alert_history[-self.max_history:]
        
        # Устанавливаем cooldown
        self.cooldown_periods[alert_key] = datetime.now()
        
        # Отправляем уведомления
        await self._send_notifications(alert)
        
        logger.info(f"Создан алерт: {component} - {level.value} - {message}")
        return True
    
    async def resolve_alert(self, component: str, level: AlertLevel, message: str) -> bool:
        """Разрешение алерта"""
        alert_key = f"{component}:{level.value}:{message}"
        
        if alert_key in self.active_alerts:
            alert = self.active_alerts[alert_key]
            alert.resolved = True
            del self.active_alerts[alert_key]
            
            # Отправляем уведомление о разрешении
            resolve_alert = Alert(
                component=component,
                level=AlertLevel.INFO,
                message=f"RESOLVED: {message}",
                timestamp=datetime.now(),
                details={'original_alert': alert.to_dict()}
            )
            
            await self._send_notifications(resolve_alert)
            
            logger.info(f"Разрешен алерт: {component} - {level.value} - {message}")
            return True
        
        return False
    
    def _is_in_cooldown(self, alert_key: str) -> bool:
        """Проверка cooldown для алерта"""
        if alert_key not in self.cooldown_periods:
            return False
        
        last_alert = self.cooldown_periods[alert_key]
        cooldown = timedelta(seconds=self.default_cooldown)
        
        return datetime.now() - last_alert < cooldown
    
    async def _send_notifications(self, alert: Alert):
        """Отправка уведомлений через все зарегистрированные обработчики"""
        tasks = []
        
        for name, handler in self.notification_handlers.items():
            try:
                # Проверяем фильтры для обработчика
                if self._should_send_to_handler(name, alert):
                    tasks.append(self._safe_send_notification(name, handler, alert))
            except Exception as e:
                logger.error(f"Ошибка подготовки уведомления {name}: {e}")
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_send_notification(self, name: str, handler: Callable, alert: Alert):
        """Безопасная отправка уведомления"""
        try:
            await handler(alert)
            logger.debug(f"Уведомление отправлено через {name}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления через {name}: {e}")
    
    def _should_send_to_handler(self, handler_name: str, alert: Alert) -> bool:
        """Проверка нужно ли отправлять уведомление через конкретный обработчик"""
        handler_config = self.config.get(handler_name, {})
        
        # Проверяем минимальный уровень
        min_level = handler_config.get('min_level', 'info')
        level_order = {'info': 0, 'warning': 1, 'critical': 2}
        
        if level_order.get(alert.level.value, 0) < level_order.get(min_level, 0):
            return False
        
        # Проверяем фильтры по компонентам
        allowed_components = handler_config.get('components')
        if allowed_components and alert.component not in allowed_components:
            return False
        
        return True
    
    # Обработчики уведомлений
    
    async def _send_telegram_alert(self, alert: Alert):
        """Отправка алерта в Telegram"""
        config = self.config.get('telegram', {})
        bot_token = config.get('bot_token')
        chat_id = config.get('chat_id')
        
        if not bot_token or not chat_id:
            logger.error("Не настроен Telegram для алертов")
            return
        
        # Формируем сообщение
        emoji = {'info': 'ℹ️', 'warning': '⚠️', 'critical': '🚨'}
        message = f"{emoji.get(alert.level.value, '📢')} **ALERT**\n\n"
        message += f"**Component:** {alert.component}\n"
        message += f"**Level:** {alert.level.value.upper()}\n"
        message += f"**Message:** {alert.message}\n"
        message += f"**Time:** {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if alert.details:
            message += f"\n**Details:**\n"
            for key, value in alert.details.items():
                message += f"• {key}: {value}\n"
        
        # Отправляем через Telegram API
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        async with requests.Session() as session:
            response = session.post(url, data=data)
            if response.status_code != 200:
                logger.error(f"Ошибка отправки Telegram алерта: {response.text}")
    
    async def _send_email_alert(self, alert: Alert):
        """Отправка алерта по email"""
        config = self.config.get('email', {})
        
        smtp_server = config.get('smtp_server')
        smtp_port = config.get('smtp_port', 587)
        username = config.get('username')
        password = config.get('password')
        to_emails = config.get('to_emails', [])
        
        if not all([smtp_server, username, password, to_emails]):
            logger.error("Не настроен email для алертов")
            return
        
        # Формируем email
        subject = f"[{alert.level.value.upper()}] {alert.component}: {alert.message}"
        
        body = f"""
        Alert Details:
        
        Component: {alert.component}
        Level: {alert.level.value.upper()}
        Message: {alert.message}
        Timestamp: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}
        
        """
        
        if alert.details:
            body += "Additional Details:\n"
            for key, value in alert.details.items():
                body += f"  {key}: {value}\n"
        
        msg = MIMEMultipart()
        msg['From'] = username
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        # Отправляем
        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(username, password)
            
            for email in to_emails:
                msg['To'] = email
                server.send_message(msg)
                del msg['To']
            
            server.quit()
        except Exception as e:
            logger.error(f"Ошибка отправки email алерта: {e}")
    
    async def _send_webhook_alert(self, alert: Alert):
        """Отправка алерта через webhook"""
        config = self.config.get('webhook', {})
        url = config.get('url')
        
        if not url:
            logger.error("Не настроен webhook для алертов")
            return
        
        # Формируем payload
        payload = {
            'alert': alert.to_dict(),
            'timestamp': datetime.now().isoformat(),
            'source': 'tggift-bot'
        }
        
        try:
            async with requests.Session() as session:
                response = session.post(
                    url,
                    json=payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10
                )
                
                if response.status_code not in [200, 201, 202]:
                    logger.error(f"Ошибка webhook алерта: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Ошибка отправки webhook алерта: {e}")
    
    # Методы для работы с алертами
    
    def get_active_alerts(self) -> List[Alert]:
        """Получение активных алертов"""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """Получение истории алертов за указанный период"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [alert for alert in self.alert_history if alert.timestamp > cutoff_time]
    
    def get_alert_stats(self) -> Dict[str, Any]:
        """Получение статистики алертов"""
        active_count = len(self.active_alerts)
        
        # Группируем по уровням
        level_stats = {'info': 0, 'warning': 0, 'critical': 0}
        for alert in self.active_alerts.values():
            level_stats[alert.level.value] += 1
        
        # История за последние 24 часа
        recent_history = self.get_alert_history(24)
        
        return {
            'active_alerts': active_count,
            'active_by_level': level_stats,
            'total_history': len(self.alert_history),
            'recent_24h': len(recent_history),
            'handlers_configured': len(self.notification_handlers)
        }
    
    async def process_health_check_results(self, health_results: Dict[str, HealthCheck]):
        """Обработка результатов health checks для создания алертов"""
        for component, result in health_results.items():
            if result.status == HealthStatus.CRITICAL:
                await self.trigger_alert(
                    component=component,
                    level=AlertLevel.CRITICAL,
                    message=result.message,
                    details={
                        'response_time': result.response_time,
                        'details': result.details
                    }
                )
            elif result.status == HealthStatus.WARNING:
                await self.trigger_alert(
                    component=component,
                    level=AlertLevel.WARNING,
                    message=result.message,
                    details={
                        'response_time': result.response_time,
                        'details': result.details
                    }
                )
            elif result.status == HealthStatus.HEALTHY:
                # Пытаемся разрешить существующие алерты
                await self.resolve_alert(component, AlertLevel.CRITICAL, result.message)
                await self.resolve_alert(component, AlertLevel.WARNING, result.message)
    
    def clear_old_alerts(self, hours: int = 168):  # 7 дней
        """Очистка старых алертов из истории"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        old_count = len(self.alert_history)
        self.alert_history = [alert for alert in self.alert_history if alert.timestamp > cutoff_time]
        
        cleared_count = old_count - len(self.alert_history)
        if cleared_count > 0:
            logger.info(f"Очищено {cleared_count} старых алертов")

# Функция для создания системы алертов с конфигурацией
def create_alert_system(config: Dict[str, Any] = None) -> AlertSystem:
    """Создание системы алертов с конфигурацией"""
    return AlertSystem(config or {}) 