"""
Inventory management views for POS system
"""
import os
import json
from datetime import datetime
from decimal import Decimal
from flask import Blueprint, render_template, request, jsonify, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_
from models import db, Product, Supplier, Category, DiscountRule, PromoCode, Transaction, UnitType, UserRole
from utils.image_processing import allowed_file, validate_image, generate_unique_filename, process_product_image, delete_product_image


# Create the blueprint
inventory_bp = Blueprint('inventory', __name__)


def require_role(required_role):
    """Decorator to require specific user role"""
    def decorator(f):
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'success': False, 'error': 'Жүйеге кіру қажет / Необходимо войти в систему'}), 401
            
            if not current_user.can_access(required_role):
                return jsonify({'success': False, 'error': 'Бұл әрекетке рұқсат жоқ / Недостаточно прав доступа'}), 403
            
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator


def log_operation(action, description=None, entity_type=None, entity_id=None, old_values=None, new_values=None):
    """Log user operations for audit trail"""
    if current_user.is_authenticated:
        try:
            from models import OperationLog
            log_entry = OperationLog()
            log_entry.action = action
            log_entry.description = description
            log_entry.entity_type = entity_type
            log_entry.entity_id = entity_id
            log_entry.old_values = json.dumps(old_values) if old_values else None
            log_entry.new_values = json.dumps(new_values) if new_values else None
            log_entry.ip_address = request.remote_addr
            log_entry.user_agent = request.headers.get('User-Agent')
            log_entry.user_id = current_user.id
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            print(f"Failed to log operation: {e}")


def get_language():
    """Get current language from session"""
    return session.get('language', 'kk')  # Default to Kazakh


def translate_name(original_name, category='products'):
    """Translate product/category name based on current language"""
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
    
    translations = TRANSLATIONS.get(category, {})
    if original_name in translations:
        return translations[original_name].get(get_language(), original_name)
    return original_name


# Main inventory management page
@inventory_bp.route('/inventory')
@login_required
def inventory():
    """Inventory management page with advanced filters"""
    search = request.args.get('search', '')
    category_id = request.args.get('category_id')
    price_range = request.args.get('price_range', '')
    stock_filter = request.args.get('stock_filter', '')
    
    query = Product.query.filter_by(is_active=True)
    
    # Text search filter
    if search:
        query = query.filter(
            or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%')
            )
        )
    
    # Category filter
    if category_id:
        query = query.filter_by(category_id=category_id)
    
    # Price range filter
    if price_range:
        if price_range == '0-500':
            query = query.filter(Product.price.between(0, 500))
        elif price_range == '500-1000':
            query = query.filter(Product.price.between(500, 1000))
        elif price_range == '1000-2000':
            query = query.filter(Product.price.between(1000, 2000))
        elif price_range == '2000+':
            query = query.filter(Product.price >= 2000)
    
    # Stock filter
    if stock_filter:
        if stock_filter == 'low':
            query = query.filter(Product.stock_quantity <= Product.min_stock_level)
        elif stock_filter == 'zero':
            query = query.filter(Product.stock_quantity == 0)
        elif stock_filter == 'available':
            query = query.filter(Product.stock_quantity > 0)
    
    # Order by stock status (critical first), then by name
    products = query.order_by(
        db.case(
            (Product.stock_quantity == 0, 0),
            (Product.stock_quantity <= Product.min_stock_level, 1),
            else_=2
        ),
        Product.name
    ).all()
    
    categories = Category.query.order_by(Category.name).all()
    suppliers = Supplier.query.filter_by(is_active=True).order_by(Supplier.name).all()
    
    # Translate names for current language
    for product in products:
        product.translated_name = translate_name(product.name, 'products')
        product.translated_unit = translate_name(product.unit_type.value, 'units')
    for category in categories:
        category.translated_name = translate_name(category.name, 'categories')
    
    # Legacy support for show_low_stock parameter
    show_low_stock = stock_filter == 'low' or request.args.get('low_stock')
    
    return render_template('inventory.html', 
                         products=products, 
                         categories=categories,
                         suppliers=suppliers,
                         search=search,
                         selected_category=category_id,
                         show_low_stock=show_low_stock,
                         price_range=price_range,
                         stock_filter=stock_filter)


# Product management API endpoints
@inventory_bp.route('/api/products', methods=['POST'])
@login_required
@require_role(UserRole.MANAGER)
def create_product():
    """Create new product"""
    try:
        data = request.get_json() or {}
        
        # Check if SKU already exists
        existing_product = Product.query.filter_by(sku=data['sku']).first()
        if existing_product:
            return jsonify({'success': False, 'error': 'Товар с таким артикулом уже существует'}), 400
        
        product = Product(  # type: ignore
            sku=data['sku'],
            name=data['name'],
            description=data.get('description', ''),
            unit_type=UnitType(data.get('unit_type', 'шт.')),
            price=Decimal(str(data['price'])),
            cost_price=Decimal(str(data.get('cost_price', 0))),
            stock_quantity=int(data.get('stock_quantity', 0)),
            min_stock_level=int(data.get('min_stock_level', 0)),
            supplier_id=data.get('supplier_id'),
            category_id=data.get('category_id')
        )
        
        db.session.add(product)
        db.session.commit()
        
        log_operation('product_create', f'Product created: {product.name}', 'product', product.id)
        
        return jsonify({
            'success': True,
            'product_id': product.id,
            'message': 'Товар успешно создан'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/api/products/<int:product_id>', methods=['PUT'])
@login_required
@require_role(UserRole.MANAGER)
def update_product(product_id):
    """Update existing product"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json() or {}
        
        # Store old values for logging
        old_values = {
            'sku': product.sku,
            'name': product.name,
            'price': float(product.price),
            'stock_quantity': product.stock_quantity
        }
        
        # Check SKU uniqueness if changed
        if data.get('sku') and data['sku'] != product.sku:
            existing = Product.query.filter_by(sku=data['sku']).first()
            if existing:
                return jsonify({'success': False, 'error': 'Товар с таким артикулом уже существует'}), 400
        
        # Update product fields
        if 'sku' in data:
            product.sku = data['sku']
        if 'name' in data:
            product.name = data['name']
        if 'description' in data:
            product.description = data['description']
        if 'unit_type' in data:
            product.unit_type = UnitType(data['unit_type'])
        if 'price' in data:
            product.price = Decimal(str(data['price']))
        if 'cost_price' in data:
            product.cost_price = Decimal(str(data['cost_price']))
        if 'stock_quantity' in data:
            product.stock_quantity = int(data['stock_quantity'])
        if 'min_stock_level' in data:
            product.min_stock_level = int(data['min_stock_level'])
        if 'supplier_id' in data:
            product.supplier_id = data['supplier_id']
        if 'category_id' in data:
            product.category_id = data['category_id']
        
        product.updated_at = datetime.utcnow()
        
        # New values for logging
        new_values = {
            'sku': product.sku,
            'name': product.name,
            'price': float(product.price),
            'stock_quantity': product.stock_quantity
        }
        
        db.session.commit()
        
        log_operation('product_update', f'Product updated: {product.name}', 'product', product.id, old_values, new_values)
        
        return jsonify({
            'success': True,
            'message': 'Товар успешно обновлен'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/api/products/<int:product_id>/stock', methods=['POST'])
@login_required
@require_role(UserRole.MANAGER)
def adjust_stock(product_id):
    """Adjust product stock level"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json() or {}
        
        adjustment = int(data.get('adjustment', 0))
        reason = data.get('reason', 'Корректировка остатков')
        
        old_quantity = product.stock_quantity
        new_quantity = product.stock_quantity + adjustment
        if new_quantity < 0:
            return jsonify({'success': False, 'error': 'Остаток не может быть отрицательным'}), 400
        
        product.stock_quantity = new_quantity
        product.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        log_operation('stock_adjustment', f'Stock adjusted for {product.name}: {old_quantity} -> {new_quantity} ({reason})', 'product', product.id)
        
        return jsonify({
            'success': True,
            'new_quantity': product.stock_quantity,
            'message': f'Остаток обновлен: {adjustment:+d} ({reason})'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# Image management API endpoints
@inventory_bp.route('/api/products/<int:product_id>/upload-image', methods=['POST'])
@login_required
@require_role(UserRole.MANAGER)
def upload_product_image(product_id):
    """Upload image for product"""
    try:
        product = Product.query.get_or_404(product_id)
        
        # Check if file was uploaded
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'Файл не выбран'}), 400
            
        file = request.files['image']
        
        # Validate the uploaded file
        is_valid, message = validate_image(file)
        if not is_valid:
            return jsonify({'success': False, 'error': message}), 400
        
        # Generate unique filename
        filename = generate_unique_filename(file.filename)
        
        # Delete old image if exists
        if product.image_filename:
            delete_product_image(product.image_filename)
        
        # Process and save the new image
        success, result = process_product_image(file, filename)
        if not success:
            return jsonify({'success': False, 'error': result}), 500
        
        # Update product record
        product.image_filename = filename
        product.updated_at = datetime.utcnow()
        db.session.commit()
        
        log_operation('product_image_upload', f'Image uploaded for product: {product.name}', 'product', product.id)
        
        return jsonify({
            'success': True,
            'message': 'Изображение успешно загружено',
            'image_filename': filename,
            'image_url': f'/static/images/products/{filename}',
            'thumbnail_url': f'/static/images/products/thumbnails/{filename}'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/api/products/<int:product_id>/delete-image', methods=['DELETE'])
@login_required
@require_role(UserRole.MANAGER)
def delete_product_image_api(product_id):
    """Delete product image"""
    try:
        product = Product.query.get_or_404(product_id)
        
        if not product.image_filename:
            return jsonify({'success': False, 'error': 'У товара нет изображения'}), 400
        
        # Delete image files
        delete_product_image(product.image_filename)
        
        # Update product record
        old_filename = product.image_filename
        product.image_filename = None
        product.updated_at = datetime.utcnow()
        db.session.commit()
        
        log_operation('product_image_delete', f'Image deleted for product: {product.name}', 'product', product.id)
        
        return jsonify({
            'success': True,
            'message': 'Изображение успешно удалено'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# Category and supplier management API endpoints
@inventory_bp.route('/api/categories', methods=['POST'])
@login_required
@require_role(UserRole.MANAGER)
def create_category():
    """Create new category"""
    try:
        data = request.get_json() or {}
        
        # Check if category already exists
        existing_category = Category.query.filter_by(name=data['name']).first()
        if existing_category:
            return jsonify({'success': False, 'error': 'Категория с таким названием уже существует'}), 400
        
        category = Category(  # type: ignore
            name=data['name'],
            description=data.get('description', '')
        )
        
        db.session.add(category)
        db.session.commit()
        
        log_operation('category_create', f'Category created: {category.name}', 'category', category.id)
        
        return jsonify({
            'success': True,
            'category_id': category.id,
            'message': 'Категория успешно создана'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@inventory_bp.route('/api/suppliers', methods=['POST'])
@login_required
@require_role(UserRole.MANAGER)
def create_supplier():
    """Create new supplier"""
    try:
        data = request.get_json() or {}
        
        # Check if supplier already exists
        existing_supplier = Supplier.query.filter_by(name=data['name']).first()
        if existing_supplier:
            return jsonify({'success': False, 'error': 'Поставщик с таким названием уже существует'}), 400
        
        supplier = Supplier(  # type: ignore
            name=data['name'],
            contact_person=data.get('contact_person', ''),
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            address=data.get('address', '')
        )
        
        db.session.add(supplier)
        db.session.commit()
        
        log_operation('supplier_create', f'Supplier created: {supplier.name}', 'supplier', supplier.id)
        
        return jsonify({
            'success': True,
            'supplier_id': supplier.id,
            'message': 'Поставщик успешно создан'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# Discount and promo code API endpoints
@inventory_bp.route('/api/discount_rules')
@login_required
def get_discount_rules():
    """Get active discount rules"""
    now = datetime.utcnow()
    rules = DiscountRule.query.filter(
        DiscountRule.is_active == True,
        or_(
            DiscountRule.start_date.is_(None),
            DiscountRule.start_date <= now
        ),
        or_(
            DiscountRule.end_date.is_(None),
            DiscountRule.end_date >= now
        )
    ).all()
    
    return jsonify([{
        'id': rule.id,
        'name': rule.name,
        'description': rule.description,
        'discount_type': rule.discount_type,
        'discount_value': float(rule.discount_value),
        'min_amount': float(rule.min_amount),
        'category_name': rule.category.name if rule.category else None
    } for rule in rules])


@inventory_bp.route('/api/promo_code/validate', methods=['POST'])
@login_required
def validate_promo_code():
    """Validate promo code"""
    try:
        data = request.get_json() or {}
        code = data.get('code', '').upper().strip()
        
        if not code:
            return jsonify({'success': False, 'error': 'Промокод не указан'}), 400
        
        # Find promo code
        promo = PromoCode.query.filter_by(code=code, is_active=True).first()
        if not promo:
            return jsonify({'success': False, 'error': 'Промокод не найден или не активен'}), 404
        
        now = datetime.utcnow()
        
        # Check date validity
        if promo.start_date and promo.start_date > now:
            return jsonify({'success': False, 'error': 'Промокод еще не активен'}), 400
        
        if promo.end_date and promo.end_date < now:
            return jsonify({'success': False, 'error': 'Промокод истек'}), 400
        
        # Check usage limit
        if promo.max_uses and promo.current_uses >= promo.max_uses:
            return jsonify({'success': False, 'error': 'Промокод исчерпан'}), 400
        
        # Check minimum amount (if transaction exists)
        transaction_id = session.get('current_transaction_id')
        if transaction_id:
            transaction = Transaction.query.get(transaction_id)
            if transaction and transaction.subtotal < promo.min_amount:
                return jsonify({
                    'success': False, 
                    'error': f'Минимальная сумма для применения промокода: {float(promo.min_amount)} ₸'
                }), 400
        
        return jsonify({
            'success': True,
            'promo_code': {
                'id': promo.id,
                'code': promo.code,
                'name': promo.name,
                'description': promo.description,
                'discount_type': promo.discount_type,
                'discount_value': float(promo.discount_value),
                'min_amount': float(promo.min_amount)
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500