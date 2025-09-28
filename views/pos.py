from flask import Blueprint, render_template, request, jsonify, session, current_app
from flask_login import login_required, current_user
from models import db, Product, Category, Transaction, TransactionItem, Payment, PromoCode, OperationLog
from models import PaymentMethod, TransactionStatus, UnitType, UserRole
from utils.helpers import log_operation, generate_transaction_number
from utils.language import get_language, translate_name
from sqlalchemy import or_, desc, func, and_
from decimal import Decimal
from datetime import datetime, timedelta
import json
import secrets
import string
import time

# Create Blueprint
pos_bp = Blueprint('pos', __name__)

# В памяти кеш для популярных товаров с индивидуальными TTL
popular_products_cache = {
    'ttl': 300,  # 5 минут кеша
    'entries': {}  # Структура: {'key': {'data': [...], 'timestamp': time.time()}}
}

# Helper functions



def update_transaction_totals(transaction):
    """Update transaction totals based on items"""
    # Ensure all values are Decimal for proper arithmetic
    subtotal = Decimal('0.00')
    for item in transaction.items:
        item_total = item.total_price or Decimal('0.00')
        item_discount = item.discount_amount or Decimal('0.00')
        subtotal += (item_total - item_discount)
    
    transaction.subtotal = subtotal
    transaction.tax_amount = subtotal * Decimal('0.12')  # 12% VAT (Kazakhstan rate)
    transaction.total_amount = subtotal + transaction.tax_amount - (transaction.discount_amount or Decimal('0.00'))

# Routes

@pos_bp.route('/pos')
@login_required
def pos():
    """POS Terminal Interface"""
    categories = Category.query.all()
    # Translate category names for current language
    for category in categories:
        category.translated_name = translate_name(category.name, 'categories')
    return render_template('pos.html', categories=categories)

@pos_bp.route('/api/products/search')
@login_required
def search_products():
    """API endpoint for live product search"""
    query = request.args.get('q', '').strip()
    category_id = request.args.get('category_id')
    
    if len(query) < 2 and not category_id:
        return jsonify([])
    
    # Build search query
    search_query = Product.query.filter_by(is_active=True)
    
    if query:
        search_query = search_query.filter(
            or_(
                Product.name.ilike(f'%{query}%'),
                Product.sku.ilike(f'%{query}%')
            )
        )
    
    if category_id:
        search_query = search_query.filter_by(category_id=category_id)
    
    products = search_query.limit(10).all()
    
    return jsonify([{
        'id': p.id,
        'sku': p.sku,
        'name': translate_name(p.name, 'products'),
        'price': float(p.price),
        'stock_quantity': p.stock_quantity,
        'unit_type': translate_name(p.unit_type.value, 'units'),
        'image_filename': p.image_filename
    } for p in products])

@pos_bp.route('/api/search-barcode')
@login_required
def search_barcode():
    """API endpoint for barcode product search"""
    barcode = request.args.get('code', '').strip()
    
    if not barcode:
        return jsonify({
            'success': False,
            'error': 'Barcode is required'
        })
    
    # Search by barcode first, then by SKU as fallback
    product = Product.query.filter_by(barcode=barcode, is_active=True).first()
    
    if not product:
        # Fallback: try to find by SKU (in case barcode is same as SKU)
        product = Product.query.filter_by(sku=barcode, is_active=True).first()
    
    if product:
        return jsonify({
            'success': True,
            'product': {
                'id': product.id,
                'sku': product.sku,
                'barcode': product.barcode,
                'name': translate_name(product.name, 'products'),
                'price': float(product.price),
                'stock_quantity': product.stock_quantity,
                'unit_type': translate_name(product.unit_type.value, 'units'),
                'image_filename': product.image_filename,
                'category_name': translate_name(product.category.name, 'categories') if product.category else None,
                'supplier_name': product.supplier.name if product.supplier else None
            }
        })
    else:
        return jsonify({
            'success': False,
            'error': f'Product with barcode {barcode} not found'
        })

def get_cached_popular_products(limit=10, days=30):
    """Получить популярные товары с кешированием"""
    current_time = time.time()
    cache_key = f"{limit}_{days}"
    
    # Проверяем кеш для конкретного ключа
    if (cache_key in popular_products_cache['entries'] and
        popular_products_cache['entries'][cache_key]['timestamp'] + popular_products_cache['ttl'] > current_time):
        return popular_products_cache['entries'][cache_key]['data']
    
    # Вычисляем данные
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    popular_products_query = db.session.query(
        Product.id,
        Product.name,
        Product.sku,
        Product.price,
        Product.stock_quantity,
        Product.unit_type,
        Product.image_filename,
        func.count(TransactionItem.id).label('transaction_count'),
        func.sum(TransactionItem.quantity).label('total_sold'),
        func.avg(TransactionItem.quantity).label('avg_quantity_per_sale')
    ).join(
        TransactionItem, Product.id == TransactionItem.product_id
    ).join(
        Transaction, TransactionItem.transaction_id == Transaction.id
    ).filter(
        Product.is_active == True,
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.completed_at >= cutoff_date
    ).group_by(
        Product.id, Product.name, Product.sku, Product.price, 
        Product.stock_quantity, Product.unit_type, Product.image_filename
    ).order_by(
        func.count(TransactionItem.id).desc(),
        func.sum(TransactionItem.quantity).desc()
    ).limit(limit)
    
    popular_products = popular_products_query.all()
    
    # Форматируем данные
    products_data = []
    for product in popular_products:
        products_data.append({
            'id': product.id,
            'name': translate_name(product.name, 'products'),
            'sku': product.sku,
            'price': float(product.price),
            'stock_quantity': product.stock_quantity,
            'unit_type': translate_name(product.unit_type.value, 'units'),
            'image_filename': product.image_filename,
            'popularity_stats': {
                'transaction_count': product.transaction_count,
                'total_sold': float(product.total_sold) if product.total_sold else 0,
                'avg_quantity_per_sale': round(float(product.avg_quantity_per_sale), 2) if product.avg_quantity_per_sale else 0
            }
        })
    
    # Сохраняем в кеш с индивидуальным timestamp
    popular_products_cache['entries'][cache_key] = {
        'data': products_data,
        'timestamp': current_time
    }
    
    # Ограничиваем размер кеша (максимум 20 записей)
    if len(popular_products_cache['entries']) > 20:
        # Удаляем самую старую запись
        oldest_key = min(popular_products_cache['entries'].keys(), 
                        key=lambda k: popular_products_cache['entries'][k]['timestamp'])
        del popular_products_cache['entries'][oldest_key]
    
    return products_data


def clear_popular_products_cache():
    """Очистка кеша популярных товаров (используется при завершении транзакций)"""
    popular_products_cache['entries'].clear()


@pos_bp.route('/api/popular-products')
@login_required
def get_popular_products():
    """API endpoint for getting popular/frequently bought products с кешированием"""
    try:
        limit = min(int(request.args.get('limit', 10)), 20)  # Max 20 products
        days = min(int(request.args.get('days', 30)), 90)  # Max 90 days
        
        # Используем кешированную версию
        products_data = get_cached_popular_products(limit, days)
        
        return jsonify({
            'success': True,
            'products': products_data,
            'period_days': days,
            'total_count': len(products_data)
        })
        
    except Exception as e:
        print(f"Error getting popular products: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve popular products'
        })

@pos_bp.route('/api/low-stock-alerts')
@login_required
def get_low_stock_alerts():
    """API endpoint для получения уведомлений о низких остатках товаров (только для менеджеров)"""
    # Проверяем права доступа - только менеджеры и админы
    if not current_user.can_access(UserRole.MANAGER):
        return jsonify({
            'success': False, 
            'error': 'Доступ запрещён. Требуются права менеджера или администратора.'
        }), 403
    
    try:
        # Получаем товары с низкими остатками с правильной логикой для min_stock_level=0
        low_stock_query = db.session.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.stock_quantity,
            Product.min_stock_level,
            Product.unit_type,
            Category.name.label('category_name')
        ).outerjoin(Category, Product.category_id == Category.id).filter(
            Product.is_active == True,
            # Правильная логика: если min_stock_level=0 (не задан), используем 5 как по умолчанию
            Product.stock_quantity <= func.coalesce(func.nullif(Product.min_stock_level, 0), 5)
        ).order_by(Product.stock_quantity.asc()).all()
        
        alerts = []
        for row in low_stock_query:
            min_level = row.min_stock_level or 5
            # Определяем уровень критичности
            if row.stock_quantity == 0:
                severity = 'critical'  # Товар закончился
                message = 'Товар закончился'
            elif row.stock_quantity <= min_level * 0.5:
                severity = 'high'  # Критически низкий остаток
                message = 'Критически низкий остаток'
            else:
                severity = 'medium'  # Низкий остаток
                message = 'Низкий остаток товара'
            
            # Локализованные сообщения
            if severity == 'critical':
                localized_message = translate_name('Товар закончился', 'alerts') 
            elif severity == 'high':
                localized_message = translate_name('Критически низкий остаток', 'alerts')
            else:
                localized_message = translate_name('Низкий остаток товара', 'alerts')
            
            alerts.append({
                'product_id': row.id,
                'product_name': translate_name(row.name, 'products'),
                'sku': row.sku,
                'current_stock': row.stock_quantity,
                'min_stock_level': min_level,
                'severity': severity,
                'message': localized_message,
                'category': translate_name(row.category_name, 'categories') if row.category_name else translate_name('Без категории', 'general'),
                'unit_type': translate_name(row.unit_type.value, 'units') if row.unit_type else translate_name('шт.', 'units')
            })
        
        return jsonify({
            'success': True,
            'alerts': alerts,
            'total_alerts': len(alerts),
            'critical_count': len([a for a in alerts if a['severity'] == 'critical']),
            'high_priority_count': len([a for a in alerts if a['severity'] == 'high'])
        })
        
    except Exception as e:
        print(f"Error getting low stock alerts: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve stock alerts'
        })


@pos_bp.route('/api/quick-access-products')
@login_required 
def get_quick_access_products():
    """API endpoint for getting products for quick access based on multiple factors"""
    try:
        # Get products based on:
        # 1. Recent popularity (last 7 days)
        # 2. Overall popularity (last 30 days) 
        # 3. Current stock availability
        
        from datetime import datetime, timedelta
        
        recent_cutoff = datetime.utcnow() - timedelta(days=7)
        overall_cutoff = datetime.utcnow() - timedelta(days=30)
        
        # Recent popular products (last 7 days)
        recent_popular = db.session.query(
            Product.id,
            func.count(TransactionItem.id).label('recent_sales')
        ).join(
            TransactionItem, Product.id == TransactionItem.product_id
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Product.is_active == True,
            Product.stock_quantity > 0,  # Only in-stock items
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.completed_at >= recent_cutoff
        ).group_by(Product.id).subquery()
        
        # Get products with both recent and overall popularity
        quick_access_products = db.session.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.price,
            Product.stock_quantity,
            Product.unit_type,
            Product.image_filename,
            recent_popular.c.recent_sales,
            func.count(TransactionItem.id).label('overall_sales')
        ).outerjoin(
            recent_popular, Product.id == recent_popular.c.id
        ).join(
            TransactionItem, Product.id == TransactionItem.product_id
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Product.is_active == True,
            Product.stock_quantity > 0,  # Only available items
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.completed_at >= overall_cutoff
        ).group_by(
            Product.id, Product.name, Product.sku, Product.price,
            Product.stock_quantity, Product.unit_type, Product.image_filename,
            recent_popular.c.recent_sales
        ).order_by(
            # Prioritize items with recent sales, then overall sales
            func.coalesce(recent_popular.c.recent_sales, 0).desc(),
            func.count(TransactionItem.id).desc()
        ).limit(8).all()  # Limit to 8 for quick access panel
        
        # Format response
        products_data = []
        for product in quick_access_products:
            products_data.append({
                'id': product.id,
                'name': translate_name(product.name, 'products'),
                'sku': product.sku,
                'price': float(product.price),
                'stock_quantity': product.stock_quantity,
                'unit_type': translate_name(product.unit_type.value, 'units'),
                'image_filename': product.image_filename,
                'recent_sales': product.recent_sales or 0,
                'overall_sales': product.overall_sales
            })
        
        return jsonify({
            'success': True,
            'products': products_data,
            'total_count': len(products_data)
        })
        
    except Exception as e:
        print(f"Error getting quick access products: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to retrieve quick access products'
        })

# Transaction API Routes

@pos_bp.route('/api/transaction/start', methods=['POST'])
@login_required
def start_transaction():
    """Start a new transaction"""
    try:
        data = request.get_json() or {}
        cashier_name = data.get('cashier_name', 'Кассир')
        customer_name = data.get('customer_name', '')
        
        transaction = Transaction(  # type: ignore
            transaction_number=generate_transaction_number(),
            status=TransactionStatus.PENDING,
            cashier_name=cashier_name,
            customer_name=customer_name,
            user_id=current_user.id
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Store transaction ID in session
        session['current_transaction_id'] = transaction.id
        
        return jsonify({
            'success': True,
            'transaction_id': transaction.id,
            'transaction_number': transaction.transaction_number
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/transaction/add_item', methods=['POST'])
def add_item_to_transaction():
    """Add item to current transaction"""
    try:
        data = request.get_json() or {}
        transaction_id = session.get('current_transaction_id')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'Нет активной транзакции'}), 400
        
        transaction = Transaction.query.get(transaction_id)
        if not transaction or transaction.status != TransactionStatus.PENDING:
            return jsonify({'success': False, 'error': 'Транзакция недоступна'}), 400
        
        product = Product.query.get(data['product_id'])
        if not product:
            return jsonify({'success': False, 'error': 'Товар не найден'}), 404
        
        quantity = Decimal(str(data['quantity']))
        if quantity <= 0:
            return jsonify({'success': False, 'error': 'Неверное количество'}), 400
        
        # Check stock
        if product.stock_quantity < float(quantity):
            return jsonify({'success': False, 'error': 'Недостаточно товара на складе'}), 400
        
        # Create new item
        item = TransactionItem(  # type: ignore
            transaction_id=transaction_id,
            product_id=product.id,
            quantity=quantity,
            unit_price=product.price,
            total_price=quantity * product.price,
            discount_amount=Decimal('0.00')
        )
        db.session.add(item)
        
        # Update transaction totals
        update_transaction_totals(transaction)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'item': {
                'product_name': product.name,
                'quantity': quantity,
                'unit_price': float(product.price),
                'total_price': float(quantity * product.price)
            },
            'transaction_total': float(transaction.total_amount)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/transaction/current')
@login_required
def get_current_transaction():
    """Get current transaction details"""
    transaction_id = session.get('current_transaction_id')
    
    if not transaction_id:
        return jsonify({'success': False, 'error': 'Нет активной транзакции'})
    
    transaction = Transaction.query.get(transaction_id)
    if not transaction:
        return jsonify({'success': False, 'error': 'Транзакция не найдена'})
    
    items = []
    for item in transaction.items:
        items.append({
            'id': item.id,
            'product_name': item.product.name,
            'sku': item.product.sku,
            'quantity': float(item.quantity),
            'unit_price': float(item.unit_price),
            'discount_amount': float(item.discount_amount),
            'total_price': float(item.total_price)
        })
    
    return jsonify({
        'success': True,
        'transaction': {
            'id': transaction.id,
            'number': transaction.transaction_number,
            'subtotal': float(transaction.subtotal),
            'discount_amount': float(transaction.discount_amount),
            'tax_amount': float(transaction.tax_amount),
            'total_amount': float(transaction.total_amount),
            'items': items
        }
    })

@pos_bp.route('/api/transaction/complete', methods=['POST'])
def complete_transaction():
    """Complete transaction with payments"""
    try:
        data = request.get_json() or {}
        transaction_id = session.get('current_transaction_id')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'Нет активной транзакции'}), 400
        
        transaction = Transaction.query.get(transaction_id)
        if not transaction or transaction.status != TransactionStatus.PENDING:
            return jsonify({'success': False, 'error': 'Транзакция недоступна'}), 400
        
        payments = data.get('payments', [])
        if not payments:
            return jsonify({'success': False, 'error': 'Не указаны способы оплаты'}), 400
        
        # Validate payment amounts
        total_payment = sum(Decimal(str(p['amount'])) for p in payments)
        if abs(total_payment - transaction.total_amount) > Decimal('0.01'):
            return jsonify({'success': False, 'error': 'Сумма оплаты не совпадает с общей суммой'}), 400
        
        # Create payment records
        for payment_data in payments:
            payment = Payment(  # type: ignore
                transaction_id=transaction.id,
                method=PaymentMethod(payment_data['method']),
                amount=Decimal(str(payment_data['amount'])),
                reference_number=payment_data.get('reference_number')
            )
            db.session.add(payment)
        
        # Update stock quantities
        for item in transaction.items:
            item.product.stock_quantity -= int(item.quantity)
        
        # Handle promo code usage increment atomically if promo code was used
        if transaction.promo_code_used:
            promo = db.session.query(PromoCode).filter(
                func.upper(PromoCode.code) == transaction.promo_code_used.upper(),
                PromoCode.is_active == True
            ).with_for_update().first()
            
            if promo:
                # Final validation before incrementing usage
                if promo.max_uses and promo.current_uses >= promo.max_uses:
                    # This should not happen if validation was done correctly earlier
                    db.session.rollback()
                    return jsonify({'success': False, 'error': 'Промокод исчерпан на момент завершения транзакции'}), 400
                
                promo.current_uses += 1
        
        # Complete transaction
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.utcnow()
        transaction.user_id = current_user.id if current_user.is_authenticated else None
        
        db.session.commit()
        
        # Очищаем кеш популярных товаров после успешной продажи
        clear_popular_products_cache()
        
        # Log the completed sale
        log_operation(
            'sale_completed',
            f'Transaction {transaction.transaction_number} completed for ₸{transaction.total_amount}',
            'transaction',
            transaction.id,
            None,
            {
                'transaction_number': transaction.transaction_number,
                'total_amount': float(transaction.total_amount),
                'items_count': len(transaction.items),
                'payment_methods': [p['method'] for p in payments]
            }
        )
        
        # Log inventory updates
        for item in transaction.items:
            log_operation(
                'inventory_update',
                f'Stock reduced for {item.product.name}: -{int(item.quantity)} units',
                'product',
                item.product.id,
                {'stock_quantity': item.product.stock_quantity + int(item.quantity)},
                {'stock_quantity': item.product.stock_quantity}
            )
        
        # Clear current transaction from session
        session.pop('current_transaction_id', None)
        
        return jsonify({
            'success': True,
            'transaction_number': transaction.transaction_number,
            'total_amount': float(transaction.total_amount)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/transaction/suspend', methods=['POST'])
def suspend_transaction():
    """Suspend current transaction"""
    try:
        transaction_id = session.get('current_transaction_id')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'Нет активной транзакции'}), 400
        
        transaction = Transaction.query.get(transaction_id)
        if not transaction:
            return jsonify({'success': False, 'error': 'Транзакция не найдена'}), 400
        
        transaction.status = TransactionStatus.SUSPENDED
        db.session.commit()
        
        # Clear current transaction from session
        session.pop('current_transaction_id', None)
        
        return jsonify({
            'success': True,
            'message': f'Чек {transaction.transaction_number} отложен'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/suspended_transactions', methods=['GET'])
@login_required
def get_suspended_transactions():
    """Get list of suspended transactions for current user"""
    try:
        suspended_transactions = Transaction.query.filter_by(
            status=TransactionStatus.SUSPENDED,
            user_id=current_user.id
        ).order_by(Transaction.created_at.desc()).all()
        
        transactions_data = []
        for transaction in suspended_transactions:
            items_count = len(transaction.items)
            transactions_data.append({
                'id': transaction.id,
                'transaction_number': transaction.transaction_number,
                'created_at': transaction.created_at.strftime('%d.%m.%Y %H:%M'),
                'cashier_name': transaction.cashier_name or 'Кассир',
                'customer_name': transaction.customer_name or '',
                'total_amount': float(transaction.total_amount),
                'items_count': items_count
            })
        
        return jsonify({
            'success': True,
            'transactions': transactions_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/transaction/restore', methods=['POST'])
@login_required
def restore_transaction():
    """Restore suspended transaction"""
    try:
        data = request.get_json() or {}
        transaction_id = data.get('transaction_id')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'Не указан ID транзакции'}), 400
        
        # Check if there's already an active transaction
        current_transaction_id = session.get('current_transaction_id')
        if current_transaction_id:
            current_transaction = Transaction.query.get(current_transaction_id)
            if current_transaction and current_transaction.status == TransactionStatus.PENDING:
                return jsonify({
                    'success': False, 
                    'error': 'Завершите или отложите текущую транзакцию перед восстановлением'
                }), 400
        
        transaction = Transaction.query.filter_by(
            id=transaction_id,
            user_id=current_user.id
        ).first()
        if not transaction:
            return jsonify({'success': False, 'error': 'Транзакция не найдена или не принадлежит вам'}), 404
        
        if transaction.status != TransactionStatus.SUSPENDED:
            return jsonify({'success': False, 'error': 'Транзакция не отложена'}), 400
        
        # Restore transaction
        transaction.status = TransactionStatus.PENDING
        db.session.commit()
        
        # Set as current transaction
        session['current_transaction_id'] = transaction.id
        
        return jsonify({
            'success': True,
            'message': f'Чек {transaction.transaction_number} восстановлен',
            'transaction_id': transaction.id,
            'transaction_number': transaction.transaction_number
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/transaction/remove_item', methods=['POST'])
def remove_item_from_transaction():
    """Remove item from current transaction"""
    try:
        data = request.get_json() or {}
        transaction_id = session.get('current_transaction_id')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'Нет активной транзакции'}), 400
        
        item_id = data.get('item_id')
        if not item_id:
            return jsonify({'success': False, 'error': 'Не указан ID товара'}), 400
        
        item = TransactionItem.query.filter_by(
            id=item_id, 
            transaction_id=transaction_id
        ).first()
        
        if not item:
            return jsonify({'success': False, 'error': 'Товар не найден в корзине'}), 404
        
        transaction = item.transaction
        db.session.delete(item)
        
        # Update transaction totals
        update_transaction_totals(transaction)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'transaction_total': float(transaction.total_amount)
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/transaction/apply_discount', methods=['POST'])
def apply_discount():
    """Apply discount to current transaction"""
    try:
        data = request.get_json() or {}
        transaction_id = session.get('current_transaction_id')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'Нет активной транзакции'}), 400
        
        transaction = Transaction.query.get(transaction_id)
        if not transaction:
            return jsonify({'success': False, 'error': 'Транзакция не найдена'}), 400
        
        discount_type = data.get('type', 'percentage')  # percentage or fixed_amount
        discount_value = float(data.get('value', 0))
        
        if discount_type == 'percentage':
            discount_amount = transaction.subtotal * (discount_value / 100)
        else:
            discount_amount = discount_value
        
        # Ensure discount doesn't exceed subtotal
        discount_amount = min(discount_amount, transaction.subtotal)
        
        transaction.discount_amount = discount_amount
        update_transaction_totals(transaction)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'discount_amount': float(discount_amount),
            'total_amount': float(transaction.total_amount),
            'message': f'Скидка {discount_value}{"%" if discount_type == "percentage" else " ₽"} применена'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/transaction/apply_promo', methods=['POST'])
def apply_promo_to_transaction():
    """Apply promo code to current transaction with proper atomicity"""
    # Check if promo features are enabled
    if not current_app.config.get('PROMO_FEATURES_ENABLED', False):
        return jsonify({'success': False, 'error': 'Promo code features not available - database schema incompatible'}), 503
        
    if not current_app.config.get('PROMO_CODES_TABLE_EXISTS', False):
        return jsonify({'success': False, 'error': 'Promo codes table not available'}), 503
        
    try:
        data = request.get_json() or {}
        code = data.get('code', '').upper().strip()
        transaction_id = session.get('current_transaction_id')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'Нет активной транзакции'}), 400
        
        if not code:
            return jsonify({'success': False, 'error': 'Промокод не указан'}), 400
            
        # Use transaction for atomicity
        with db.session.begin():
            # Get and lock the transaction
            transaction = db.session.query(Transaction).filter_by(id=transaction_id).with_for_update().first()
            if not transaction or transaction.status != TransactionStatus.PENDING:
                return jsonify({'success': False, 'error': 'Транзакция недоступна'}), 400
            
            # Check if promo already applied
            if transaction.promo_code_used:
                return jsonify({'success': False, 'error': 'Промокод уже применен к этой транзакции'}), 400
            
            # Get and lock the promo code
            promo = db.session.query(PromoCode).filter(
                func.upper(PromoCode.code) == code,
                PromoCode.is_active == True
            ).with_for_update().first()
            
            if not promo:
                return jsonify({'success': False, 'error': 'Промокод не найден или не активен'}), 404
            
            now = datetime.utcnow()
            
            # Validate promo code constraints
            if promo.start_date and promo.start_date > now:
                return jsonify({'success': False, 'error': 'Промокод еще не активен'}), 400
            
            if promo.end_date and promo.end_date < now:
                return jsonify({'success': False, 'error': 'Промокод истек'}), 400
            
            if promo.max_uses and promo.current_uses >= promo.max_uses:
                return jsonify({'success': False, 'error': 'Промокод исчерпан'}), 400
            
            if transaction.subtotal < promo.min_amount:
                return jsonify({
                    'success': False, 
                    'error': f'Минимальная сумма для применения промокода: {float(promo.min_amount)} ₸'
                }), 400
            
            # Calculate discount
            if promo.discount_type == 'percentage':
                discount_amount = transaction.subtotal * (promo.discount_value / 100)
            else:
                discount_amount = promo.discount_value
            
            # Ensure discount doesn't exceed subtotal
            discount_amount = min(discount_amount, transaction.subtotal)
            
            # Apply discount to transaction
            transaction.discount_amount = discount_amount
            transaction.promo_code_used = code
            update_transaction_totals(transaction)
            
            # Note: Don't increment usage here - only on successful checkout
            
            return jsonify({
                'success': True,
                'promo_code': code,
                'discount_amount': float(discount_amount),
                'total_amount': float(transaction.total_amount),
                'message': f'Промокод "{code}" применен! Скидка: {float(promo.discount_value)}{"%" if promo.discount_type == "percentage" else " ₸"}'
            })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@pos_bp.route('/api/transaction/remove_promo', methods=['POST'])
def remove_promo_from_transaction():
    """Remove promo code from current transaction"""
    # Check if promo features are enabled
    if not current_app.config.get('PROMO_FEATURES_ENABLED', False):
        return jsonify({'success': False, 'error': 'Promo code features not available - database schema incompatible'}), 503
        
    try:
        transaction_id = session.get('current_transaction_id')
        
        if not transaction_id:
            return jsonify({'success': False, 'error': 'Нет активной транзакции'}), 400
            
        with db.session.begin():
            transaction = db.session.query(Transaction).filter_by(id=transaction_id).with_for_update().first()
            if not transaction or transaction.status != TransactionStatus.PENDING:
                return jsonify({'success': False, 'error': 'Транзакция недоступна'}), 400
            
            if not transaction.promo_code_used:
                return jsonify({'success': False, 'error': 'Промокод не применен'}), 400
            
            # Remove discount
            transaction.discount_amount = Decimal('0.00')
            transaction.promo_code_used = None
            update_transaction_totals(transaction)
            
            return jsonify({
                'success': True,
                'total_amount': float(transaction.total_amount),
                'message': 'Промокод удален'
            })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500