#!/usr/bin/env python3
"""
Менеджер покупки Telegram Stars через Fragment.com
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Tuple
from config import FRAGMENT_CONFIG, ADMIN_ID
import aiohttp

logger = logging.getLogger(__name__)

class FragmentStarsManager:
    """Менеджер покупки Stars через Fragment.com"""
    
    def __init__(self, db_manager, bot_instance=None):
        self.db_manager = db_manager
        self.bot_instance = bot_instance  # Для отправки уведомлений админу
        self.packages = FRAGMENT_CONFIG['stars_packages']
        self.pending_purchases = {}  # Ожидающие покупки
        
        logger.info("Fragment Stars Manager инициализирован")
    
    def calculate_optimal_package(self, needed_stars: int) -> Dict:
        """Расчет оптимального пакета или комбинации пакетов"""
        try:
            if needed_stars < FRAGMENT_CONFIG['min_stars_purchase']:
                needed_stars = FRAGMENT_CONFIG['min_stars_purchase']
            
            # Находим наиболее выгодную комбинацию
            best_combination = self._find_best_combination(needed_stars)
            
            if not best_combination:
                # Если не нашли комбинацию, берем ближайший больший пакет
                for stars in sorted(self.packages.keys()):
                    if stars >= needed_stars:
                        best_combination = [stars]
                        break
            
            if not best_combination:
                # Если нужно больше максимального пакета, используем несколько больших
                max_package = max(self.packages.keys())
                count = (needed_stars + max_package - 1) // max_package
                best_combination = [max_package] * count
            
            # Рассчитываем общую стоимость
            total_stars = sum(best_combination)
            total_ton = sum(self.packages[stars]['ton'] for stars in best_combination)
            total_usd = sum(self.packages[stars]['usd'] for stars in best_combination)
            
            # Рассчитываем экономию по сравнению с Telegram
            telegram_price_usd = total_stars * 0.02  # Примерная цена в Telegram
            savings_usd = telegram_price_usd - total_usd
            savings_percent = (savings_usd / telegram_price_usd) * 100
            
            return {
                'needed_stars': needed_stars,
                'packages': best_combination,
                'total_stars': total_stars,
                'total_ton': round(total_ton, 4),
                'total_usd': round(total_usd, 2),
                'savings_usd': round(savings_usd, 2),
                'savings_percent': round(savings_percent, 1),
                'overpurchase': total_stars - needed_stars
            }
            
        except Exception as e:
            logger.error(f"Ошибка расчета оптимального пакета: {e}")
            return {
                'needed_stars': needed_stars,
                'packages': [FRAGMENT_CONFIG['min_stars_purchase']],
                'total_stars': FRAGMENT_CONFIG['min_stars_purchase'],
                'total_ton': self.packages[FRAGMENT_CONFIG['min_stars_purchase']]['ton'],
                'total_usd': self.packages[FRAGMENT_CONFIG['min_stars_purchase']]['usd'],
                'error': str(e)
            }
    
    def _find_best_combination(self, needed_stars: int) -> Optional[List[int]]:
        """Находит оптимальную комбинацию пакетов (динамическое программирование)"""
        try:
            packages = sorted(self.packages.keys())
            
            # DP для нахождения минимальной стоимости
            dp = [float('inf')] * (needed_stars + max(packages) + 1)
            parent = [-1] * (needed_stars + max(packages) + 1)
            dp[0] = 0
            
            for i in range(needed_stars + max(packages) + 1):
                if dp[i] == float('inf'):
                    continue
                    
                for package in packages:
                    if i + package < len(dp):
                        new_cost = dp[i] + self.packages[package]['ton']
                        if new_cost < dp[i + package]:
                            dp[i + package] = new_cost
                            parent[i + package] = package
            
            # Находим минимальную стоимость для >= needed_stars
            best_stars = needed_stars
            best_cost = dp[needed_stars]
            
            for stars in range(needed_stars, min(needed_stars + max(packages), len(dp))):
                if dp[stars] < best_cost:
                    best_cost = dp[stars]
                    best_stars = stars
            
            # Восстанавливаем комбинацию
            combination = []
            current = best_stars
            while current > 0 and parent[current] != -1:
                package = parent[current]
                combination.append(package)
                current -= package
            
            return combination if combination else None
            
        except Exception as e:
            logger.error(f"Ошибка поиска оптимальной комбинации: {e}")
            return None
    
    def generate_fragment_url(self, recipient_username: str, package_info: Dict) -> str:
        """Генерация ссылки Fragment для покупки"""
        try:
            base_url = FRAGMENT_CONFIG['base_url']
            
            # Для простоты берем первый (или единственный) пакет
            # В реальности можно создать несколько ссылок для комбинации
            main_package = package_info['packages'][0]
            
            url = f"{base_url}/stars?recipient={recipient_username}&amount={main_package}"
            
            return url
            
        except Exception as e:
            logger.error(f"Ошибка генерации Fragment URL: {e}")
            return f"{FRAGMENT_CONFIG['base_url']}/stars"
    
    async def request_stars_topup(self, account_username: str, needed_stars: int, 
                                 account_key: str = None) -> Dict:
        """Запрос пополнения Stars через Fragment"""
        try:
            # Рассчитываем оптимальный пакет
            package_info = self.calculate_optimal_package(needed_stars)
            
            # Генерируем ссылку
            fragment_url = self.generate_fragment_url(account_username, package_info)
            
            # Создаем запись о pending покупке
            purchase_id = f"stars_{account_key}_{int(datetime.now().timestamp())}"
            self.pending_purchases[purchase_id] = {
                'account_username': account_username,
                'account_key': account_key,
                'needed_stars': needed_stars,
                'package_info': package_info,
                'fragment_url': fragment_url,
                'created_at': datetime.now(),
                'status': 'pending'
            }
            
            # Отправляем уведомление админу
            await self._notify_admin_topup_needed(purchase_id, package_info, fragment_url)
            
            # Ожидаем подтверждения покупки
            result = await self._wait_for_purchase_confirmation(
                purchase_id, 
                timeout_minutes=FRAGMENT_CONFIG['notification_settings']['timeout_minutes']
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка запроса пополнения Stars: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _notify_admin_topup_needed(self, purchase_id: str, package_info: Dict, 
                                       fragment_url: str):
        """Уведомление админу о необходимости покупки Stars"""
        try:
            if not self.bot_instance:
                logger.warning("Bot instance не установлен для уведомлений")
                return
            
            # Определяем срочность
            is_urgent = package_info['needed_stars'] >= FRAGMENT_CONFIG['notification_settings']['urgent_threshold']
            urgency_emoji = "🚨" if is_urgent else "🌟"
            
            message = f"""
{urgency_emoji} **ПОЛЬЗОВАТЕЛЬ ПОПОЛНИЛ БАЛАНС - НУЖНЫ STARS**

💎 **Причина:** Пользователь пополнил баланс, нужно обеспечить Stars для будущих покупок

📊 **Детали заказа:**
⭐ Нужно Stars: {package_info['needed_stars']:,}
📦 Рекомендуемые пакеты: {', '.join(map(str, package_info['packages']))}
🎯 Итого Stars: {package_info['total_stars']:,}
💰 Стоимость: {package_info['total_ton']} TON (${package_info['total_usd']})

💡 **Экономия vs Telegram:**
💵 Экономия: ${package_info.get('savings_usd', 0)}
📊 Процент экономии: {package_info.get('savings_percent', 0)}%

🔗 **Ссылка для покупки:**
{fragment_url}

⏰ **Время ожидания:** {FRAGMENT_CONFIG['notification_settings']['timeout_minutes']} минут
🆔 **ID заказа:** `{purchase_id}`

✅ `/confirm_{purchase_id}` - подтвердить покупку
❌ `/cancel_{purchase_id}` - отложить покупку
            """
            
            # Отправляем уведомление админу
            await self.bot_instance.send_message(
                chat_id=ADMIN_ID,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Уведомление о покупке Stars отправлено админу: {purchase_id}")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу: {e}")
    
    async def _wait_for_purchase_confirmation(self, purchase_id: str, 
                                            timeout_minutes: int = 60) -> Dict:
        """Ожидание подтверждения покупки"""
        try:
            timeout_seconds = timeout_minutes * 60
            start_time = datetime.now()
            
            while (datetime.now() - start_time).total_seconds() < timeout_seconds:
                # Проверяем статус покупки
                if purchase_id in self.pending_purchases:
                    purchase = self.pending_purchases[purchase_id]
                    
                    if purchase['status'] == 'confirmed':
                        # Покупка подтверждена
                        del self.pending_purchases[purchase_id]
                        return {
                            'success': True,
                            'purchase_id': purchase_id,
                            'stars_purchased': purchase['package_info']['total_stars']
                        }
                    elif purchase['status'] == 'cancelled':
                        # Покупка отменена
                        del self.pending_purchases[purchase_id]
                        return {
                            'success': False,
                            'error': 'Покупка отменена администратором'
                        }
                
                # Ждем 30 секунд перед следующей проверкой
                await asyncio.sleep(30)
            
            # Таймаут
            if purchase_id in self.pending_purchases:
                self.pending_purchases[purchase_id]['status'] = 'timeout'
            
            return {
                'success': False,
                'error': f'Таймаут ожидания покупки ({timeout_minutes} минут)'
            }
            
        except Exception as e:
            logger.error(f"Ошибка ожидания подтверждения покупки: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def confirm_purchase(self, purchase_id: str) -> bool:
        """Подтверждение покупки администратором"""
        try:
            if purchase_id in self.pending_purchases:
                self.pending_purchases[purchase_id]['status'] = 'confirmed'
                self.pending_purchases[purchase_id]['confirmed_at'] = datetime.now()
                
                logger.info(f"Покупка Stars подтверждена: {purchase_id}")
                return True
            else:
                logger.warning(f"Покупка не найдена: {purchase_id}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка подтверждения покупки: {e}")
            return False
    
    async def cancel_purchase(self, purchase_id: str) -> bool:
        """Отмена покупки администратором"""
        try:
            if purchase_id in self.pending_purchases:
                self.pending_purchases[purchase_id]['status'] = 'cancelled'
                self.pending_purchases[purchase_id]['cancelled_at'] = datetime.now()
                
                logger.info(f"Покупка Stars отменена: {purchase_id}")
                return True
            else:
                logger.warning(f"Покупка не найдена: {purchase_id}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка отмены покупки: {e}")
            return False
    
    def get_pending_purchases(self) -> List[Dict]:
        """Получение списка ожидающих покупок"""
        try:
            return [
                {
                    'purchase_id': pid,
                    **purchase_data
                }
                for pid, purchase_data in self.pending_purchases.items()
                if purchase_data['status'] == 'pending'
            ]
            
        except Exception as e:
            logger.error(f"Ошибка получения ожидающих покупок: {e}")
            return []
    
    async def cleanup_old_purchases(self, max_age_hours: int = 24):
        """Очистка старых записей о покупках"""
        try:
            current_time = datetime.now()
            to_remove = []
            
            for purchase_id, purchase_data in self.pending_purchases.items():
                age = current_time - purchase_data['created_at']
                if age.total_seconds() > max_age_hours * 3600:
                    to_remove.append(purchase_id)
            
            for purchase_id in to_remove:
                del self.pending_purchases[purchase_id]
                logger.info(f"Удалена старая запись о покупке: {purchase_id}")
                
        except Exception as e:
            logger.error(f"Ошибка очистки старых покупок: {e}") 