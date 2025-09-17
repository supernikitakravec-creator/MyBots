#!/usr/bin/env python3
"""
Auth Manager - система аутентификации и авторизации для TgGIFT Bot
"""

import logging
import time
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib
from functools import wraps

logger = logging.getLogger(__name__)

class UserRole(Enum):
    """Роли пользователей"""
    GUEST = "guest"
    USER = "user"
    VIP = "vip"
    MODERATOR = "moderator"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

class Permission(Enum):
    """Разрешения системы"""
    # Основные действия
    READ_PROFILE = "read_profile"
    WRITE_PROFILE = "write_profile"
    DELETE_PROFILE = "delete_profile"
    
    # Подписки
    MANAGE_SUBSCRIPTION = "manage_subscription"
    VIEW_SUBSCRIPTION = "view_subscription"
    
    # Платежи
    MAKE_PAYMENT = "make_payment"
    VIEW_PAYMENTS = "view_payments"
    REFUND_PAYMENT = "refund_payment"
    
    # Подарки
    SEND_GIFT = "send_gift"
    RECEIVE_GIFT = "receive_gift"
    VIEW_GIFTS = "view_gifts"
    
    # Администрирование
    MANAGE_USERS = "manage_users"
    VIEW_ANALYTICS = "view_analytics"
    MANAGE_SYSTEM = "manage_system"
    VIEW_LOGS = "view_logs"
    
    # Модерация
    MODERATE_CONTENT = "moderate_content"
    BAN_USERS = "ban_users"
    
    # API
    API_ACCESS = "api_access"
    API_ADMIN = "api_admin"

@dataclass
class UserSession:
    """Сессия пользователя"""
    session_id: str
    user_id: int
    role: UserRole
    permissions: Set[Permission]
    created_at: datetime
    last_activity: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Проверка истечения сессии"""
        return datetime.now() > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Проверка валидности сессии"""
        return self.is_active and not self.is_expired

@dataclass
class AuthAttempt:
    """Попытка аутентификации"""
    user_id: int
    timestamp: datetime
    success: bool
    ip_address: Optional[str] = None
    error_reason: Optional[str] = None

class AuthManager:
    """Менеджер аутентификации и авторизации"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Настройки сессий
        self.session_timeout_hours = self.config.get('session_timeout_hours', 24)
        self.max_sessions_per_user = self.config.get('max_sessions_per_user', 5)
        
        # Настройки безопасности
        self.max_login_attempts = self.config.get('max_login_attempts', 5)
        self.lockout_duration_minutes = self.config.get('lockout_duration_minutes', 15)
        self.require_2fa_for_admin = self.config.get('require_2fa_for_admin', True)
        
        # Хранилище сессий и попыток
        self.active_sessions: Dict[str, UserSession] = {}
        self.auth_attempts: Dict[int, List[AuthAttempt]] = {}
        
        # Настройка ролей и разрешений
        self.role_permissions = self._setup_role_permissions()
        
        logger.info("Auth Manager инициализирован")
    
    def _setup_role_permissions(self) -> Dict[UserRole, Set[Permission]]:
        """Настройка разрешений для ролей"""
        return {
            UserRole.GUEST: {
                Permission.READ_PROFILE,
            },
            
            UserRole.USER: {
                Permission.READ_PROFILE,
                Permission.WRITE_PROFILE,
                Permission.VIEW_SUBSCRIPTION,
                Permission.MAKE_PAYMENT,
                Permission.VIEW_PAYMENTS,
                Permission.SEND_GIFT,
                Permission.RECEIVE_GIFT,
                Permission.VIEW_GIFTS,
            },
            
            UserRole.VIP: {
                # Все права обычного пользователя
                Permission.READ_PROFILE,
                Permission.WRITE_PROFILE,
                Permission.VIEW_SUBSCRIPTION,
                Permission.MANAGE_SUBSCRIPTION,
                Permission.MAKE_PAYMENT,
                Permission.VIEW_PAYMENTS,
                Permission.SEND_GIFT,
                Permission.RECEIVE_GIFT,
                Permission.VIEW_GIFTS,
                # Дополнительные VIP права
                Permission.API_ACCESS,
            },
            
            UserRole.MODERATOR: {
                # Все права VIP
                Permission.READ_PROFILE,
                Permission.WRITE_PROFILE,
                Permission.VIEW_SUBSCRIPTION,
                Permission.MANAGE_SUBSCRIPTION,
                Permission.MAKE_PAYMENT,
                Permission.VIEW_PAYMENTS,
                Permission.SEND_GIFT,
                Permission.RECEIVE_GIFT,
                Permission.VIEW_GIFTS,
                Permission.API_ACCESS,
                # Модераторские права
                Permission.MODERATE_CONTENT,
                Permission.BAN_USERS,
                Permission.VIEW_LOGS,
            },
            
            UserRole.ADMIN: {
                # Все права модератора
                Permission.READ_PROFILE,
                Permission.WRITE_PROFILE,
                Permission.DELETE_PROFILE,
                Permission.VIEW_SUBSCRIPTION,
                Permission.MANAGE_SUBSCRIPTION,
                Permission.MAKE_PAYMENT,
                Permission.VIEW_PAYMENTS,
                Permission.REFUND_PAYMENT,
                Permission.SEND_GIFT,
                Permission.RECEIVE_GIFT,
                Permission.VIEW_GIFTS,
                Permission.API_ACCESS,
                Permission.MODERATE_CONTENT,
                Permission.BAN_USERS,
                Permission.VIEW_LOGS,
                # Админские права
                Permission.MANAGE_USERS,
                Permission.VIEW_ANALYTICS,
                Permission.API_ADMIN,
            },
            
            UserRole.SUPER_ADMIN: {
                # Все возможные права
                *Permission
            }
        }
    
    def create_session(self, user_id: int, role: UserRole, 
                      ip_address: str = None, user_agent: str = None,
                      expires_in_hours: int = None) -> str:
        """Создание новой сессии"""
        
        # Проверяем лимит сессий
        user_sessions = [s for s in self.active_sessions.values() 
                        if s.user_id == user_id and s.is_valid]
        
        if len(user_sessions) >= self.max_sessions_per_user:
            # Удаляем самую старую сессию
            oldest_session = min(user_sessions, key=lambda s: s.created_at)
            self.revoke_session(oldest_session.session_id)
        
        # Создаем новую сессию
        session_id = self._generate_session_id()
        expires_in = expires_in_hours or self.session_timeout_hours
        
        session = UserSession(
            session_id=session_id,
            user_id=user_id,
            role=role,
            permissions=self.role_permissions.get(role, set()),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=expires_in),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        self.active_sessions[session_id] = session
        
        logger.info(f"Создана сессия {session_id} для пользователя {user_id} с ролью {role.value}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[UserSession]:
        """Получение сессии"""
        session = self.active_sessions.get(session_id)
        
        if not session:
            return None
        
        if not session.is_valid:
            # Удаляем недействительную сессию
            self.revoke_session(session_id)
            return None
        
        # Обновляем время последней активности
        session.last_activity = datetime.now()
        return session
    
    def revoke_session(self, session_id: str) -> bool:
        """Отзыв сессии"""
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            session.is_active = False
            del self.active_sessions[session_id]
            
            logger.info(f"Сессия {session_id} отозвана")
            return True
        
        return False
    
    def revoke_user_sessions(self, user_id: int) -> int:
        """Отзыв всех сессий пользователя"""
        revoked_count = 0
        
        sessions_to_revoke = [
            session_id for session_id, session in self.active_sessions.items()
            if session.user_id == user_id
        ]
        
        for session_id in sessions_to_revoke:
            if self.revoke_session(session_id):
                revoked_count += 1
        
        logger.info(f"Отозвано {revoked_count} сессий для пользователя {user_id}")
        return revoked_count
    
    def check_permission(self, session_id: str, permission: Permission) -> bool:
        """Проверка разрешения"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        return permission in session.permissions
    
    def has_role(self, session_id: str, role: UserRole) -> bool:
        """Проверка роли"""
        session = self.get_session(session_id)
        if not session:
            return False
        
        # Проверяем точное соответствие роли или более высокий уровень
        role_hierarchy = {
            UserRole.GUEST: 0,
            UserRole.USER: 1,
            UserRole.VIP: 2,
            UserRole.MODERATOR: 3,
            UserRole.ADMIN: 4,
            UserRole.SUPER_ADMIN: 5
        }
        
        user_level = role_hierarchy.get(session.role, 0)
        required_level = role_hierarchy.get(role, 0)
        
        return user_level >= required_level
    
    def record_auth_attempt(self, user_id: int, success: bool, 
                           ip_address: str = None, error_reason: str = None):
        """Запись попытки аутентификации"""
        
        if user_id not in self.auth_attempts:
            self.auth_attempts[user_id] = []
        
        attempt = AuthAttempt(
            user_id=user_id,
            timestamp=datetime.now(),
            success=success,
            ip_address=ip_address,
            error_reason=error_reason
        )
        
        self.auth_attempts[user_id].append(attempt)
        
        # Ограничиваем размер истории
        if len(self.auth_attempts[user_id]) > 100:
            self.auth_attempts[user_id] = self.auth_attempts[user_id][-100:]
        
        logger.info(f"Попытка аутентификации пользователя {user_id}: {'успешна' if success else 'неудачна'}")
    
    def is_user_locked(self, user_id: int) -> bool:
        """Проверка блокировки пользователя"""
        if user_id not in self.auth_attempts:
            return False
        
        # Проверяем последние попытки
        cutoff_time = datetime.now() - timedelta(minutes=self.lockout_duration_minutes)
        recent_attempts = [
            attempt for attempt in self.auth_attempts[user_id]
            if attempt.timestamp > cutoff_time and not attempt.success
        ]
        
        return len(recent_attempts) >= self.max_login_attempts
    
    def unlock_user(self, user_id: int):
        """Разблокировка пользователя"""
        if user_id in self.auth_attempts:
            # Удаляем неудачные попытки
            self.auth_attempts[user_id] = [
                attempt for attempt in self.auth_attempts[user_id]
                if attempt.success
            ]
            
            logger.info(f"Пользователь {user_id} разблокирован")
    
    def cleanup_expired_sessions(self) -> int:
        """Очистка истекших сессий"""
        expired_sessions = [
            session_id for session_id, session in self.active_sessions.items()
            if not session.is_valid
        ]
        
        for session_id in expired_sessions:
            del self.active_sessions[session_id]
        
        if expired_sessions:
            logger.info(f"Очищено {len(expired_sessions)} истекших сессий")
        
        return len(expired_sessions)
    
    def get_user_sessions(self, user_id: int) -> List[UserSession]:
        """Получение всех сессий пользователя"""
        return [
            session for session in self.active_sessions.values()
            if session.user_id == user_id and session.is_valid
        ]
    
    def get_auth_stats(self) -> Dict[str, Any]:
        """Статистика аутентификации"""
        total_sessions = len(self.active_sessions)
        active_sessions = len([s for s in self.active_sessions.values() if s.is_valid])
        
        # Статистика по ролям
        role_stats = {}
        for session in self.active_sessions.values():
            if session.is_valid:
                role = session.role.value
                role_stats[role] = role_stats.get(role, 0) + 1
        
        # Статистика попыток аутентификации
        total_attempts = sum(len(attempts) for attempts in self.auth_attempts.values())
        successful_attempts = sum(
            len([a for a in attempts if a.success])
            for attempts in self.auth_attempts.values()
        )
        
        return {
            'total_sessions': total_sessions,
            'active_sessions': active_sessions,
            'sessions_by_role': role_stats,
            'total_auth_attempts': total_attempts,
            'successful_auth_attempts': successful_attempts,
            'success_rate': (successful_attempts / total_attempts * 100) if total_attempts > 0 else 0,
            'locked_users': len([
                user_id for user_id in self.auth_attempts.keys()
                if self.is_user_locked(user_id)
            ])
        }
    
    def _generate_session_id(self) -> str:
        """Генерация ID сессии"""
        # Комбинируем временную метку с случайными данными
        timestamp = str(int(time.time()))
        random_part = secrets.token_hex(16)
        
        # Создаем хеш для дополнительной безопасности
        session_data = f"{timestamp}:{random_part}"
        session_hash = hashlib.sha256(session_data.encode()).hexdigest()
        
        return f"sess_{session_hash[:32]}"

# Декораторы для проверки прав доступа

def require_auth(func):
    """Декоратор требующий аутентификации"""
    @wraps(func)
    async def wrapper(self, update, context, *args, **kwargs):
        # Получаем session_id из контекста
        session_id = getattr(context, 'session_id', None)
        
        if not session_id:
            await update.message.reply_text("❌ Требуется аутентификация")
            return
        
        from auth_manager import get_auth_manager
        auth_manager = get_auth_manager()
        
        if not auth_manager or not auth_manager.get_session(session_id):
            await update.message.reply_text("❌ Сессия недействительна")
            return
        
        return await func(self, update, context, *args, **kwargs)
    
    return wrapper

def require_permission(permission: Permission):
    """Декоратор требующий определенное разрешение"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, update, context, *args, **kwargs):
            session_id = getattr(context, 'session_id', None)
            
            if not session_id:
                await update.message.reply_text("❌ Требуется аутентификация")
                return
            
            from auth_manager import get_auth_manager
            auth_manager = get_auth_manager()
            
            if not auth_manager or not auth_manager.check_permission(session_id, permission):
                await update.message.reply_text("❌ Недостаточно прав доступа")
                return
            
            return await func(self, update, context, *args, **kwargs)
        
        return wrapper
    return decorator

def require_role(role: UserRole):
    """Декоратор требующий определенную роль"""
    def decorator(func):
        @wraps(func)
        async def wrapper(self, update, context, *args, **kwargs):
            session_id = getattr(context, 'session_id', None)
            
            if not session_id:
                await update.message.reply_text("❌ Требуется аутентификация")
                return
            
            from auth_manager import get_auth_manager
            auth_manager = get_auth_manager()
            
            if not auth_manager or not auth_manager.has_role(session_id, role):
                await update.message.reply_text(f"❌ Требуется роль {role.value}")
                return
            
            return await func(self, update, context, *args, **kwargs)
        
        return wrapper
    return decorator

# Middleware для Telegram бота

class TelegramAuthMiddleware:
    """Middleware для аутентификации в Telegram боте"""
    
    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        self.user_sessions: Dict[int, str] = {}  # user_id -> session_id
    
    async def process_update(self, update, context):
        """Обработка обновления с аутентификацией"""
        
        # Извлекаем user_id из обновления
        user_id = None
        if update.message:
            user_id = update.message.from_user.id
        elif update.callback_query:
            user_id = update.callback_query.from_user.id
        
        if not user_id:
            return
        
        # Проверяем существующую сессию
        session_id = self.user_sessions.get(user_id)
        
        if session_id:
            session = self.auth_manager.get_session(session_id)
            if session:
                # Сессия действительна
                context.session_id = session_id
                context.user_session = session
                return
            else:
                # Сессия недействительна, удаляем
                del self.user_sessions[user_id]
        
        # Создаем новую сессию для пользователя
        # По умолчанию роль USER (в реальном приложении нужно получать из БД)
        session_id = self.auth_manager.create_session(
            user_id=user_id,
            role=UserRole.USER  # Получать из базы данных
        )
        
        self.user_sessions[user_id] = session_id
        context.session_id = session_id
        context.user_session = self.auth_manager.get_session(session_id)

# Утилиты для интеграции

def setup_auth_for_bot(bot_instance, auth_manager: AuthManager):
    """Настройка аутентификации для бота"""
    
    # Создаем middleware
    auth_middleware = TelegramAuthMiddleware(auth_manager)
    
    # Добавляем middleware к боту (псевдокод - зависит от реализации)
    # bot_instance.add_middleware(auth_middleware)
    
    logger.info("Аутентификация настроена для бота")

def get_user_role_from_database(user_id: int) -> UserRole:
    """Получение роли пользователя из базы данных"""
    # Заглушка - в реальном приложении получать из БД
    return UserRole.USER

def promote_user_role(auth_manager: AuthManager, user_id: int, new_role: UserRole):
    """Повышение роли пользователя"""
    
    # Отзываем все существующие сессии
    auth_manager.revoke_user_sessions(user_id)
    
    # Обновляем роль в базе данных
    # update_user_role_in_database(user_id, new_role)
    
    logger.info(f"Роль пользователя {user_id} изменена на {new_role.value}")

# Глобальный экземпляр
_global_auth_manager = None

def get_auth_manager() -> Optional[AuthManager]:
    """Получение глобального менеджера аутентификации"""
    return _global_auth_manager

def set_auth_manager(manager: AuthManager):
    """Установка глобального менеджера аутентификации"""
    global _global_auth_manager
    _global_auth_manager = manager 