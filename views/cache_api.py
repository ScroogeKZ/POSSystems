# API для управления кэшем
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from models import UserRole
from services.cache_service import cache_service
from utils.helpers import require_role

cache_api_bp = Blueprint('cache_api', __name__, url_prefix='/api/cache')


@cache_api_bp.route('/info')
@login_required
@require_role(UserRole.MANAGER)
def get_cache_info():
    """Получение информации о состоянии кэша"""
    return jsonify(cache_service.get_cache_info())


@cache_api_bp.route('/clear', methods=['POST'])
@login_required
@require_role(UserRole.ADMIN)
def clear_cache():
    """Очистка кэша (только для администраторов)"""
    try:
        # Очищаем основные кэши
        cache_service.delete_pattern("popular_products:*")
        cache_service.delete_pattern("categories_with_counts")
        cache_service.delete_pattern("dashboard_stats:*")
        
        return jsonify({
            'success': True,
            'message': 'Кэш успешно очищен'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@cache_api_bp.route('/refresh/<cache_type>', methods=['POST'])
@login_required
@require_role(UserRole.MANAGER)
def refresh_cache(cache_type):
    """Обновление конкретного типа кэша"""
    try:
        if cache_type == 'popular':
            data = cache_service.get_popular_products(force_refresh=True)
        elif cache_type == 'categories':
            data = cache_service.get_categories_with_counts(force_refresh=True)
        elif cache_type == 'dashboard':
            data = cache_service.get_dashboard_stats(force_refresh=True)
        else:
            return jsonify({
                'success': False,
                'error': 'Неизвестный тип кэша'
            }), 400
        
        return jsonify({
            'success': True,
            'message': f'Кэш {cache_type} обновлен',
            'data': data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500