import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from config import Config
from werkzeug.middleware.proxy_fix import ProxyFix
from models import db, Product, Supplier, Category, Transaction, TransactionItem, Payment, PurchaseOrder, DiscountRule, PromoCode
from models import PaymentMethod, TransactionStatus, UnitType
from datetime import datetime, timedelta
from sqlalchemy import or_, desc, func, text, inspect
from decimal import Decimal
import secrets
import string

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Add ProxyFix for Replit environment
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Initialize extensions
    db.init_app(app)
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    with app.app_context():
        db.create_all()
        initialize_sample_data()
        
        # Check schema compatibility for promo code features
        check_promo_schema_compatibility(app)
    
    return app

def check_promo_schema_compatibility(app):
    """Check if database schema supports promo code features"""
    try:
        # Use proper schema inspection to check if promo_code_used column exists
        inspector = inspect(db.engine)
        transaction_columns = [col['name'] for col in inspector.get_columns('transactions')]
        
        if 'promo_code_used' in transaction_columns:
            app.config['PROMO_FEATURES_ENABLED'] = True
        else:
            print("WARNING: Promo code features disabled - promo_code_used column not found in transactions table")
            app.config['PROMO_FEATURES_ENABLED'] = False
            
    except Exception as e:
        print(f"WARNING: Promo code features disabled due to schema check error: {e}")
        app.config['PROMO_FEATURES_ENABLED'] = False
        
    try:
        # Check if promo_codes table exists
        inspector = inspect(db.engine)
        if inspector.has_table('promo_codes'):
            app.config['PROMO_CODES_TABLE_EXISTS'] = True
        else:
            print("WARNING: Promo codes table does not exist")
            app.config['PROMO_CODES_TABLE_EXISTS'] = False
    except Exception as e:
        print(f"WARNING: Could not check promo_codes table: {e}")
        app.config['PROMO_CODES_TABLE_EXISTS'] = False

def generate_transaction_number():
    """Generate unique transaction number"""
    timestamp = datetime.now().strftime('%Y%m%d')
    random_part = ''.join(secrets.choice(string.digits) for _ in range(4))
    return f"TXN{timestamp}{random_part}"

def generate_order_number():
    """Generate unique purchase order number"""
    timestamp = datetime.now().strftime('%Y%m%d')
    random_part = ''.join(secrets.choice(string.digits) for _ in range(4))
    return f"PO{timestamp}{random_part}"

def initialize_sample_data():
    """Initialize database with sample data if empty"""
    if Category.query.count() == 0:
        # Create categories for Kazakhstan market
        category1 = Category(name="Сүт өнімдері", description="Сүт, ірімшік, йогурт")
        category2 = Category(name="Нан өнімдері", description="Нан, тоқаш, печенье")
        category3 = Category(name="Сусындар", description="Шырын, газдалған сусындар, су")
        category4 = Category(name="Ет өнімдері", description="Ет, шұжық, деликатестер")
        category5 = Category(name="Жемістер мен көкөністер", description="Жаңа жемістер мен көкөністер")
        
        categories = [category1, category2, category3, category4, category5]
        
        for category in categories:
            db.session.add(category)
        
        # Create Kazakhstan supplier
        supplier = Supplier(
            name="ЖШС АлматыТрейд",
            contact_person="Асылбек Нұрболов", 
            phone="+7 (727) 250-30-40",
            email="orders@almatytrade.kz",
            address="Алматы қ., Абай д-лы, 120, 050000"
        )
        db.session.add(supplier)
        
        db.session.commit()
        
        # Create sample products for Kazakhstan market
        product1 = Product(sku="MLK001", name="Сүт 3.2% 1л", price=320.00, cost_price=220.00, 
                           stock_quantity=50, min_stock_level=10, unit_type=UnitType.PIECE,
                           supplier=supplier, category=categories[0])
        product2 = Product(sku="BRD001", name="Нан ақ", price=180.00, cost_price=120.00,
                           stock_quantity=30, min_stock_level=5, unit_type=UnitType.PIECE,
                           supplier=supplier, category=categories[1])
        product3 = Product(sku="JCE001", name="Апельсин шырыны 1л", price=580.00, cost_price=410.00,
                           stock_quantity=25, min_stock_level=8, unit_type=UnitType.PIECE,
                           supplier=supplier, category=categories[2])
        product4 = Product(sku="CHE001", name="Ірімшік қазақстандық", price=2200.00, cost_price=1560.00,
                           stock_quantity=15, min_stock_level=3, unit_type=UnitType.KILOGRAM,
                           supplier=supplier, category=categories[0])
        product5 = Product(sku="APL001", name="Алма қызыл", price=890.00, cost_price=590.00,
                           stock_quantity=40, min_stock_level=10, unit_type=UnitType.KILOGRAM,
                           supplier=supplier, category=categories[4])
        
        products = [product1, product2, product3, product4, product5]
        
        for product in products:
            db.session.add(product)
        
        db.session.commit()
        
        # Create sample promo codes for testing
        if PromoCode.query.count() == 0:
            promo1 = PromoCode(
                code="SAVE10", 
                name="10% скидка", 
                description="Скидка 10% на любую покупку",
                discount_type="percentage", 
                discount_value=10.00, 
                min_amount=500.00, 
                max_uses=100, 
                current_uses=0, 
                is_active=True
            )
            
            promo2 = PromoCode(
                code="NEWCUSTOMER", 
                name="Скидка новому клиенту", 
                description="200₸ скидка для новых клиентов",
                discount_type="fixed_amount", 
                discount_value=200.00, 
                min_amount=1000.00, 
                max_uses=50, 
                current_uses=0, 
                is_active=True
            )
            
            promo3 = PromoCode(
                code="WEEKEND", 
                name="Выходная скидка", 
                description="15% скидка на выходные",
                discount_type="percentage", 
                discount_value=15.00, 
                min_amount=300.00, 
                max_uses=None,  # Unlimited
                current_uses=0, 
                is_active=True,
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=30)
            )
            
            promos = [promo1, promo2, promo3]
            for promo in promos:
                db.session.add(promo)
            
            db.session.commit()

# Create the Flask app
app = create_app()

# Language support
def get_language():
    """Get current language from session"""
    return session.get('language', 'kk')  # Default to Kazakh

def get_text(kk_text, ru_text):
    """Get text based on current language"""
    if get_language() == 'ru':
        return ru_text
    return kk_text

# Translation dictionaries
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

def translate_name(original_name, category='products'):
    """Translate product/category name based on current language"""
    translations = TRANSLATIONS.get(category, {})
    if original_name in translations:
        return translations[original_name].get(get_language(), original_name)
    return original_name

# Language switcher route
@app.route('/set_language/<language>')
def set_language(language):
    """Set language preference"""
    if language in ['kk', 'ru']:
        session['language'] = language
    return redirect(request.referrer or url_for('index'))

# Make language functions available in templates
@app.context_processor
def inject_language_functions():
    return dict(get_language=get_language, get_text=get_text, translate_name=translate_name)

# Routes
@app.route('/')
def index():
    """Main dashboard"""
    # Get quick stats for dashboard
    total_products = Product.query.filter_by(is_active=True).count()
    low_stock_count = Product.query.filter(Product.stock_quantity <= Product.min_stock_level).count()
    
    # Today's sales
    today = datetime.now().date()
    today_sales = db.session.query(func.sum(Transaction.total_amount)).filter(
        func.date(Transaction.created_at) == today,
        Transaction.status == TransactionStatus.COMPLETED
    ).scalar() or 0
    
    # Recent transactions
    recent_transactions = Transaction.query.filter_by(status=TransactionStatus.COMPLETED)\
        .order_by(desc(Transaction.created_at)).limit(5).all()
    
    return render_template('dashboard.html', 
                         total_products=total_products,
                         low_stock_count=low_stock_count,
                         today_sales=today_sales,
                         recent_transactions=recent_transactions)

@app.route('/pos')
def pos():
    """POS Terminal Interface"""
    categories = Category.query.all()
    # Translate category names for current language
    for category in categories:
        category.translated_name = translate_name(category.name, 'categories')
    return render_template('pos.html', categories=categories)

@app.route('/api/products/search')
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

@app.route('/inventory')
def inventory():
    """Inventory management page"""
    search = request.args.get('search', '')
    category_id = request.args.get('category_id')
    low_stock = request.args.get('low_stock')
    
    query = Product.query.filter_by(is_active=True)
    
    if search:
        query = query.filter(
            or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%')
            )
        )
    
    if category_id:
        query = query.filter_by(category_id=category_id)
    
    if low_stock:
        query = query.filter(Product.stock_quantity <= Product.min_stock_level)
    
    products = query.order_by(Product.name).all()
    categories = Category.query.all()
    suppliers = Supplier.query.filter_by(is_active=True).all()
    
    # Translate names for current language
    for product in products:
        product.translated_name = translate_name(product.name, 'products')
        product.translated_unit = translate_name(product.unit_type.value, 'units')
    for category in categories:
        category.translated_name = translate_name(category.name, 'categories')
    
    return render_template('inventory.html', 
                         products=products, 
                         categories=categories,
                         suppliers=suppliers,
                         search=search,
                         selected_category=category_id,
                         show_low_stock=low_stock)

@app.route('/reports')
def reports():
    """Reports and analytics page"""
    # Date range filter
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    # Sales by day
    daily_sales = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.total_amount).label('total')
    ).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(func.date(Transaction.created_at)).all()
    
    # Top selling products
    top_products = db.session.query(
        Product.name,
        func.sum(TransactionItem.quantity).label('total_sold'),
        func.sum(TransactionItem.total_price).label('total_revenue')
    ).join(TransactionItem).join(Transaction).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(Product.id, Product.name).order_by(desc('total_sold')).limit(10).all()
    
    return render_template('reports.html',
                         daily_sales=daily_sales,
                         top_products=top_products,
                         start_date=start_date,
                         end_date=end_date)

# API Routes for POS functionality
@app.route('/api/transaction/start', methods=['POST'])
def start_transaction():
    """Start a new transaction"""
    try:
        data = request.get_json() or {}
        cashier_name = data.get('cashier_name', 'Кассир')
        customer_name = data.get('customer_name', '')
        
        transaction = Transaction(
            transaction_number=generate_transaction_number(),
            status=TransactionStatus.PENDING,
            cashier_name=cashier_name,
            customer_name=customer_name
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

@app.route('/api/transaction/add_item', methods=['POST'])
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
        item = TransactionItem(
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

@app.route('/api/transaction/current')
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

@app.route('/api/transaction/complete', methods=['POST'])
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
            payment = Payment(
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
        
        db.session.commit()
        
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

@app.route('/api/transaction/suspend', methods=['POST'])
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

@app.route('/api/transaction/remove_item', methods=['POST'])
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

# Inventory Management Routes
@app.route('/api/products', methods=['POST'])
def create_product():
    """Create new product"""
    try:
        data = request.get_json() or {}
        
        # Check if SKU already exists
        existing_product = Product.query.filter_by(sku=data['sku']).first()
        if existing_product:
            return jsonify({'success': False, 'error': 'Товар с таким артикулом уже существует'}), 400
        
        product = Product(
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
        
        return jsonify({
            'success': True,
            'product_id': product.id,
            'message': 'Товар успешно создан'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    """Update existing product"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json() or {}
        
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
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Товар успешно обновлен'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/products/<int:product_id>/stock', methods=['POST'])
def adjust_stock(product_id):
    """Adjust product stock level"""
    try:
        product = Product.query.get_or_404(product_id)
        data = request.get_json() or {}
        
        adjustment = int(data.get('adjustment', 0))
        reason = data.get('reason', 'Корректировка остатков')
        
        new_quantity = product.stock_quantity + adjustment
        if new_quantity < 0:
            return jsonify({'success': False, 'error': 'Остаток не может быть отрицательным'}), 400
        
        product.stock_quantity = new_quantity
        product.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'new_quantity': product.stock_quantity,
            'message': f'Остаток обновлен: {adjustment:+d} ({reason})'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/categories', methods=['POST'])
def create_category():
    """Create new category"""
    try:
        data = request.get_json() or {}
        
        category = Category(
            name=data['name'],
            description=data.get('description', '')
        )
        
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'category_id': category.id,
            'message': 'Категория успешно создана'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/suppliers', methods=['POST'])
def create_supplier():
    """Create new supplier"""
    try:
        data = request.get_json() or {}
        
        supplier = Supplier(
            name=data['name'],
            contact_person=data.get('contact_person', ''),
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            address=data.get('address', '')
        )
        
        db.session.add(supplier)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'supplier_id': supplier.id,
            'message': 'Поставщик успешно создан'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# Discount System Routes
@app.route('/api/transaction/apply_discount', methods=['POST'])
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

@app.route('/api/discount_rules')
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

@app.route('/api/promo_code/validate', methods=['POST'])
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

@app.route('/api/transaction/apply_promo', methods=['POST'])
def apply_promo_to_transaction():
    """Apply promo code to current transaction with proper atomicity"""
    # Check if promo features are enabled
    if not app.config.get('PROMO_FEATURES_ENABLED', False):
        return jsonify({'success': False, 'error': 'Прomo code features not available - database schema incompatible'}), 503
        
    if not app.config.get('PROMO_CODES_TABLE_EXISTS', False):
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

@app.route('/api/transaction/remove_promo', methods=['POST'])
def remove_promo_from_transaction():
    """Remove promo code from current transaction"""
    # Check if promo features are enabled
    if not app.config.get('PROMO_FEATURES_ENABLED', False):
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

# Analytics and Reports Routes
@app.route('/api/analytics/top_products')
def get_top_products():
    """Get top selling products analytics"""
    days = request.args.get('days', 30, type=int)
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Top products by quantity
    top_by_quantity = db.session.query(
        Product.name,
        Product.sku,
        func.sum(TransactionItem.quantity).label('total_sold'),
        func.sum(TransactionItem.total_price).label('total_revenue'),
        func.count(TransactionItem.id).label('transaction_count')
    ).join(TransactionItem).join(Transaction).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.created_at >= start_date
    ).group_by(Product.id, Product.name, Product.sku)\
     .order_by(desc('total_sold')).limit(10).all()
    
    # Low performing products
    low_performing = db.session.query(
        Product.name,
        Product.sku,
        func.sum(TransactionItem.quantity).label('total_sold'),
        func.sum(TransactionItem.total_price).label('total_revenue')
    ).join(TransactionItem).join(Transaction).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        Transaction.created_at >= start_date
    ).group_by(Product.id, Product.name, Product.sku)\
     .order_by('total_sold').limit(10).all()
    
    return jsonify({
        'top_products': [{
            'name': p.name,
            'sku': p.sku,
            'total_sold': float(p.total_sold),
            'total_revenue': float(p.total_revenue),
            'transaction_count': p.transaction_count
        } for p in top_by_quantity],
        'low_performing': [{
            'name': p.name,
            'sku': p.sku,
            'total_sold': float(p.total_sold),
            'total_revenue': float(p.total_revenue)
        } for p in low_performing]
    })

@app.route('/api/analytics/sales_summary')
def get_sales_summary():
    """Get sales summary for dashboard"""
    today = datetime.utcnow().date()
    start_of_month = today.replace(day=1)
    
    # Today's sales
    today_sales = db.session.query(
        func.sum(Transaction.total_amount),
        func.count(Transaction.id)
    ).filter(
        func.date(Transaction.created_at) == today,
        Transaction.status == TransactionStatus.COMPLETED
    ).first()
    
    # Month's sales
    month_sales = db.session.query(
        func.sum(Transaction.total_amount),
        func.count(Transaction.id)
    ).filter(
        func.date(Transaction.created_at) >= start_of_month,
        Transaction.status == TransactionStatus.COMPLETED
    ).first()
    
    # Low stock alerts
    low_stock_products = Product.query.filter(
        Product.stock_quantity <= Product.min_stock_level,
        Product.is_active == True
    ).count()
    
    return jsonify({
        'today': {
            'revenue': float(today_sales[0] if today_sales and today_sales[0] else 0),
            'transactions': today_sales[1] if today_sales and today_sales[1] else 0
        },
        'month': {
            'revenue': float(month_sales[0] if month_sales and month_sales[0] else 0),
            'transactions': month_sales[1] if month_sales and month_sales[1] else 0
        },
        'low_stock_count': low_stock_products
    })

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

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)