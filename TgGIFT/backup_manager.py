#!/usr/bin/env python3
"""
Backup Manager - система бэкапов для TgGIFT Bot PostgreSQL
"""

import logging
import asyncio
import os
import subprocess
import shutil
import gzip
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
import hashlib
import tempfile

logger = logging.getLogger(__name__)

class BackupManager:
    """Менеджер бэкапов PostgreSQL"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # Настройки подключения к БД
        self.db_host = config.get('db_host', 'localhost')
        self.db_port = config.get('db_port', 5432)
        self.db_name = config.get('db_name', 'tggift')
        self.db_user = config.get('db_user', 'tggift_user')
        self.db_password = config.get('db_password')
        
        # Настройки бэкапов
        self.backup_dir = Path(config.get('backup_dir', 'backups'))
        self.retention_days = config.get('retention_days', 30)
        self.compression = config.get('compression', True)
        self.encryption = config.get('encryption', False)
        self.encryption_key = config.get('encryption_key')
        
        # Настройки расписания
        self.daily_backup_hour = config.get('daily_backup_hour', 2)  # 2 AM
        self.weekly_backup_day = config.get('weekly_backup_day', 6)  # Sunday
        self.monthly_backup_day = config.get('monthly_backup_day', 1)  # 1st day
        
        # Удаленное хранилище (опционально)
        self.remote_storage = config.get('remote_storage', {})
        
        # Создаем директорию для бэкапов
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Backup Manager инициализирован: {self.backup_dir}")
    
    def _get_pg_dump_command(self, output_file: str, backup_type: str = 'full') -> List[str]:
        """Формирование команды pg_dump"""
        cmd = [
            'pg_dump',
            f'--host={self.db_host}',
            f'--port={self.db_port}',
            f'--username={self.db_user}',
            f'--dbname={self.db_name}',
            '--verbose',
            '--no-password',
            f'--file={output_file}'
        ]
        
        if backup_type == 'schema_only':
            cmd.append('--schema-only')
        elif backup_type == 'data_only':
            cmd.append('--data-only')
        
        # Добавляем формат
        if output_file.endswith('.sql'):
            cmd.extend(['--format=plain', '--no-owner', '--no-privileges'])
        else:
            cmd.extend(['--format=custom', '--compress=9'])
        
        return cmd
    
    def _get_pg_restore_command(self, backup_file: str, target_db: str = None) -> List[str]:
        """Формирование команды pg_restore"""
        target = target_db or self.db_name
        
        cmd = [
            'pg_restore',
            f'--host={self.db_host}',
            f'--port={self.db_port}',
            f'--username={self.db_user}',
            f'--dbname={target}',
            '--verbose',
            '--no-password',
            '--clean',
            '--if-exists',
            '--no-owner',
            '--no-privileges',
            backup_file
        ]
        
        return cmd
    
    async def create_backup(self, backup_type: str = 'full', 
                          description: str = None) -> Dict[str, Any]:
        """Создание бэкапа"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"tggift_backup_{backup_type}_{timestamp}"
        
        # Определяем расширение файла
        if self.compression:
            backup_file = self.backup_dir / f"{backup_name}.dump.gz"
            temp_file = self.backup_dir / f"{backup_name}.dump"
        else:
            backup_file = self.backup_dir / f"{backup_name}.dump"
            temp_file = backup_file
        
        backup_info = {
            'name': backup_name,
            'type': backup_type,
            'timestamp': datetime.now().isoformat(),
            'description': description or f"Автоматический {backup_type} бэкап",
            'file_path': str(backup_file),
            'status': 'in_progress'
        }
        
        try:
            logger.info(f"Создание бэкапа: {backup_name}")
            
            # Устанавливаем переменную окружения для пароля
            env = os.environ.copy()
            if self.db_password:
                env['PGPASSWORD'] = self.db_password
            
            # Выполняем pg_dump
            cmd = self._get_pg_dump_command(str(temp_file), backup_type)
            
            start_time = datetime.now()
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            duration = (datetime.now() - start_time).total_seconds()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                logger.error(f"Ошибка создания бэкапа: {error_msg}")
                backup_info.update({
                    'status': 'failed',
                    'error': error_msg,
                    'duration': duration
                })
                return backup_info
            
            # Сжимаем файл если нужно
            if self.compression and temp_file != backup_file:
                await self._compress_file(temp_file, backup_file)
                temp_file.unlink()  # Удаляем временный файл
            
            # Шифруем если нужно
            if self.encryption:
                encrypted_file = backup_file.with_suffix(backup_file.suffix + '.enc')
                await self._encrypt_file(backup_file, encrypted_file)
                backup_file.unlink()  # Удаляем незашифрованный файл
                backup_file = encrypted_file
                backup_info['file_path'] = str(backup_file)
            
            # Получаем информацию о файле
            file_size = backup_file.stat().st_size
            file_hash = await self._calculate_file_hash(backup_file)
            
            backup_info.update({
                'status': 'completed',
                'duration': duration,
                'file_size': file_size,
                'file_size_mb': round(file_size / (1024 * 1024), 2),
                'file_hash': file_hash,
                'compressed': self.compression,
                'encrypted': self.encryption
            })
            
            # Сохраняем метаданные
            await self._save_backup_metadata(backup_info)
            
            # Загружаем в удаленное хранилище если настроено
            if self.remote_storage.get('enabled'):
                await self._upload_to_remote_storage(backup_file, backup_info)
            
            logger.info(f"Бэкап создан успешно: {backup_name} ({backup_info['file_size_mb']} MB)")
            return backup_info
            
        except Exception as e:
            logger.error(f"Критическая ошибка создания бэкапа: {e}")
            backup_info.update({
                'status': 'failed',
                'error': str(e)
            })
            return backup_info
    
    async def restore_backup(self, backup_file: str, target_db: str = None,
                           confirm: bool = False) -> Dict[str, Any]:
        """Восстановление из бэкапа"""
        if not confirm:
            return {
                'status': 'cancelled',
                'message': 'Восстановление требует подтверждения (confirm=True)'
            }
        
        backup_path = Path(backup_file)
        if not backup_path.exists():
            return {
                'status': 'failed',
                'error': f'Файл бэкапа не найден: {backup_file}'
            }
        
        restore_info = {
            'backup_file': backup_file,
            'target_db': target_db or self.db_name,
            'timestamp': datetime.now().isoformat(),
            'status': 'in_progress'
        }
        
        try:
            logger.warning(f"НАЧАЛО ВОССТАНОВЛЕНИЯ БД из {backup_file}")
            
            # Расшифровываем если нужно
            working_file = backup_path
            if backup_file.endswith('.enc'):
                decrypted_file = backup_path.with_suffix('')
                await self._decrypt_file(backup_path, decrypted_file)
                working_file = decrypted_file
            
            # Распаковываем если нужно
            if working_file.suffix == '.gz':
                uncompressed_file = working_file.with_suffix('')
                await self._decompress_file(working_file, uncompressed_file)
                if working_file != backup_path:  # Если это расшифрованный файл
                    working_file.unlink()
                working_file = uncompressed_file
            
            # Устанавливаем переменную окружения для пароля
            env = os.environ.copy()
            if self.db_password:
                env['PGPASSWORD'] = self.db_password
            
            # Выполняем восстановление
            cmd = self._get_pg_restore_command(str(working_file), target_db)
            
            start_time = datetime.now()
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            duration = (datetime.now() - start_time).total_seconds()
            
            # Очищаем временные файлы
            if working_file != backup_path:
                working_file.unlink()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                logger.error(f"Ошибка восстановления: {error_msg}")
                restore_info.update({
                    'status': 'failed',
                    'error': error_msg,
                    'duration': duration
                })
                return restore_info
            
            restore_info.update({
                'status': 'completed',
                'duration': duration,
                'message': f'База данных успешно восстановлена из {backup_file}'
            })
            
            logger.info(f"Восстановление завершено успешно за {duration:.2f}s")
            return restore_info
            
        except Exception as e:
            logger.error(f"Критическая ошибка восстановления: {e}")
            restore_info.update({
                'status': 'failed',
                'error': str(e)
            })
            return restore_info
    
    async def list_backups(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Получение списка бэкапов"""
        backups = []
        
        try:
            # Сканируем директорию бэкапов
            for backup_file in self.backup_dir.glob('tggift_backup_*'):
                if backup_file.is_file():
                    stat = backup_file.stat()
                    
                    # Пытаемся загрузить метаданные
                    metadata_file = backup_file.with_suffix(backup_file.suffix + '.meta')
                    metadata = {}
                    
                    if metadata_file.exists():
                        try:
                            with open(metadata_file, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                        except:
                            pass
                    
                    backup_info = {
                        'name': backup_file.stem,
                        'file_path': str(backup_file),
                        'file_size': stat.st_size,
                        'file_size_mb': round(stat.st_size / (1024 * 1024), 2),
                        'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        **metadata
                    }
                    
                    backups.append(backup_info)
            
            # Сортируем по дате создания (новые первые)
            backups.sort(key=lambda x: x['created'], reverse=True)
            
            return backups[:limit]
            
        except Exception as e:
            logger.error(f"Ошибка получения списка бэкапов: {e}")
            return []
    
    async def cleanup_old_backups(self) -> Dict[str, Any]:
        """Очистка старых бэкапов"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        cleaned_files = []
        total_size_freed = 0
        
        try:
            for backup_file in self.backup_dir.glob('tggift_backup_*'):
                if backup_file.is_file():
                    file_date = datetime.fromtimestamp(backup_file.stat().st_ctime)
                    
                    if file_date < cutoff_date:
                        file_size = backup_file.stat().st_size
                        
                        # Удаляем файл бэкапа
                        backup_file.unlink()
                        
                        # Удаляем метаданные если есть
                        metadata_file = backup_file.with_suffix(backup_file.suffix + '.meta')
                        if metadata_file.exists():
                            metadata_file.unlink()
                        
                        cleaned_files.append({
                            'name': backup_file.name,
                            'size_mb': round(file_size / (1024 * 1024), 2),
                            'date': file_date.isoformat()
                        })
                        
                        total_size_freed += file_size
            
            result = {
                'cleaned_files': len(cleaned_files),
                'total_size_freed_mb': round(total_size_freed / (1024 * 1024), 2),
                'retention_days': self.retention_days,
                'files': cleaned_files
            }
            
            if cleaned_files:
                logger.info(f"Очищено {len(cleaned_files)} старых бэкапов, "
                           f"освобождено {result['total_size_freed_mb']} MB")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка очистки старых бэкапов: {e}")
            return {'error': str(e)}
    
    async def verify_backup(self, backup_file: str) -> Dict[str, Any]:
        """Проверка целостности бэкапа"""
        backup_path = Path(backup_file)
        
        if not backup_path.exists():
            return {
                'status': 'failed',
                'error': f'Файл бэкапа не найден: {backup_file}'
            }
        
        verify_info = {
            'backup_file': backup_file,
            'timestamp': datetime.now().isoformat(),
            'checks': []
        }
        
        try:
            # Проверка 1: Размер файла
            file_size = backup_path.stat().st_size
            verify_info['checks'].append({
                'name': 'file_size',
                'status': 'passed' if file_size > 0 else 'failed',
                'value': file_size
            })
            
            # Проверка 2: Контрольная сумма
            current_hash = await self._calculate_file_hash(backup_path)
            
            # Загружаем сохраненную контрольную сумму
            metadata_file = backup_path.with_suffix(backup_path.suffix + '.meta')
            expected_hash = None
            
            if metadata_file.exists():
                try:
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        expected_hash = metadata.get('file_hash')
                except:
                    pass
            
            hash_check = {
                'name': 'checksum',
                'current_hash': current_hash,
                'expected_hash': expected_hash
            }
            
            if expected_hash:
                hash_check['status'] = 'passed' if current_hash == expected_hash else 'failed'
            else:
                hash_check['status'] = 'skipped'
                hash_check['message'] = 'Нет сохраненной контрольной суммы'
            
            verify_info['checks'].append(hash_check)
            
            # Проверка 3: Можно ли прочитать файл как бэкап PostgreSQL
            try:
                # Пытаемся получить информацию о бэкапе
                cmd = ['pg_restore', '--list', str(backup_path)]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                pg_check = {
                    'name': 'postgresql_format',
                    'status': 'passed' if process.returncode == 0 else 'failed'
                }
                
                if process.returncode == 0:
                    # Подсчитываем количество объектов в бэкапе
                    lines = stdout.decode().strip().split('\n')
                    pg_check['objects_count'] = len([l for l in lines if l.strip()])
                else:
                    pg_check['error'] = stderr.decode()
                
                verify_info['checks'].append(pg_check)
                
            except Exception as e:
                verify_info['checks'].append({
                    'name': 'postgresql_format',
                    'status': 'failed',
                    'error': str(e)
                })
            
            # Определяем общий статус
            all_checks = [c for c in verify_info['checks'] if c['status'] != 'skipped']
            failed_checks = [c for c in all_checks if c['status'] == 'failed']
            
            if not failed_checks:
                verify_info['status'] = 'passed'
                verify_info['message'] = 'Все проверки пройдены'
            else:
                verify_info['status'] = 'failed'
                verify_info['message'] = f'Не пройдено проверок: {len(failed_checks)}'
            
            return verify_info
            
        except Exception as e:
            logger.error(f"Ошибка проверки бэкапа: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    # Вспомогательные методы
    
    async def _compress_file(self, source_file: Path, target_file: Path):
        """Сжатие файла"""
        def compress():
            with open(source_file, 'rb') as f_in:
                with gzip.open(target_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        
        await asyncio.get_event_loop().run_in_executor(None, compress)
    
    async def _decompress_file(self, source_file: Path, target_file: Path):
        """Распаковка файла"""
        def decompress():
            with gzip.open(source_file, 'rb') as f_in:
                with open(target_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        
        await asyncio.get_event_loop().run_in_executor(None, decompress)
    
    async def _encrypt_file(self, source_file: Path, target_file: Path):
        """Шифрование файла (заглушка - требует реализации)"""
        # TODO: Реализовать шифрование с использованием cryptography
        logger.warning("Шифрование файлов не реализовано")
        shutil.copy2(source_file, target_file)
    
    async def _decrypt_file(self, source_file: Path, target_file: Path):
        """Расшифровка файла (заглушка - требует реализации)"""
        # TODO: Реализовать расшифровку
        logger.warning("Расшифровка файлов не реализована")
        shutil.copy2(source_file, target_file)
    
    async def _calculate_file_hash(self, file_path: Path) -> str:
        """Вычисление контрольной суммы файла"""
        def calculate():
            hash_sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        
        return await asyncio.get_event_loop().run_in_executor(None, calculate)
    
    async def _save_backup_metadata(self, backup_info: Dict[str, Any]):
        """Сохранение метаданных бэкапа"""
        metadata_file = Path(backup_info['file_path']).with_suffix('.meta')
        
        try:
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(backup_info, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения метаданных: {e}")
    
    async def _upload_to_remote_storage(self, backup_file: Path, backup_info: Dict[str, Any]):
        """Загрузка в удаленное хранилище (заглушка)"""
        # TODO: Реализовать загрузку в S3/Google Cloud/etc.
        logger.info(f"Загрузка в удаленное хранилище: {backup_file.name}")
    
    def get_backup_stats(self) -> Dict[str, Any]:
        """Получение статистики бэкапов"""
        try:
            backup_files = list(self.backup_dir.glob('tggift_backup_*'))
            
            if not backup_files:
                return {
                    'total_backups': 0,
                    'total_size_mb': 0,
                    'oldest_backup': None,
                    'newest_backup': None
                }
            
            total_size = sum(f.stat().st_size for f in backup_files)
            
            # Сортируем по дате создания
            backup_files.sort(key=lambda x: x.stat().st_ctime)
            
            return {
                'total_backups': len(backup_files),
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'oldest_backup': {
                    'name': backup_files[0].name,
                    'date': datetime.fromtimestamp(backup_files[0].stat().st_ctime).isoformat()
                },
                'newest_backup': {
                    'name': backup_files[-1].name,
                    'date': datetime.fromtimestamp(backup_files[-1].stat().st_ctime).isoformat()
                },
                'retention_days': self.retention_days,
                'backup_dir': str(self.backup_dir)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики бэкапов: {e}")
            return {'error': str(e)} 