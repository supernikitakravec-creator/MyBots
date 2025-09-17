#!/usr/bin/env python3
"""
Система алертов для TgGIFT Star Bot
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum

logger = logging.getLogger(__name__)

class AlertLevel(Enum):
    """Уровни критичности алертов"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class AlertType(Enum):
    """Типы алертов"""
    SYSTEM = "system"
    DATABASE = "database"
    MEMORY = "memory"
    CPU = "cpu"
    QUEUE = "queue"
    BALANCE = "balance"
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"
    CONNECTION = "connection"
    GIFT_MONITORING = "gift_monitoring"

class Alert:
    """Класс для представления алерта"""
    
    def __init__(self, 
                 alert_type: AlertType,
                 level: AlertLevel,
                 title: str,
                 message: str,
                 details: Optional[Dict] = None):
        self.alert_type = alert_type
        self.level = level
        self.title = title
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.now()
        self.id = f"{alert_type.value}_{int(self.timestamp.timestamp())}"

class AlertManager:
    """Менеджер алертов"""
    
    def __init__(self, webhook_url: Optional[str] = None, 
                 telegram_chat_id: Optional[str] = None,
                 telegram_bot_token: Optional[str] = None):
        self.webhook_url = webhook_url
        self.telegram_chat_id = telegram_chat_id
        self.telegram_bot_token = telegram_bot_token
        
        # История алертов
        self.alert_history: List[Alert] = []
        self.alert_cooldowns: Dict[str, datetime] = {}
        
        # Настройки
        self.cooldown_minutes = {
            AlertLevel.INFO: 60,
            AlertLevel.WARNING: 30,
            AlertLevel.ERROR: 15,
            AlertLevel.CRITICAL: 5
        }
        
        # Пороги для автоматических алертов
        self.thresholds = {
            'memory_percent': 80,
            'cpu_percent': 80,
            'error_rate_per_minute': 10,
            'response_time_ms': 1000,
            'queue_size': 1000,
            'min_balance': 100,
            'database_size_mb': 500,
            'log_size_mb': 100
        }
        
        # Колбеки для кастомных проверок
        self.custom_checks: Dict[str, Callable] = {}
    
    def set_threshold(self, key: str, value: float):
        """Установить порог для алерта"""
        self.thresholds[key] = value
    
    def add_custom_check(self, name: str, check_func: Callable):
        """Добавить кастомную проверку"""
        self.custom_checks[name] = check_func
    
    async def send_alert(self, alert: Alert):
        """Отправить алерт"""
        try:
            # Проверяем cooldown
            cooldown_key = f"{alert.alert_type.value}_{alert.level.value}"
            if cooldown_key in self.alert_cooldowns:
                cooldown_until = self.alert_cooldowns[cooldown_key]
                if datetime.now() < cooldown_until:
                    logger.debug(f"Алерт {cooldown_key} в cooldown до {cooldown_until}")
                    return
            
            # Добавляем в историю
            self.alert_history.append(alert)
            if len(self.alert_history) > 1000:
                self.alert_history = self.alert_history[-1000:]
            
            # Устанавливаем cooldown
            cooldown_minutes = self.cooldown_minutes.get(alert.level, 30)
            self.alert_cooldowns[cooldown_key] = datetime.now() + timedelta(minutes=cooldown_minutes)
            
            # Отправляем через доступные каналы
            tasks = []
            
            if self.webhook_url:
                tasks.append(self._send_webhook(alert))
            
            if self.telegram_chat_id and self.telegram_bot_token:
                tasks.append(self._send_telegram(alert))
            
            # Логируем
            self._log_alert(alert)
            
            # Отправляем параллельно
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")
    
    async def _send_webhook(self, alert: Alert):
        """Отправить алерт через webhook"""
        try:
            payload = {
                'id': alert.id,
                'type': alert.alert_type.value,
                'level': alert.level.value,
                'title': alert.title,
                'message': alert.message,
                'details': alert.details,
                'timestamp': alert.timestamp.isoformat()
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        logger.error(f"Webhook вернул статус {response.status}")
                        
        except Exception as e:
            logger.error(f"Ошибка отправки webhook: {e}")
    
    async def _send_telegram(self, alert: Alert):
        """Отправить алерт в Telegram"""
        try:
            # Формируем текст сообщения
            emoji = {
                AlertLevel.INFO: "ℹ️",
                AlertLevel.WARNING: "⚠️",
                AlertLevel.ERROR: "❌",
                AlertLevel.CRITICAL: "🚨"
            }.get(alert.level, "📢")
            
            text = f"{emoji} **{alert.title}**\n\n"
            text += f"Тип: {alert.alert_type.value}\n"
            text += f"Уровень: {alert.level.value}\n"
            text += f"Время: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            text += f"{alert.message}\n"
            
            if alert.details:
                text += "\nДетали:\n"
                for key, value in alert.details.items():
                    text += f"• {key}: {value}\n"
            
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': text,
                'parse_mode': 'Markdown'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Telegram API вернул статус {response.status}")
                        
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
    
    def _log_alert(self, alert: Alert):
        """Логировать алерт"""
        log_func = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.ERROR: logger.error,
            AlertLevel.CRITICAL: logger.critical
        }.get(alert.level, logger.warning)
        
        log_func(f"ALERT [{alert.alert_type.value}] {alert.title}: {alert.message}")
    
    async def check_system_health(self, stats: Dict):
        """Проверить здоровье системы и отправить алерты при необходимости"""
        alerts = []
        
        # Проверка памяти
        if 'memory_percent' in stats:
            if stats['memory_percent'] > self.thresholds['memory_percent']:
                alerts.append(Alert(
                    AlertType.MEMORY,
                    AlertLevel.WARNING if stats['memory_percent'] < 90 else AlertLevel.CRITICAL,
                    "Высокое использование памяти",
                    f"Использование памяти: {stats['memory_percent']:.1f}%",
                    {'memory_percent': stats['memory_percent']}
                ))
        
        # Проверка CPU
        if 'cpu_percent' in stats:
            if stats['cpu_percent'] > self.thresholds['cpu_percent']:
                alerts.append(Alert(
                    AlertType.CPU,
                    AlertLevel.WARNING if stats['cpu_percent'] < 90 else AlertLevel.CRITICAL,
                    "Высокая загрузка CPU",
                    f"Загрузка CPU: {stats['cpu_percent']:.1f}%",
                    {'cpu_percent': stats['cpu_percent']}
                ))
        
        # Проверка очереди
        if 'queue_size' in stats:
            if stats['queue_size'] > self.thresholds['queue_size']:
                alerts.append(Alert(
                    AlertType.QUEUE,
                    AlertLevel.WARNING,
                    "Большая очередь покупок",
                    f"Размер очереди: {stats['queue_size']}",
                    {'queue_size': stats['queue_size']}
                ))
        
        # Проверка ошибок
        if 'error_rate' in stats:
            if stats['error_rate'] > self.thresholds['error_rate_per_minute']:
                alerts.append(Alert(
                    AlertType.ERROR_RATE,
                    AlertLevel.ERROR,
                    "Высокий уровень ошибок",
                    f"Ошибок в минуту: {stats['error_rate']}",
                    {'error_rate': stats['error_rate']}
                ))
        
        # Проверка времени отклика
        if 'response_time_ms' in stats:
            if stats['response_time_ms'] > self.thresholds['response_time_ms']:
                alerts.append(Alert(
                    AlertType.RESPONSE_TIME,
                    AlertLevel.WARNING,
                    "Медленное время отклика",
                    f"Время отклика: {stats['response_time_ms']}мс",
                    {'response_time_ms': stats['response_time_ms']}
                ))
        
        # Кастомные проверки
        for name, check_func in self.custom_checks.items():
            try:
                result = await check_func(stats)
                if result:
                    alerts.append(result)
            except Exception as e:
                logger.error(f"Ошибка в кастомной проверке {name}: {e}")
        
        # Отправляем все алерты
        for alert in alerts:
            await self.send_alert(alert)
    
    async def alert_critical_error(self, error_type: str, error_message: str, details: Optional[Dict] = None):
        """Отправить критический алерт об ошибке"""
        alert = Alert(
            AlertType.SYSTEM,
            AlertLevel.CRITICAL,
            f"Критическая ошибка: {error_type}",
            error_message,
            details
        )
        await self.send_alert(alert)
    
    async def alert_connection_lost(self, connection_type: str, details: Optional[Dict] = None):
        """Алерт о потере соединения"""
        alert = Alert(
            AlertType.CONNECTION,
            AlertLevel.ERROR,
            f"Потеря соединения: {connection_type}",
            f"Соединение с {connection_type} потеряно",
            details
        )
        await self.send_alert(alert)
    
    async def alert_low_balance(self, user_id: int, balance: int):
        """Алерт о низком балансе"""
        if balance < self.thresholds['min_balance']:
            alert = Alert(
                AlertType.BALANCE,
                AlertLevel.WARNING,
                "Низкий баланс пользователя",
                f"Пользователь {user_id} имеет низкий баланс: {balance}⭐",
                {'user_id': user_id, 'balance': balance}
            )
            await self.send_alert(alert)
    
    def get_recent_alerts(self, hours: int = 24) -> List[Alert]:
        """Получить недавние алерты"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alert_history
            if alert.timestamp > cutoff_time
        ]
    
    def get_alert_summary(self) -> Dict:
        """Получить сводку по алертам"""
        summary = {
            'total': len(self.alert_history),
            'by_level': {},
            'by_type': {},
            'recent_24h': len(self.get_recent_alerts(24))
        }
        
        for alert in self.alert_history:
            # По уровню
            level = alert.level.value
            summary['by_level'][level] = summary['by_level'].get(level, 0) + 1
            
            # По типу
            alert_type = alert.alert_type.value
            summary['by_type'][alert_type] = summary['by_type'].get(alert_type, 0) + 1
        
        return summary 