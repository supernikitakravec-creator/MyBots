#!/usr/bin/env python3
"""
Encryption Manager - система шифрования для TgGIFT Bot
"""

import logging
import os
import base64
import hashlib
import secrets
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime, timedelta

# Криптографические библиотеки
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import bcrypt

logger = logging.getLogger(__name__)

class EncryptionType(Enum):
    """Типы шифрования"""
    SYMMETRIC = "symmetric"      # Симметричное (Fernet)
    ASYMMETRIC = "asymmetric"    # Асимметричное (RSA)
    PASSWORD = "password"        # Хеширование паролей (bcrypt)
    AES = "aes"                 # AES-256

class KeyType(Enum):
    """Типы ключей"""
    MASTER_KEY = "master_key"
    DATABASE_KEY = "database_key"
    SESSION_KEY = "session_key"
    USER_KEY = "user_key"
    BACKUP_KEY = "backup_key"

@dataclass
class EncryptionKey:
    """Ключ шифрования"""
    key_id: str
    key_type: KeyType
    algorithm: str
    key_data: bytes
    created_at: datetime
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    @property
    def is_expired(self) -> bool:
        """Проверка истечения ключа"""
        if self.expires_at:
            return datetime.now() > self.expires_at
        return False

class EncryptionManager:
    """Менеджер шифрования"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        
        # Настройки
        self.key_rotation_days = self.config.get('key_rotation_days', 90)
        self.master_key_env = self.config.get('master_key_env', 'MASTER_ENCRYPTION_KEY')
        
        # Хранилище ключей
        self.keys: Dict[str, EncryptionKey] = {}
        
        # Инициализация мастер-ключа
        self._initialize_master_key()
        
        logger.info("Encryption Manager инициализирован")
    
    def _initialize_master_key(self):
        """Инициализация мастер-ключа"""
        # Получаем мастер-ключ из переменной окружения
        master_key_b64 = os.getenv(self.master_key_env)
        
        if not master_key_b64:
            # Генерируем новый мастер-ключ
            master_key = Fernet.generate_key()
            master_key_b64 = base64.b64encode(master_key).decode()
            
            logger.warning(f"Сгенерирован новый мастер-ключ. Сохраните в {self.master_key_env}:")
            logger.warning(f"{self.master_key_env}={master_key_b64}")
        else:
            master_key = base64.b64decode(master_key_b64)
        
        # Сохраняем мастер-ключ
        self.keys['master'] = EncryptionKey(
            key_id='master',
            key_type=KeyType.MASTER_KEY,
            algorithm='Fernet',
            key_data=master_key,
            created_at=datetime.now()
        )
    
    def generate_key(self, key_type: KeyType, algorithm: str = 'Fernet',
                    expires_in_days: Optional[int] = None) -> str:
        """Генерация нового ключа"""
        
        key_id = f"{key_type.value}_{secrets.token_hex(8)}"
        
        # Генерируем ключ в зависимости от алгоритма
        if algorithm == 'Fernet':
            key_data = Fernet.generate_key()
        elif algorithm == 'AES-256':
            key_data = secrets.token_bytes(32)  # 256 бит
        elif algorithm == 'RSA-2048':
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048
            )
            key_data = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            )
        else:
            raise ValueError(f"Неподдерживаемый алгоритм: {algorithm}")
        
        # Определяем срок действия
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now() + timedelta(days=expires_in_days)
        elif self.key_rotation_days > 0:
            expires_at = datetime.now() + timedelta(days=self.key_rotation_days)
        
        # Создаем ключ
        encryption_key = EncryptionKey(
            key_id=key_id,
            key_type=key_type,
            algorithm=algorithm,
            key_data=key_data,
            created_at=datetime.now(),
            expires_at=expires_at
        )
        
        # Сохраняем ключ
        self.keys[key_id] = encryption_key
        
        logger.info(f"Сгенерирован ключ {key_id} ({algorithm})")
        return key_id
    
    def get_key(self, key_id: str) -> Optional[EncryptionKey]:
        """Получение ключа"""
        key = self.keys.get(key_id)
        
        if key and key.is_expired:
            logger.warning(f"Ключ {key_id} истек")
            return None
        
        return key
    
    def encrypt_data(self, data: Union[str, bytes], key_id: str = None,
                    algorithm: str = 'Fernet') -> Dict[str, Any]:
        """Шифрование данных"""
        
        # Используем мастер-ключ если не указан другой
        if not key_id:
            key_id = 'master'
        
        key = self.get_key(key_id)
        if not key:
            raise ValueError(f"Ключ {key_id} не найден или истек")
        
        # Подготавливаем данные
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        try:
            if algorithm == 'Fernet' or key.algorithm == 'Fernet':
                fernet = Fernet(key.key_data)
                encrypted_data = fernet.encrypt(data)
                
            elif algorithm == 'AES-256' or key.algorithm == 'AES-256':
                # AES-256-GCM
                iv = secrets.token_bytes(12)  # 96 бит для GCM
                cipher = Cipher(
                    algorithms.AES(key.key_data),
                    modes.GCM(iv)
                )
                encryptor = cipher.encryptor()
                encrypted_data = encryptor.update(data) + encryptor.finalize()
                # Комбинируем IV, tag и зашифрованные данные
                encrypted_data = iv + encryptor.tag + encrypted_data
                
            elif algorithm == 'RSA-2048' or key.algorithm == 'RSA-2048':
                private_key = serialization.load_pem_private_key(
                    key.key_data, password=None
                )
                public_key = private_key.public_key()
                encrypted_data = public_key.encrypt(
                    data,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
            else:
                raise ValueError(f"Неподдерживаемый алгоритм: {algorithm}")
            
            return {
                'encrypted_data': base64.b64encode(encrypted_data).decode(),
                'key_id': key_id,
                'algorithm': key.algorithm,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Ошибка шифрования: {e}")
            raise
    
    def decrypt_data(self, encrypted_package: Dict[str, Any]) -> bytes:
        """Расшифровка данных"""
        
        key_id = encrypted_package['key_id']
        algorithm = encrypted_package['algorithm']
        encrypted_data = base64.b64decode(encrypted_package['encrypted_data'])
        
        key = self.get_key(key_id)
        if not key:
            raise ValueError(f"Ключ {key_id} не найден или истек")
        
        try:
            if algorithm == 'Fernet':
                fernet = Fernet(key.key_data)
                decrypted_data = fernet.decrypt(encrypted_data)
                
            elif algorithm == 'AES-256':
                # Извлекаем IV, tag и данные
                iv = encrypted_data[:12]
                tag = encrypted_data[12:28]
                ciphertext = encrypted_data[28:]
                
                cipher = Cipher(
                    algorithms.AES(key.key_data),
                    modes.GCM(iv, tag)
                )
                decryptor = cipher.decryptor()
                decrypted_data = decryptor.update(ciphertext) + decryptor.finalize()
                
            elif algorithm == 'RSA-2048':
                private_key = serialization.load_pem_private_key(
                    key.key_data, password=None
                )
                decrypted_data = private_key.decrypt(
                    encrypted_data,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )
            else:
                raise ValueError(f"Неподдерживаемый алгоритм: {algorithm}")
            
            return decrypted_data
            
        except Exception as e:
            logger.error(f"Ошибка расшифровки: {e}")
            raise
    
    def hash_password(self, password: str, rounds: int = 12) -> str:
        """Хеширование пароля"""
        salt = bcrypt.gensalt(rounds=rounds)
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Проверка пароля"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.error(f"Ошибка проверки пароля: {e}")
            return False
    
    def generate_secure_token(self, length: int = 32) -> str:
        """Генерация безопасного токена"""
        return secrets.token_urlsafe(length)
    
    def generate_api_key(self, prefix: str = "tggift") -> str:
        """Генерация API ключа"""
        token = secrets.token_urlsafe(32)
        return f"{prefix}_{token}"
    
    def hash_data(self, data: Union[str, bytes], algorithm: str = 'SHA-256') -> str:
        """Хеширование данных"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        if algorithm == 'SHA-256':
            hash_obj = hashlib.sha256(data)
        elif algorithm == 'SHA-512':
            hash_obj = hashlib.sha512(data)
        elif algorithm == 'MD5':
            hash_obj = hashlib.md5(data)
        else:
            raise ValueError(f"Неподдерживаемый алгоритм хеширования: {algorithm}")
        
        return hash_obj.hexdigest()
    
    def derive_key_from_password(self, password: str, salt: bytes = None) -> bytes:
        """Получение ключа из пароля"""
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 256 бит
            salt=salt,
            iterations=100000,
        )
        
        key = kdf.derive(password.encode('utf-8'))
        return key
    
    def rotate_keys(self) -> List[str]:
        """Ротация ключей"""
        rotated_keys = []
        
        for key_id, key in list(self.keys.items()):
            if key.key_id == 'master':  # Мастер-ключ не ротируем автоматически
                continue
            
            if key.is_expired:
                # Генерируем новый ключ того же типа
                new_key_id = self.generate_key(key.key_type, key.algorithm)
                rotated_keys.append(f"{key_id} -> {new_key_id}")
                
                # Старый ключ помечаем как устаревший (не удаляем для расшифровки)
                key.metadata = key.metadata or {}
                key.metadata['deprecated'] = True
                key.metadata['replaced_by'] = new_key_id
        
        if rotated_keys:
            logger.info(f"Ротированы ключи: {rotated_keys}")
        
        return rotated_keys
    
    def get_encryption_stats(self) -> Dict[str, Any]:
        """Статистика шифрования"""
        active_keys = len([k for k in self.keys.values() if not k.is_expired])
        expired_keys = len([k for k in self.keys.values() if k.is_expired])
        
        keys_by_type = {}
        keys_by_algorithm = {}
        
        for key in self.keys.values():
            # По типам
            key_type = key.key_type.value
            if key_type not in keys_by_type:
                keys_by_type[key_type] = 0
            keys_by_type[key_type] += 1
            
            # По алгоритмам
            algorithm = key.algorithm
            if algorithm not in keys_by_algorithm:
                keys_by_algorithm[algorithm] = 0
            keys_by_algorithm[algorithm] += 1
        
        return {
            'total_keys': len(self.keys),
            'active_keys': active_keys,
            'expired_keys': expired_keys,
            'keys_by_type': keys_by_type,
            'keys_by_algorithm': keys_by_algorithm,
            'key_rotation_days': self.key_rotation_days
        }

class SecureDataManager:
    """Менеджер безопасного хранения данных"""
    
    def __init__(self, encryption_manager: EncryptionManager):
        self.encryption_manager = encryption_manager
        
        # Поля, которые нужно шифровать
        self.encrypted_fields = {
            'users': ['phone_number', 'email', 'payment_data'],
            'payments': ['card_number', 'cvv', 'account_details'],
            'sessions': ['session_data', 'user_context'],
            'logs': ['sensitive_data', 'user_input']
        }
    
    def encrypt_user_data(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Шифрование пользовательских данных"""
        encrypted_data = user_data.copy()
        
        for field in self.encrypted_fields.get('users', []):
            if field in encrypted_data and encrypted_data[field]:
                try:
                    encrypted_package = self.encryption_manager.encrypt_data(
                        str(encrypted_data[field])
                    )
                    encrypted_data[f"{field}_encrypted"] = encrypted_package
                    # Удаляем оригинальное поле
                    del encrypted_data[field]
                except Exception as e:
                    logger.error(f"Ошибка шифрования поля {field}: {e}")
        
        return encrypted_data
    
    def decrypt_user_data(self, encrypted_user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Расшифровка пользовательских данных"""
        decrypted_data = encrypted_user_data.copy()
        
        # Находим зашифрованные поля
        encrypted_fields = [k for k in decrypted_data.keys() if k.endswith('_encrypted')]
        
        for encrypted_field in encrypted_fields:
            original_field = encrypted_field.replace('_encrypted', '')
            
            try:
                encrypted_package = decrypted_data[encrypted_field]
                decrypted_bytes = self.encryption_manager.decrypt_data(encrypted_package)
                decrypted_data[original_field] = decrypted_bytes.decode('utf-8')
                
                # Удаляем зашифрованное поле
                del decrypted_data[encrypted_field]
                
            except Exception as e:
                logger.error(f"Ошибка расшифровки поля {original_field}: {e}")
        
        return decrypted_data
    
    def secure_delete(self, data: Union[str, bytes]) -> None:
        """Безопасное удаление данных из памяти"""
        # В Python сложно гарантированно удалить данные из памяти
        # Но мы можем перезаписать переменную
        if isinstance(data, str):
            data = 'X' * len(data)
        elif isinstance(data, bytes):
            data = b'X' * len(data)

# Утилиты для интеграции

def setup_encryption_for_database(db_manager, encryption_manager: EncryptionManager):
    """Настройка шифрования для базы данных"""
    
    # Генерируем ключ для базы данных
    db_key_id = encryption_manager.generate_key(KeyType.DATABASE_KEY)
    
    # Создаем менеджер безопасных данных
    secure_data_manager = SecureDataManager(encryption_manager)
    
    # Добавляем методы шифрования в адаптер базы данных
    original_save_user = db_manager.save_user
    original_get_user = db_manager.get_user
    
    def encrypted_save_user(user_data: Dict[str, Any]):
        encrypted_data = secure_data_manager.encrypt_user_data(user_data)
        return original_save_user(encrypted_data)
    
    def encrypted_get_user(user_id: int):
        encrypted_data = original_get_user(user_id)
        if encrypted_data:
            return secure_data_manager.decrypt_user_data(encrypted_data)
        return encrypted_data
    
    # Заменяем методы
    db_manager.save_user = encrypted_save_user
    db_manager.get_user = encrypted_get_user
    
    logger.info("Шифрование настроено для базы данных")

def create_secure_session_token(encryption_manager: EncryptionManager, 
                               user_id: int, expires_in_hours: int = 24) -> str:
    """Создание безопасного токена сессии"""
    
    session_data = {
        'user_id': user_id,
        'created_at': datetime.now().isoformat(),
        'expires_at': (datetime.now() + timedelta(hours=expires_in_hours)).isoformat(),
        'nonce': secrets.token_hex(16)
    }
    
    # Шифруем данные сессии
    encrypted_package = encryption_manager.encrypt_data(json.dumps(session_data))
    
    # Кодируем в base64 для использования в URL
    token = base64.urlsafe_b64encode(
        json.dumps(encrypted_package).encode()
    ).decode()
    
    return token

def verify_secure_session_token(encryption_manager: EncryptionManager, 
                               token: str) -> Optional[Dict[str, Any]]:
    """Проверка токена сессии"""
    try:
        # Декодируем из base64
        encrypted_package_json = base64.urlsafe_b64decode(token).decode()
        encrypted_package = json.loads(encrypted_package_json)
        
        # Расшифровываем
        decrypted_data = encryption_manager.decrypt_data(encrypted_package)
        session_data = json.loads(decrypted_data.decode())
        
        # Проверяем срок действия
        expires_at = datetime.fromisoformat(session_data['expires_at'])
        if datetime.now() > expires_at:
            return None
        
        return session_data
        
    except Exception as e:
        logger.error(f"Ошибка проверки токена сессии: {e}")
        return None

# Глобальный экземпляр
_global_encryption_manager = None

def get_encryption_manager() -> Optional[EncryptionManager]:
    """Получение глобального менеджера шифрования"""
    return _global_encryption_manager

def set_encryption_manager(manager: EncryptionManager):
    """Установка глобального менеджера шифрования"""
    global _global_encryption_manager
    _global_encryption_manager = manager 