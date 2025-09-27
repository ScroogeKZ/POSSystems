"""
Language and translation utilities for POS system
"""
from flask import session


# Translation dictionaries for Kazakhstan market
TRANSLATIONS = {
    'categories': {
        'Сүт өнімдері': {'kk': 'Сүт өнімдері', 'ru': 'Молочные продукты'},
        'Нан өнімдері': {'kk': 'Нан өнімдері', 'ru': 'Хлебобулочные'},
        'Сусындар': {'kk': 'Сусындар', 'ru': 'Напитки'},
        'Ет өнімдері': {'kk': 'Ет өнімдері', 'ru': 'Мясные продукты'},
        'Жемістер мен көкөністер': {'kk': 'Жемістер мен көкөністер', 'ru': 'Фрукты и овощи'},
    },
    'products': {
        'Сүт 3.2% 1л': {'kk': 'Сүт 3.2% 1л', 'ru': 'Молоко 3.2% 1л'},
        'Нан ақ': {'kk': 'Нан ақ', 'ru': 'Хлеб белый'},
        'Апельсин шырыны 1л': {'kk': 'Апельсин шырыны 1л', 'ru': 'Сок апельсиновый 1л'},
        'Ірімшік қазақстандық': {'kk': 'Ірімшік қазақстандық', 'ru': 'Сыр казахстанский'},
        'Алма қызыл': {'kk': 'Алма қызыл', 'ru': 'Яблоки красные'},
    },
    'units': {
        'шт.': {'kk': 'дана', 'ru': 'шт.'},
        'кг.': {'kk': 'кг.', 'ru': 'кг.'},
        'л.': {'kk': 'л.', 'ru': 'л.'},
        'м.': {'kk': 'м.', 'ru': 'м.'},
        'упак.': {'kk': 'орам', 'ru': 'упак.'},
    }
}


def get_language():
    """Get current language from session"""
    return session.get('language', 'kk')  # Default to Kazakh


def get_text(kk_text, ru_text):
    """Get text based on current language"""
    if get_language() == 'ru':
        return ru_text
    return kk_text


def translate_name(original_name, category='products'):
    """Translate product/category name based on current language"""
    translations = TRANSLATIONS.get(category, {})
    if original_name in translations:
        return translations[original_name].get(get_language(), original_name)
    return original_name