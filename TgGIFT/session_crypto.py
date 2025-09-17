#!/usr/bin/env python3
"""
Простые утилиты для шифрования/дешифрования строк сессий с использованием cryptography (Fernet).
"""

import base64
import hashlib
from typing import Optional

try:
    from cryptography.fernet import Fernet
except Exception:  # cryptography может отсутствовать в рантайме
    Fernet = None  # type: ignore


def _derive_key(secret: str) -> Optional[bytes]:
    if not secret:
        return None
    # Деривация ключа из произвольной строки: SHA256 -> urlsafe_b64
    h = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(h)


def encrypt_string(plain_text: str, secret: str) -> str:
    """Шифрует строку. Если secret пустой или cryptography недоступна — возвращает исходный текст."""
    if not plain_text:
        return plain_text
    if Fernet is None or not secret:
        return plain_text
    key = _derive_key(secret)
    if not key:
        return plain_text
    f = Fernet(key)
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_string(cipher_text: str, secret: str) -> str:
    """Дешифрует строку. Если secret пустой или cryptography недоступна — возвращает исходный текст."""
    if not cipher_text:
        return cipher_text
    if Fernet is None or not secret:
        return cipher_text
    key = _derive_key(secret)
    if not key:
        return cipher_text
    f = Fernet(key)
    try:
        return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return cipher_text


