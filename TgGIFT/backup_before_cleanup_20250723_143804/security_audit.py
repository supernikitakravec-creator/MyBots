#!/usr/bin/env python3
"""
Security Audit - система аудита безопасности для TgGIFT Bot
"""

import logging
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
import ipaddress
import re
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class SecurityEventType(Enum):
    """Типы событий безопасности"""
    # Аутентификация
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    SESSION_EXPIRED = "session_expired"
    ACCOUNT_LOCKED = "account_locked"
    
    # Авторизация
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    PERMISSION_ESCALATION = "permission_escalation"
    
    # Подозрительная активность
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"
    UNUSUAL_LOCATION = "unusual_location"
    
    # Изменения данных
    DATA_MODIFICATION = "data_modification"
    SENSITIVE_DATA_ACCESS = "sensitive_data_access"
    CONFIGURATION_CHANGE = "configuration_change"
    
    # Системные события
    SYSTEM_ERROR = "system_error"
    ENCRYPTION_FAILURE = "encryption_failure"
    DATABASE_ERROR = "database_error"
    
    # Атаки
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    CSRF_ATTEMPT = "csrf_attempt"
    DOS_ATTEMPT = "dos_attempt"

class SecurityLevel(Enum):
    """Уровни безопасности событий"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityEvent:
    """Событие безопасности"""
    event_id: str
    event_type: SecurityEventType
    level: SecurityLevel
    timestamp: datetime
    user_id: Optional[int] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    risk_score: int = 0
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертация в словарь"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['event_type'] = self.event_type.value
        data['level'] = self.level.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SecurityEvent':
        """Создание из словаря"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        data['event_type'] = SecurityEventType(data['event_type'])
        data['level'] = SecurityLevel(data['level'])
        return cls(**data)

class SecurityAuditLogger:
    """Логгер аудита безопасности"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Настройки
        self.max_events_in_memory = self.config.get('max_events_in_memory', 10000)
        self.retention_days = self.config.get('retention_days', 90)
        self.log_file_path = self.config.get('log_file_path', 'security_audit.log')
        
        # Хранилище событий
        self.events: deque = deque(maxlen=self.max_events_in_memory)
        self.events_by_user: Dict[int, List[SecurityEvent]] = defaultdict(list)
        self.events_by_ip: Dict[str, List[SecurityEvent]] = defaultdict(list)
        
        # Настройка логгера
        self.audit_logger = self._setup_audit_logger()
        
        logger.info("Security Audit Logger инициализирован")
    
    def _setup_audit_logger(self):
        """Настройка специального логгера для аудита"""
        audit_logger = logging.getLogger('security_audit')
        audit_logger.setLevel(logging.INFO)
        
        # Файловый handler
        handler = logging.FileHandler(self.log_file_path, encoding='utf-8')
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        audit_logger.addHandler(handler)
        
        return audit_logger
    
    def log_event(self, event: SecurityEvent):
        """Логирование события безопасности"""
        
        # Добавляем в память
        self.events.append(event)
        
        # Индексируем по пользователю и IP
        if event.user_id:
            self.events_by_user[event.user_id].append(event)
            # Ограничиваем размер истории на пользователя
            if len(self.events_by_user[event.user_id]) > 1000:
                self.events_by_user[event.user_id] = self.events_by_user[event.user_id][-500:]
        
        if event.ip_address:
            self.events_by_ip[event.ip_address].append(event)
            # Ограничиваем размер истории на IP
            if len(self.events_by_ip[event.ip_address]) > 1000:
                self.events_by_ip[event.ip_address] = self.events_by_ip[event.ip_address][-500:]
        
        # Записываем в файл
        log_message = json.dumps(event.to_dict(), ensure_ascii=False)
        
        if event.level == SecurityLevel.CRITICAL:
            self.audit_logger.critical(log_message)
        elif event.level == SecurityLevel.HIGH:
            self.audit_logger.error(log_message)
        elif event.level == SecurityLevel.MEDIUM:
            self.audit_logger.warning(log_message)
        else:
            self.audit_logger.info(log_message)
        
        # Проверяем на подозрительные паттерны
        self._analyze_event_patterns(event)
    
    def _analyze_event_patterns(self, event: SecurityEvent):
        """Анализ паттернов событий"""
        
        # Анализ по пользователю
        if event.user_id:
            user_events = self.events_by_user[event.user_id]
            self._check_user_patterns(event, user_events)
        
        # Анализ по IP
        if event.ip_address:
            ip_events = self.events_by_ip[event.ip_address]
            self._check_ip_patterns(event, ip_events)
    
    def _check_user_patterns(self, event: SecurityEvent, user_events: List[SecurityEvent]):
        """Проверка паттернов пользователя"""
        
        # Проверяем частые неудачные попытки входа
        if event.event_type == SecurityEventType.LOGIN_FAILURE:
            recent_failures = [
                e for e in user_events[-10:]
                if e.event_type == SecurityEventType.LOGIN_FAILURE and
                (event.timestamp - e.timestamp).total_seconds() < 300  # 5 минут
            ]
            
            if len(recent_failures) >= 3:
                self._create_alert_event(
                    SecurityEventType.BRUTE_FORCE_ATTEMPT,
                    SecurityLevel.HIGH,
                    event.user_id,
                    event.ip_address,
                    f"Обнаружены множественные неудачные попытки входа: {len(recent_failures)}"
                )
        
        # Проверяем необычную активность
        if len(user_events) > 50:
            recent_events = [
                e for e in user_events[-50:]
                if (event.timestamp - e.timestamp).total_seconds() < 3600  # 1 час
            ]
            
            if len(recent_events) > 30:  # Более 30 событий в час
                self._create_alert_event(
                    SecurityEventType.SUSPICIOUS_ACTIVITY,
                    SecurityLevel.MEDIUM,
                    event.user_id,
                    event.ip_address,
                    f"Необычно высокая активность: {len(recent_events)} событий в час"
                )
    
    def _check_ip_patterns(self, event: SecurityEvent, ip_events: List[SecurityEvent]):
        """Проверка паттернов IP адреса"""
        
        # Проверяем множественные пользователи с одного IP
        recent_users = set()
        for e in ip_events[-20:]:
            if e.user_id and (event.timestamp - e.timestamp).total_seconds() < 3600:
                recent_users.add(e.user_id)
        
        if len(recent_users) > 5:  # Более 5 пользователей с одного IP за час
            self._create_alert_event(
                SecurityEventType.SUSPICIOUS_ACTIVITY,
                SecurityLevel.MEDIUM,
                None,
                event.ip_address,
                f"Множественные пользователи с одного IP: {len(recent_users)}"
            )
        
        # Проверяем частоту запросов
        recent_events = [
            e for e in ip_events[-100:]
            if (event.timestamp - e.timestamp).total_seconds() < 300  # 5 минут
        ]
        
        if len(recent_events) > 50:  # Более 50 событий за 5 минут
            self._create_alert_event(
                SecurityEventType.DOS_ATTEMPT,
                SecurityLevel.HIGH,
                event.user_id,
                event.ip_address,
                f"Возможная DoS атака: {len(recent_events)} событий за 5 минут"
            )
    
    def _create_alert_event(self, event_type: SecurityEventType, level: SecurityLevel,
                           user_id: Optional[int], ip_address: Optional[str], 
                           description: str):
        """Создание события-алерта"""
        
        alert_event = SecurityEvent(
            event_id=self._generate_event_id(),
            event_type=event_type,
            level=level,
            timestamp=datetime.now(),
            user_id=user_id,
            ip_address=ip_address,
            details={'alert_description': description, 'auto_generated': True},
            risk_score=self._calculate_risk_score(level),
            tags=['alert', 'auto_generated']
        )
        
        # Логируем алерт (без рекурсивного анализа)
        self.events.append(alert_event)
        log_message = json.dumps(alert_event.to_dict(), ensure_ascii=False)
        self.audit_logger.warning(f"ALERT: {log_message}")
    
    def _generate_event_id(self) -> str:
        """Генерация ID события"""
        timestamp = str(int(time.time() * 1000000))  # микросекунды
        hash_input = f"{timestamp}:{time.time()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def _calculate_risk_score(self, level: SecurityLevel) -> int:
        """Расчет риск-скора"""
        risk_scores = {
            SecurityLevel.INFO: 1,
            SecurityLevel.LOW: 25,
            SecurityLevel.MEDIUM: 50,
            SecurityLevel.HIGH: 75,
            SecurityLevel.CRITICAL: 100
        }
        return risk_scores.get(level, 0)
    
    def get_events(self, filters: Dict[str, Any] = None, 
                   limit: int = 100) -> List[SecurityEvent]:
        """Получение событий с фильтрацией"""
        
        events = list(self.events)
        
        if filters:
            # Фильтр по типу события
            if 'event_type' in filters:
                event_type = SecurityEventType(filters['event_type'])
                events = [e for e in events if e.event_type == event_type]
            
            # Фильтр по уровню
            if 'level' in filters:
                level = SecurityLevel(filters['level'])
                events = [e for e in events if e.level == level]
            
            # Фильтр по пользователю
            if 'user_id' in filters:
                user_id = filters['user_id']
                events = [e for e in events if e.user_id == user_id]
            
            # Фильтр по IP
            if 'ip_address' in filters:
                ip_address = filters['ip_address']
                events = [e for e in events if e.ip_address == ip_address]
            
            # Фильтр по времени
            if 'start_time' in filters:
                start_time = datetime.fromisoformat(filters['start_time'])
                events = [e for e in events if e.timestamp >= start_time]
            
            if 'end_time' in filters:
                end_time = datetime.fromisoformat(filters['end_time'])
                events = [e for e in events if e.timestamp <= end_time]
        
        # Сортируем по времени (новые сначала)
        events.sort(key=lambda e: e.timestamp, reverse=True)
        
        return events[:limit]
    
    def get_security_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Получение сводки безопасности"""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_events = [e for e in self.events if e.timestamp >= cutoff_time]
        
        # Статистика по типам событий
        event_types = {}
        for event in recent_events:
            event_type = event.event_type.value
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        # Статистика по уровням
        levels = {}
        for event in recent_events:
            level = event.level.value
            levels[level] = levels.get(level, 0) + 1
        
        # Топ IP адресов
        ip_stats = {}
        for event in recent_events:
            if event.ip_address:
                ip_stats[event.ip_address] = ip_stats.get(event.ip_address, 0) + 1
        
        top_ips = sorted(ip_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Топ пользователей
        user_stats = {}
        for event in recent_events:
            if event.user_id:
                user_stats[event.user_id] = user_stats.get(event.user_id, 0) + 1
        
        top_users = sorted(user_stats.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Критические события
        critical_events = [
            e for e in recent_events 
            if e.level in [SecurityLevel.HIGH, SecurityLevel.CRITICAL]
        ]
        
        return {
            'period_hours': hours,
            'total_events': len(recent_events),
            'events_by_type': event_types,
            'events_by_level': levels,
            'top_ips': top_ips,
            'top_users': top_users,
            'critical_events_count': len(critical_events),
            'recent_critical_events': [e.to_dict() for e in critical_events[-5:]]
        }

class SecurityValidator:
    """Валидатор безопасности входных данных"""
    
    def __init__(self):
        # Паттерны для обнаружения атак
        self.sql_injection_patterns = [
            r"(?i)(union\s+select|drop\s+table|delete\s+from)",
            r"(?i)(\'\s*or\s+\d+\s*=\s*\d+|admin\'\s*--)",
            r"(?i)(exec\s*\(|execute\s*\(|sp_executesql)"
        ]
        
        self.xss_patterns = [
            r"(?i)(<script|javascript:|onload=|onerror=)",
            r"(?i)(alert\s*\(|confirm\s*\(|prompt\s*\()",
            r"(?i)(<iframe|<object|<embed)"
        ]
        
        self.path_traversal_patterns = [
            r"(\.\.\/|\.\.\\)",
            r"(%2e%2e%2f|%2e%2e%5c)",
            r"(\/etc\/passwd|\/etc\/shadow)"
        ]
    
    def validate_input(self, input_data: str, field_name: str = "input") -> Dict[str, Any]:
        """Валидация входных данных"""
        
        threats = []
        risk_score = 0
        
        # Проверка на SQL injection
        for pattern in self.sql_injection_patterns:
            if re.search(pattern, input_data):
                threats.append({
                    'type': 'sql_injection',
                    'pattern': pattern,
                    'field': field_name
                })
                risk_score += 30
        
        # Проверка на XSS
        for pattern in self.xss_patterns:
            if re.search(pattern, input_data):
                threats.append({
                    'type': 'xss',
                    'pattern': pattern,
                    'field': field_name
                })
                risk_score += 25
        
        # Проверка на Path Traversal
        for pattern in self.path_traversal_patterns:
            if re.search(pattern, input_data):
                threats.append({
                    'type': 'path_traversal',
                    'pattern': pattern,
                    'field': field_name
                })
                risk_score += 20
        
        return {
            'is_safe': len(threats) == 0,
            'threats': threats,
            'risk_score': min(risk_score, 100)
        }
    
    def validate_ip_address(self, ip_address: str) -> Dict[str, Any]:
        """Валидация IP адреса"""
        
        try:
            ip = ipaddress.ip_address(ip_address)
            
            is_private = ip.is_private
            is_loopback = ip.is_loopback
            is_multicast = ip.is_multicast
            
            # Проверка на подозрительные сети
            suspicious_ranges = [
                # Tor exit nodes (примерные диапазоны)
                "185.220.100.0/24",
                "199.87.154.0/24",
            ]
            
            is_suspicious = False
            for range_str in suspicious_ranges:
                try:
                    if ip in ipaddress.ip_network(range_str):
                        is_suspicious = True
                        break
                except:
                    pass
            
            return {
                'is_valid': True,
                'is_private': is_private,
                'is_loopback': is_loopback,
                'is_multicast': is_multicast,
                'is_suspicious': is_suspicious,
                'ip_type': 'IPv4' if isinstance(ip, ipaddress.IPv4Address) else 'IPv6'
            }
            
        except ValueError:
            return {
                'is_valid': False,
                'error': 'Invalid IP address format'
            }

# Интеграция с системой аутентификации

def log_auth_event(audit_logger: SecurityAuditLogger, event_type: SecurityEventType,
                  user_id: int = None, session_id: str = None, 
                  ip_address: str = None, details: Dict[str, Any] = None):
    """Логирование события аутентификации"""
    
    # Определяем уровень безопасности
    level_mapping = {
        SecurityEventType.LOGIN_SUCCESS: SecurityLevel.INFO,
        SecurityEventType.LOGIN_FAILURE: SecurityLevel.LOW,
        SecurityEventType.ACCOUNT_LOCKED: SecurityLevel.HIGH,
        SecurityEventType.ACCESS_DENIED: SecurityLevel.MEDIUM,
        SecurityEventType.PERMISSION_ESCALATION: SecurityLevel.HIGH,
    }
    
    level = level_mapping.get(event_type, SecurityLevel.MEDIUM)
    
    event = SecurityEvent(
        event_id=audit_logger._generate_event_id(),
        event_type=event_type,
        level=level,
        timestamp=datetime.now(),
        user_id=user_id,
        session_id=session_id,
        ip_address=ip_address,
        details=details or {},
        risk_score=audit_logger._calculate_risk_score(level)
    )
    
    audit_logger.log_event(event)

# Middleware для валидации входных данных

class SecurityValidationMiddleware:
    """Middleware для валидации безопасности"""
    
    def __init__(self, audit_logger: SecurityAuditLogger):
        self.audit_logger = audit_logger
        self.validator = SecurityValidator()
    
    async def validate_message(self, update, context):
        """Валидация сообщения пользователя"""
        
        if not update.message or not update.message.text:
            return
        
        user_id = update.message.from_user.id
        message_text = update.message.text
        
        # Валидируем входные данные
        validation_result = self.validator.validate_input(message_text, "message")
        
        if not validation_result['is_safe']:
            # Логируем подозрительную активность
            for threat in validation_result['threats']:
                event_type = {
                    'sql_injection': SecurityEventType.SQL_INJECTION_ATTEMPT,
                    'xss': SecurityEventType.XSS_ATTEMPT,
                    'path_traversal': SecurityEventType.SUSPICIOUS_ACTIVITY
                }.get(threat['type'], SecurityEventType.SUSPICIOUS_ACTIVITY)
                
                event = SecurityEvent(
                    event_id=self.audit_logger._generate_event_id(),
                    event_type=event_type,
                    level=SecurityLevel.HIGH,
                    timestamp=datetime.now(),
                    user_id=user_id,
                    details={
                        'threat_type': threat['type'],
                        'pattern': threat['pattern'],
                        'input_data': message_text[:100] + "..." if len(message_text) > 100 else message_text
                    },
                    risk_score=validation_result['risk_score'],
                    tags=['input_validation', 'threat_detected']
                )
                
                self.audit_logger.log_event(event)
            
            # Блокируем обработку сообщения
            await update.message.reply_text("❌ Обнаружены подозрительные данные в сообщении")
            return False
        
        return True

# Глобальный экземпляр
_global_security_audit_logger = None

def get_security_audit_logger() -> Optional[SecurityAuditLogger]:
    """Получение глобального логгера аудита"""
    return _global_security_audit_logger

def set_security_audit_logger(logger: SecurityAuditLogger):
    """Установка глобального логгера аудита"""
    global _global_security_audit_logger
    _global_security_audit_logger = logger 