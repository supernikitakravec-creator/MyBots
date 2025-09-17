import httpx
import json
from typing import Dict, List, Optional, Any
from loguru import logger
from config.settings import settings

class WebasystAPI:
    """Класс для работы с Webasyst API"""
    
    def __init__(self):
        self.base_url = settings.WEBASYST_API_URL.rstrip('/')
        self.token = settings.WEBASYST_API_TOKEN
        self.shop_id = settings.WEBASYST_SHOP_ID
        
        if not self.token:
            logger.error("Не указан токен Webasyst API")
            raise ValueError("WEBASYST_API_TOKEN не настроен")
        
        self.headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """
        Выполняет запрос к API
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method.upper() == 'GET':
                    response = await client.get(url, headers=self.headers)
                elif method.upper() == 'POST':
                    response = await client.post(url, headers=self.headers, json=data)
                elif method.upper() == 'PUT':
                    response = await client.put(url, headers=self.headers, json=data)
                else:
                    logger.error(f"Неподдерживаемый метод: {method}")
                    return None
                
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP ошибка при запросе к {url}: {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Ошибка запроса к {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при запросе к {url}: {e}")
            return None
    
    async def get_products(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        Получает список товаров
        """
        endpoint = f"products?limit={limit}&offset={offset}"
        if self.shop_id:
            endpoint += f"&shop_id={self.shop_id}"
        
        result = await self._make_request('GET', endpoint)
        if result and 'products' in result:
            return result['products']
        return []
    
    async def get_product_by_id(self, product_id: int) -> Optional[Dict]:
        """
        Получает товар по ID
        """
        endpoint = f"products/{product_id}"
        return await self._make_request('GET', endpoint)
    
    async def update_product_price(self, product_id: int, new_price: float) -> bool:
        """
        Обновляет цену товара
        """
        data = {
            'price': new_price
        }
        
        endpoint = f"products/{product_id}"
        result = await self._make_request('PUT', endpoint, data)
        
        if result:
            logger.info(f"Цена товара {product_id} обновлена на {new_price}")
            return True
        else:
            logger.error(f"Не удалось обновить цену товара {product_id}")
            return False
    
    async def search_products(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Ищет товары по названию
        """
        endpoint = f"products?q={query}&limit={limit}"
        if self.shop_id:
            endpoint += f"&shop_id={self.shop_id}"
        
        result = await self._make_request('GET', endpoint)
        if result and 'products' in result:
            return result['products']
        return []
    
    async def get_product_by_sku(self, sku: str) -> Optional[Dict]:
        """
        Получает товар по артикулу
        """
        products = await self.search_products(sku, limit=10)
        
        for product in products:
            if product.get('sku') == sku:
                return product
        
        return None
    
    async def find_matching_product(self, title: str, price: float) -> Optional[Dict]:
        """
        Ищет товар по названию и цене
        """
        # Ищем по названию
        products = await self.search_products(title, limit=20)
        
        if not products:
            return None
        
        # Ищем наиболее подходящий товар
        best_match = None
        best_score = 0
        
        for product in products:
            product_title = product.get('name', '').lower()
            product_price = float(product.get('price', 0))
            
            # Простая оценка совпадения
            title_similarity = self._calculate_title_similarity(title.lower(), product_title)
            price_similarity = 1 - abs(price - product_price) / max(price, product_price, 1)
            
            score = title_similarity * 0.7 + price_similarity * 0.3
            
            if score > best_score and score > 0.5:  # Минимальный порог совпадения
                best_score = score
                best_match = product
        
        return best_match
    
    def _calculate_title_similarity(self, title1: str, title2: str) -> float:
        """
        Вычисляет схожесть названий товаров
        """
        words1 = set(title1.split())
        words2 = set(title2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    async def batch_update_prices(self, updates: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Пакетное обновление цен
        """
        results = {
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        
        for update in updates:
            product_id = update.get('product_id')
            new_price = update.get('new_price')
            
            if not product_id or new_price is None:
                results['skipped'] += 1
                continue
            
            success = await self.update_product_price(product_id, new_price)
            if success:
                results['success'] += 1
            else:
                results['failed'] += 1
        
        logger.info(f"Пакетное обновление завершено: {results['success']} успешно, {results['failed']} ошибок, {results['skipped']} пропущено")
        return results 