# Сервис пагинации для POS системы
from flask import request, url_for
from sqlalchemy import func
from math import ceil


class PaginationService:
    """Сервис для обработки пагинации в POS системе"""
    
    def __init__(self, query, page=1, per_page=20, error_out=False):
        self.query = query
        self.page = max(1, page)
        self.per_page = min(max(1, per_page), 100)  # Ограничиваем до 100 элементов
        self.error_out = error_out
        self.total = None
        self.items = None
        self._paginate()
    
    def _paginate(self):
        """Выполнение пагинации"""
        # Получаем общее количество
        self.total = self.query.count()
        
        # Рассчитываем смещение
        offset = (self.page - 1) * self.per_page
        
        # Получаем элементы для текущей страницы
        self.items = self.query.offset(offset).limit(self.per_page).all()
        
        # Если запрошенная страница больше доступных и error_out=True
        if self.error_out and self.page > self.pages and self.total > 0:
            raise ValueError(f"Page {self.page} is out of range")
    
    @property
    def pages(self):
        """Общее количество страниц"""
        if self.total == 0:
            return 1
        return ceil(self.total / self.per_page)
    
    @property
    def has_prev(self):
        """Есть ли предыдущая страница"""
        return self.page > 1
    
    @property
    def prev_num(self):
        """Номер предыдущей страницы"""
        return self.page - 1 if self.has_prev else None
    
    @property
    def has_next(self):
        """Есть ли следующая страница"""
        return self.page < self.pages
    
    @property
    def next_num(self):
        """Номер следующей страницы"""
        return self.page + 1 if self.has_next else None
    
    def iter_pages(self, left_edge=2, left_current=2, right_current=3, right_edge=2):
        """Итератор для номеров страниц с разумными пропусками"""
        last = self.pages
        for num in range(1, last + 1):
            if num <= left_edge or \
               (self.page - left_current - 1 < num < self.page + right_current) or \
               num > last - right_edge:
                yield num
    
    def get_page_range(self, window=5):
        """Получение диапазона страниц для отображения"""
        start = max(1, self.page - window // 2)
        end = min(self.pages, start + window - 1)
        
        # Корректируем начало если конец упирается в максимум
        if end - start < window - 1:
            start = max(1, end - window + 1)
        
        return list(range(start, end + 1))
    
    def get_pagination_info(self):
        """Получение информации о пагинации для API"""
        return {
            'page': self.page,
            'per_page': self.per_page,
            'total': self.total,
            'pages': self.pages,
            'has_prev': self.has_prev,
            'prev_num': self.prev_num,
            'has_next': self.has_next,
            'next_num': self.next_num,
            'items_count': len(self.items),
            'start_index': (self.page - 1) * self.per_page + 1,
            'end_index': min(self.page * self.per_page, self.total)
        }
    
    def get_pagination_urls(self, endpoint, **kwargs):
        """Получение URL для навигации по страницам"""
        urls = {}
        
        if self.has_prev:
            urls['prev'] = url_for(endpoint, page=self.prev_num, **kwargs)
        
        if self.has_next:
            urls['next'] = url_for(endpoint, page=self.next_num, **kwargs)
        
        urls['first'] = url_for(endpoint, page=1, **kwargs)
        urls['last'] = url_for(endpoint, page=self.pages, **kwargs)
        
        return urls


def paginate_query(query, page=None, per_page=None, error_out=False):
    """Функция-помощник для пагинации запросов"""
    # Получаем параметры из запроса если не переданы
    if page is None:
        page = request.args.get('page', 1, type=int)
    
    if per_page is None:
        per_page = request.args.get('per_page', 20, type=int)
    
    return PaginationService(query, page=page, per_page=per_page, error_out=error_out)


def create_pagination_context(pagination, endpoint, **kwargs):
    """Создание контекста для шаблонов пагинации"""
    return {
        'pagination': pagination,
        'pagination_info': pagination.get_pagination_info(),
        'pagination_urls': pagination.get_pagination_urls(endpoint, **kwargs),
        'page_range': pagination.get_page_range()
    }