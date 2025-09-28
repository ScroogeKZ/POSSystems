# Redis кэширование для POS системы
import json
import redis
from datetime import datetime, timedelta
from flask import current_app
from typing import Optional, List, Dict, Any, Callable


class CacheService:
    """Сервис кэширования для улучшения производительности POS системы"""
    
    def __init__(self, app=None):
        self.redis_client = None
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Инициализация Redis клиента"""
        try:
            # Попытка подключиться к Redis
            redis_url = app.config.get('REDIS_URL', 'redis://localhost:6379/0')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            
            # Проверка подключения
            self.redis_client.ping()
            app.logger.info("Redis cache connected successfully")
            
        except (redis.ConnectionError, redis.TimeoutError) as e:
            app.logger.warning(f"Redis connection failed: {e}. Cache will be disabled.")
            self.redis_client = None
            
        except Exception as e:
            app.logger.error(f"Redis initialization error: {e}")
            self.redis_client = None
    
    def is_available(self):
        """Проверка доступности Redis"""
        if not self.redis_client:
            return False
        try:
            self.redis_client.ping()
            return True
        except:
            return False
    
    def set(self, key, value, ttl=300):
        """Установка значения в кэш с TTL (время жизни в секундах)"""
        if not self.is_available():
            return False
        
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, default=str)
            
            return self.redis_client.setex(key, ttl, value)
        except Exception as e:
            current_app.logger.error(f"Cache SET error for key {key}: {e}")
            return False
    
    def get(self, key):
        """Получение значения из кэша"""
        if not self.is_available():
            return None
        
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
                
        except Exception as e:
            current_app.logger.error(f"Cache GET error for key {key}: {e}")
            return None
    
    def delete(self, key):
        """Удаление ключа из кэша"""
        if not self.is_available():
            return False
        
        try:
            return self.redis_client.delete(key) > 0
        except Exception as e:
            current_app.logger.error(f"Cache DELETE error for key {key}: {e}")
            return False
    
    def delete_pattern(self, pattern):
        """Удаление ключей по паттерну (безопасно через SCAN)"""
        if not self.is_available():
            return False
        
        try:
            # Используем SCAN вместо KEYS для безопасности в production
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = self.redis_client.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted += self.redis_client.delete(*keys)
                if cursor == 0:
                    break
            return deleted > 0
        except Exception as e:
            current_app.logger.error(f"Cache DELETE PATTERN error for {pattern}: {e}")
            return False
    
    def exists(self, key):
        """Проверка существования ключа"""
        if not self.is_available():
            return False
        
        try:
            return self.redis_client.exists(key) > 0
        except Exception as e:
            current_app.logger.error(f"Cache EXISTS error for key {key}: {e}")
            return False
    
    def get_or_set(self, key, callback, ttl=300):
        """Получить из кэша или установить через callback"""
        value = self.get(key)
        if value is not None:
            return value
        
        # Если в кэше нет, получаем через callback
        value = callback()
        self.set(key, value, ttl)
        return value
    
    # Методы для кэширования популярных товаров
    def get_popular_products(self, limit=10, days=7, force_refresh=False):
        """Получение популярных товаров с кэшированием"""
        cache_key = f"popular_products:{limit}:{days}"
        
        if not force_refresh:
            cached_data = self.get(cache_key)
            if cached_data:
                return cached_data
        
        # Получаем данные из БД
        def fetch_popular_products():
            from models import Product, Transaction, TransactionItem, TransactionStatus, db
            from sqlalchemy import func, desc
            start_date = datetime.now() - timedelta(days=days)
            
            popular = db.session.query(
                Product.id,
                Product.name,
                Product.price,
                Product.stock_quantity,
                Product.image_filename,
                func.sum(TransactionItem.quantity).label('total_sold'),
                func.count(TransactionItem.id).label('transaction_count')
            ).join(
                TransactionItem, Product.id == TransactionItem.product_id
            ).join(
                Transaction, TransactionItem.transaction_id == Transaction.id
            ).filter(
                Transaction.status == TransactionStatus.COMPLETED,
                Transaction.completed_at >= start_date,
                Product.is_active == True
            ).group_by(
                Product.id, Product.name, Product.price, Product.stock_quantity, Product.image_filename
            ).order_by(
                desc('total_sold')
            ).limit(limit).all()
            
            return [{
                'id': p.id,
                'name': p.name,
                'price': float(p.price),
                'stock_quantity': p.stock_quantity,
                'image_filename': p.image_filename,
                'total_sold': int(p.total_sold),
                'transaction_count': int(p.transaction_count)
            } for p in popular]
        
        data = fetch_popular_products()
        # Кэшируем на 10 минут
        self.set(cache_key, data, ttl=600)
        return data
    
    def get_categories_with_counts(self, force_refresh=False):
        """Получение категорий с количеством товаров (кэширование)"""
        cache_key = "categories_with_counts"
        
        if not force_refresh:
            cached_data = self.get(cache_key)
            if cached_data:
                return cached_data
        
        def fetch_categories():
            from models import Product, Category, db
            from sqlalchemy import func
            categories = db.session.query(
                Category.id,
                Category.name,
                func.count(Product.id).label('product_count')
            ).outerjoin(
                Product, Category.id == Product.category_id
            ).filter(
                Product.is_active == True
            ).group_by(
                Category.id, Category.name
            ).order_by(Category.name).all()
            
            return [{
                'id': c.id,
                'name': c.name,
                'product_count': int(c.product_count)
            } for c in categories]
        
        data = fetch_categories()
        # Кэшируем на 5 минут
        self.set(cache_key, data, ttl=300)
        return data
    
    def get_dashboard_stats(self, force_refresh=False):
        """Получение статистики для дашборда с кэшированием"""
        cache_key = f"dashboard_stats:{datetime.now().date()}"
        
        if not force_refresh:
            cached_data = self.get(cache_key)
            if cached_data:
                return cached_data
        
        def fetch_dashboard_stats():
            from models import Product, Transaction, TransactionStatus, db
            from sqlalchemy import func
            today = datetime.now().date()
            
            # Общее количество активных товаров
            total_products = Product.query.filter_by(is_active=True).count()
            
            # Товары с низким остатком
            low_stock_count = Product.query.filter(
                Product.stock_quantity <= Product.min_stock_level,
                Product.is_active == True
            ).count()
            
            # Продажи за сегодня
            today_sales = db.session.query(func.sum(Transaction.total_amount)).filter(
                func.date(Transaction.created_at) == today,
                Transaction.status == TransactionStatus.COMPLETED
            ).scalar() or 0
            
            # Количество транзакций за сегодня
            today_transactions = Transaction.query.filter(
                func.date(Transaction.created_at) == today,
                Transaction.status == TransactionStatus.COMPLETED
            ).count()
            
            return {
                'total_products': total_products,
                'low_stock_count': low_stock_count,
                'today_sales': float(today_sales),
                'today_transactions': today_transactions,
                'cache_updated': datetime.now().isoformat()
            }
        
        data = fetch_dashboard_stats()
        # Кэшируем на 2 минуты
        self.set(cache_key, data, ttl=120)
        return data
    
    def invalidate_product_cache(self, product_id=None):
        """Сброс кэша товаров при обновлении"""
        patterns = [
            "popular_products:*",
            "categories_with_counts",
            "dashboard_stats:*"
        ]
        
        if product_id:
            patterns.append(f"product:{product_id}:*")
        
        for pattern in patterns:
            self.delete_pattern(pattern)
    
    def invalidate_category_cache(self):
        """Сброс кэша категорий"""
        self.delete_pattern("categories_with_counts")
        self.delete_pattern("popular_products:*")
    
    def invalidate_sales_cache(self):
        """Сброс кэша продаж"""
        self.delete_pattern("dashboard_stats:*")
        self.delete_pattern("popular_products:*")
    
    def get_cache_info(self):
        """Получение информации о состоянии кэша"""
        if not self.is_available():
            return {'status': 'disabled', 'redis_connected': False}
        
        try:
            info = self.redis_client.info()
            return {
                'status': 'active',
                'redis_connected': True,
                'redis_version': info.get('redis_version'),
                'used_memory_human': info.get('used_memory_human'),
                'connected_clients': info.get('connected_clients'),
                'total_keys': self.redis_client.dbsize()
            }
        except Exception as e:
            return {
                'status': 'error',
                'redis_connected': False,
                'error': str(e)
            }


# Глобальный экземпляр кэша
cache_service = CacheService()


def init_cache(app):
    """Инициализация кэша в приложении"""
    cache_service.init_app(app)
    return cache_service