#!/usr/bin/env python3
"""
Менеджер пользовательских аккаунтов (Pyrogram) для покупок с баланса пользователя
"""

import os
import asyncio
import logging
from typing import Dict, Optional

from pyrogram import Client
from pyrogram.errors import FloodWait, SessionPasswordNeeded, PhoneCodeInvalid, PhoneCodeExpired, PhoneNumberInvalid

from config import USER_API_ID, USER_API_HASH, USER_SESSIONS_DIR, SESSION_ENC_KEY
from session_crypto import encrypt_string, decrypt_string

logger = logging.getLogger(__name__)


class UserAccountsManager:
    """Управление Pyrogram-клиентами пользователей."""

    def __init__(self, db_manager):
        self.db_manager = db_manager
        self._clients: Dict[int, Client] = {}
        self._pending: Dict[int, Dict] = {}
        os.makedirs(USER_SESSIONS_DIR, exist_ok=True)
        # Фоновая задача мониторинга баланса
        self._balance_task: Optional[asyncio.Task] = None

    def _session_file(self, user_id: int) -> str:
        return os.path.join(USER_SESSIONS_DIR, f"user_{user_id}.session")

    async def start_from_session(self, user_id: int) -> bool:
        """Запуск клиента из существующего session-файла (если он уже есть на диске)."""
        try:
            session_path = self._session_file(user_id)
            if not os.path.exists(session_path):
                # Пытаемся поднять по session_string из БД
                try:
                    enc = await self.db_manager.get_user_session_string(user_id)
                    if enc:
                        from pyrogram import Client
                        ss = decrypt_string(enc, SESSION_ENC_KEY)
                        client = Client(name=session_path, api_id=USER_API_ID, api_hash=USER_API_HASH, session_string=ss)
                        await client.start()
                        me = await client.get_me()
                        self._clients[user_id] = client
                        await self.db_manager.set_user_session_connected(user_id, True, session_path=session_path)
                        await self.db_manager.upsert_user_account(user_id, is_connected=True, last_error=None)
                        logger.info(f"✅ Пользовательский аккаунт {user_id} подключен из session_string: @{me.username or me.first_name}")
                        return True
                except Exception:
                    pass
                logger.info(f"Session file not found for user {user_id}: {session_path}")
                return False

            client = Client(
                name=session_path,
                api_id=USER_API_ID,
                api_hash=USER_API_HASH
            )
            await client.start()
            me = await client.get_me()
            self._clients[user_id] = client
            await self.db_manager.set_user_session_connected(user_id, True, session_path=session_path)
            await self.db_manager.upsert_user_account(user_id, is_connected=True, last_error=None)
            logger.info(f"✅ Пользовательский аккаунт {user_id} подключен: @{me.username or me.first_name}")
            return True
        except FloodWait as e:
            logger.warning(f"FloodWait при старте user {user_id}: {e.value}s")
            await asyncio.sleep(e.value)
            return False
        except Exception as e:
            logger.error(f"Ошибка запуска пользовательского клиента {user_id}: {e}")
            await self.db_manager.upsert_user_account(user_id, is_connected=False, last_error=str(e))
            return False

    async def store_session_secret(self, user_id: int, value: str) -> bool:
        """Пример шифрования произвольных секретов (можно расширить под 2FA)."""
        try:
            enc = encrypt_string(value, SESSION_ENC_KEY)
            return bool(self.db_manager.upsert_user_account(user_id, last_error=None))  # заглушка
        except Exception:
            return False

    async def disconnect(self, user_id: int) -> bool:
        try:
            client = self._clients.get(user_id)
            if client:
                try:
                    await client.stop()
                finally:
                    self._clients.pop(user_id, None)
            await self.db_manager.set_user_session_connected(user_id, False)
            return True
        except Exception as e:
            logger.error(f"Ошибка отключения пользовательского клиента {user_id}: {e}")
            return False

    async def reconnect(self, user_id: int) -> bool:
        """Переинициализация клиента из существующей сессии."""
        await self.disconnect(user_id)
        return await self.start_from_session(user_id)

    def _build_client(self, user_id: int) -> Client:
        session_path = self._session_file(user_id)
        return Client(name=session_path, api_id=USER_API_ID, api_hash=USER_API_HASH)

    async def begin_login(self, user_id: int, phone: str) -> str:
        """Начало входа: отправка кода на телефон. Возвращает статус."""
        try:
            client = self._build_client(user_id)
            await client.connect()
            sent = await client.send_code(phone)
            self._pending[user_id] = {
                'client': client,
                'phone': phone,
                'phone_code_hash': getattr(sent, 'phone_code_hash', None)
            }
            return 'code_sent'
        except PhoneNumberInvalid:
            return 'invalid_phone'
        except Exception as e:
            logger.error(f"begin_login error for {user_id}: {e}")
            return 'error'

    async def confirm_code(self, user_id: int, code: str) -> str:
        """Подтверждение кода. Возвращает 'ok', 'need_password', 'invalid_code' или 'error'."""
        try:
            pend = self._pending.get(user_id)
            if not pend:
                return 'error'
            client: Client = pend['client']
            phone = pend['phone']
            phone_code_hash = pend.get('phone_code_hash')
            try:
                if phone_code_hash:
                    await client.sign_in(phone_number=phone, phone_code_hash=phone_code_hash, phone_code=code)
                else:
                    await client.sign_in(phone, code)
            except SessionPasswordNeeded:
                return 'need_password'
            except (PhoneCodeInvalid, PhoneCodeExpired):
                return 'invalid_code'
            # Успех
            me = await client.get_me()
            self._clients[user_id] = client
            self._pending.pop(user_id, None)
            await self.db_manager.set_user_session_connected(user_id, True, session_path=self._session_file(user_id))
            # Пробуем сохранить session_string в БД (шифрованный), если доступно
            try:
                ss = await client.export_session_string()
                if ss:
                    enc = encrypt_string(ss, SESSION_ENC_KEY)
                    await self.db_manager.set_user_session_string(user_id, enc)
            except Exception:
                pass
            await self.db_manager.upsert_user_account(user_id, is_connected=True, last_error=None)
            logger.info(f"✅ Пользовательский аккаунт {user_id} подключен: @{me.username or me.first_name}")
            return 'ok'
        except SessionPasswordNeeded:
            return 'need_password'
        except Exception as e:
            logger.error(f"confirm_code error for {user_id}: {e}")
            return 'error'

    async def submit_password(self, user_id: int, password: str) -> str:
        """Ввод пароля 2FA. Возвращает 'ok' или 'error'."""
        try:
            pend = self._pending.get(user_id)
            if not pend:
                return 'error'
            client: Client = pend['client']
            await client.check_password(password=password)
            me = await client.get_me()
            self._clients[user_id] = client
            self._pending.pop(user_id, None)
            await self.db_manager.set_user_session_connected(user_id, True, session_path=self._session_file(user_id))
            try:
                ss = await client.export_session_string()
                if ss:
                    enc = encrypt_string(ss, SESSION_ENC_KEY)
                    await self.db_manager.set_user_session_string(user_id, enc)
            except Exception:
                pass
            await self.db_manager.upsert_user_account(user_id, is_connected=True, last_error=None)
            logger.info(f"✅ Пользовательский аккаунт {user_id} подключен (2FA): @{me.username or me.first_name}")
            return 'ok'
        except Exception as e:
            logger.error(f"submit_password error for {user_id}: {e}")
            return 'error'

    async def _get_stars_balance(self, client: Client) -> int:
        """Пытаемся получить баланс Stars пользователя. Пока возвращает заглушку."""
        try:
            # TODO: Реализовать получение баланса Stars через подходящий API/бота
            # Пробный запрос: получение своей информации как пинг
            await client.get_me()
            return 1000
        except Exception as e:
            logger.debug(f"_get_stars_balance error: {e}")
            return 0

    async def balance_monitor(self, interval_seconds: int = 1800):
        """Периодически обновляет Stars-баланс для подключенных пользовательских клиентов."""
        if self._balance_task and not self._balance_task.done():
            return
        async def _runner():
            while True:
                try:
                    # Обновляем только текущие подключенные
                    for uid, client in list(self._clients.items()):
                        try:
                            bal = await self._get_stars_balance(client)
                            await self.db_manager.upsert_user_account(uid, stars_balance=bal)
                        except Exception as e:
                            logger.debug(f"balance update failed for {uid}: {e}")
                    await asyncio.sleep(interval_seconds)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"balance_monitor loop error: {e}")
                    await asyncio.sleep(60)
        self._balance_task = asyncio.create_task(_runner())

    def is_connected(self, user_id: int) -> bool:
        client = self._clients.get(user_id)
        return bool(client)

    def get_client(self, user_id: int) -> Optional[Client]:
        return self._clients.get(user_id)

    async def set_purchase_mode(self, user_id: int, mode: str) -> bool:
        try:
            return bool(self.db_manager.set_user_purchase_mode(user_id, mode))
        except Exception as e:
            logger.error(f"Ошибка смены режима покупки для {user_id}: {e}")
            return False


