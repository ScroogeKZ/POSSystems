import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from config import Config
from werkzeug.middleware.proxy_fix import ProxyFix
from models import db, Product, Supplier, Category, Transaction, TransactionItem, Payment, PurchaseOrder, DiscountRule, PromoCode, User, OperationLog
from models import PaymentMethod, TransactionStatus, UnitType, UserRole
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import json
from data_initialization import initialize_sample_data
from datetime import datetime, timedelta
from sqlalchemy import or_, desc, func, text, inspect
from decimal import Decimal
import secrets
import string
import io
import uuid
import pandas as pd
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from flask import send_file, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
import imghdr

def create_default_admin_user():
    """Create default admin user if none exists - requires ADMIN_PASSWORD env var"""
    admin_user = User.query.filter_by(role=UserRole.ADMIN).first()
    if not admin_user:
        # Require ADMIN_PASSWORD environment variable for security
        admin_password = os.environ.get('ADMIN_PASSWORD')
        if not admin_password:
            print("❌ SECURITY ERROR: ADMIN_PASSWORD environment variable is required to create admin user.")
            print("   Set ADMIN_PASSWORD environment variable with a secure password (min 8 chars, mixed case, numbers, symbols)")
            print("   Example: export ADMIN_PASSWORD='MySecureP@ssw0rd123'")
            raise RuntimeError("Admin user creation requires ADMIN_PASSWORD environment variable for security")
        
        # Validate password strength (same rules as user registration)
        if len(admin_password) < 8:
            print("❌ SECURITY ERROR: ADMIN_PASSWORD must be at least 8 characters long")
            raise RuntimeError("Admin password must be at least 8 characters for security")
        
        # Additional password complexity check (same as user registration)
        has_upper = any(c.isupper() for c in admin_password)
        has_lower = any(c.islower() for c in admin_password)
        has_digit = any(c.isdigit() for c in admin_password)
        
        if not (has_upper and has_lower and has_digit):
            print("❌ SECURITY ERROR: ADMIN_PASSWORD must contain uppercase letters, lowercase letters, and numbers")
            print("   Example: MySecureP@ssw0rd123")
            raise RuntimeError("Admin password must contain uppercase, lowercase, and numbers for security")
        
        admin = User()
        admin.username = 'admin'
        admin.email = 'admin@pos.kz'
        admin.first_name = 'Админ'
        admin.last_name = 'Жүйесі'
        admin.role = UserRole.ADMIN
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        
        print(f"✅ SECURE: Admin user created with password from ADMIN_PASSWORD environment variable")

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Add ProxyFix for Replit environment
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    
    # Initialize extensions
    db.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Жүйеге кіру қажет / Необходимо войти в систему'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    with app.app_context():
        db.create_all()
        initialize_sample_data()
        
        # Check schema compatibility for promo code features
        check_promo_schema_compatibility(app)
        
        # Initialize bcrypt for the app context
        from models import bcrypt
        bcrypt.init_app(app)
        
        # Create default admin user if none exists
        create_default_admin_user()
    
    # Authentication routes
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password) and user.is_active:
                login_user(user)
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                log_operation('login', f'User logged in: {user.username}')
                
                next_page = request.args.get('next')
                flash(f'Сәлем, {user.first_name}! / Добро пожаловать, {user.first_name}!', 'success')
                return redirect(next_page) if next_page else redirect(url_for('index'))
            else:
                flash('Қате логин немесе құпия сөз / Неверный логин или пароль', 'error')
        
        return render_template('auth/login.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        log_operation('logout', f'User logged out: {current_user.username}')
        logout_user()
        flash('Сіз жүйеден шықтыңыз / Вы вышли из системы', 'info')
        return redirect(url_for('login'))
    
    @app.route('/register', methods=['GET', 'POST'])
    @login_required
    @require_role(UserRole.ADMIN)
    def register():
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            role = request.form.get('role')
            
            # Validate password strength
            if not password or len(password) < 8:
                flash('Құпия сөз кемінде 8 таңбадан тұруы керек / Пароль должен содержать минимум 8 символов', 'error')
                return render_template('auth/register.html')
            
            # Additional password complexity check
            has_upper = any(c.isupper() for c in password)
            has_lower = any(c.islower() for c in password)
            has_digit = any(c.isdigit() for c in password)
            
            if not (has_upper and has_lower and has_digit):
                flash('Құпия сөзде үлкен әріп, кіші әріп және сан болуы керек / Пароль должен содержать заглавные буквы, строчные буквы и цифры', 'error')
                return render_template('auth/register.html')
            
            # Check if user already exists
            if User.query.filter_by(username=username).first():
                flash('Мұндай пайдаланушы бар / Пользователь уже существует', 'error')
                return render_template('auth/register.html')
            
            if User.query.filter_by(email=email).first():
                flash('Мұндай email бар / Email уже зарегистрирован', 'error')
                return render_template('auth/register.html')
            
            # Create new user
            new_user = User()
            new_user.username = username
            new_user.email = email
            new_user.first_name = first_name
            new_user.last_name = last_name
            new_user.role = UserRole(role)
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            log_operation('user_create', f'New user created: {username}', 'user', new_user.id)
            flash(f'Пайдаланушы құрылды / Пользователь {username} создан', 'success')
            return redirect(url_for('users'))
        
        return render_template('auth/register.html')
    
    @app.route('/users')
    @login_required
    @require_role(UserRole.MANAGER)
    def users():
        users = User.query.all()
        return render_template('auth/users.html', users=users)
    
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

def log_operation(action, description=None, entity_type=None, entity_id=None, old_values=None, new_values=None):
    """Log user operations for audit trail"""
    if current_user.is_authenticated:
        try:
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

def require_role(required_role):
    """Decorator to require specific user role"""
    def decorator(f):
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Жүйеге кіру қажет / Необходимо войти в систему', 'error')
                return redirect(url_for('login'))
            
            if not current_user.can_access(required_role):
                flash('Бұл әрекетке рұқсат жоқ / Недостаточно прав доступа', 'error')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

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
    return dict(get_language=get_language, get_text=get_text, translate_name=translate_name, UserRole=UserRole)

# Image processing functions
def allowed_file(filename):
    """Check if uploaded file has allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def validate_image(file):
    """Validate uploaded image file"""
    if not file or file.filename == '':
        return False, 'Файл не выбран'
    
    if not allowed_file(file.filename):
        return False, 'Недопустимый тип файла. Разрешены: PNG, JPG, JPEG, GIF'
    
    # Check file content type
    file.seek(0)
    header = file.read(512)
    file.seek(0)
    
    format = imghdr.what(None, header)
    if not format or format not in ['jpeg', 'png', 'gif']:
        return False, 'Файл не является изображением'
    
    return True, 'OK'

def generate_unique_filename(original_filename):
    """Generate unique filename for uploaded image (normalized to .jpg)"""
    unique_id = str(uuid.uuid4())[:8]
    secure_name = secure_filename(original_filename.rsplit('.', 1)[0])
    return f"{unique_id}_{secure_name}.jpg"

def process_product_image(file, filename):
    """Process uploaded product image - resize and create thumbnail (all saved as JPEG)"""
    try:
        # Open and process the image
        image = Image.open(file)
        
        # Convert RGBA to RGB if necessary
        if image.mode == 'RGBA':
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Auto-orient the image
        image = ImageOps.exif_transpose(image)
        
        # Resize main image if it's too large
        max_size = (app.config['MAX_IMAGE_WIDTH'], app.config['MAX_IMAGE_HEIGHT'])
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # Save main image as JPEG (filename already has .jpg extension)
        main_image_path = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
        os.makedirs(os.path.dirname(main_image_path), exist_ok=True)
        image.save(main_image_path, 'JPEG', quality=85, optimize=True)
        
        # Create and save thumbnail as JPEG
        thumbnail = image.copy()
        thumbnail.thumbnail(app.config['THUMBNAIL_SIZE'], Image.Resampling.LANCZOS)
        
        thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], 'products', 'thumbnails', filename)
        os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
        thumbnail.save(thumbnail_path, 'JPEG', quality=80, optimize=True)
        
        return True, filename
        
    except Exception as e:
        return False, f'Ошибка обработки изображения: {str(e)}'

def delete_product_image(filename):
    """Delete product image and thumbnail"""
    if not filename:
        return
    
    main_image_path = os.path.join(app.config['UPLOAD_FOLDER'], 'products', filename)
    thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], 'products', 'thumbnails', filename)
    
    # Delete main image
    if os.path.exists(main_image_path):
        try:
            os.remove(main_image_path)
        except OSError:
            pass
    
    # Delete thumbnail
    if os.path.exists(thumbnail_path):
        try:
            os.remove(thumbnail_path)
        except OSError:
            pass

# Routes
@app.route('/')
@login_required
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
@login_required
def pos():
    """POS Terminal Interface"""
    categories = Category.query.all()
    # Translate category names for current language
    for category in categories:
        category.translated_name = translate_name(category.name, 'categories')
    return render_template('pos.html', categories=categories)

@app.route('/api/products/search')
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

@app.route('/inventory')
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

@app.route('/reports')
@login_required
def reports():
    """Enhanced reports and analytics page"""
    # Date range filter
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    report_type = request.args.get('type', 'overview')  # overview, profit, categories, inventory
    
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    # Sales by day with profit calculation
    daily_sales = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.total_amount).label('total_revenue'),
        func.sum(
            TransactionItem.quantity * (Product.price - Product.cost_price)
        ).label('total_profit')
    ).select_from(Transaction).join(
        TransactionItem, Transaction.id == TransactionItem.transaction_id
    ).join(
        Product, TransactionItem.product_id == Product.id
    ).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(func.date(Transaction.created_at)).all()
    
    # Monthly aggregation for longer periods (database-agnostic using extract)
    monthly_sales = db.session.query(
        func.concat(
            func.extract('year', Transaction.created_at), 
            '-', 
            func.lpad(func.extract('month', Transaction.created_at).cast(db.String), 2, '0')
        ).label('month'),
        func.sum(Transaction.total_amount).label('total_revenue'),
        func.sum(
            TransactionItem.quantity * (Product.price - Product.cost_price)
        ).label('total_profit')
    ).select_from(Transaction).join(
        TransactionItem, Transaction.id == TransactionItem.transaction_id
    ).join(
        Product, TransactionItem.product_id == Product.id
    ).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(
        func.extract('year', Transaction.created_at),
        func.extract('month', Transaction.created_at)
    ).all()
    
    # Top selling products with profit
    top_products = db.session.query(
        Product.name,
        func.sum(TransactionItem.quantity).label('total_sold'),
        func.sum(TransactionItem.total_price).label('total_revenue'),
        func.sum(
            TransactionItem.quantity * (Product.price - Product.cost_price)
        ).label('total_profit'),
        func.avg(Product.price - Product.cost_price).label('avg_profit_per_unit')
    ).select_from(Product).join(
        TransactionItem, Product.id == TransactionItem.product_id
    ).join(
        Transaction, TransactionItem.transaction_id == Transaction.id
    ).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(Product.id, Product.name).order_by(desc('total_sold')).limit(10).all()
    
    # Category analysis - most popular categories
    category_analysis = db.session.query(
        Category.name,
        func.count(TransactionItem.id).label('total_transactions'),
        func.sum(TransactionItem.quantity).label('total_sold'),
        func.sum(TransactionItem.total_price).label('total_revenue'),
        func.sum(
            TransactionItem.quantity * (Product.price - Product.cost_price)
        ).label('total_profit')
    ).select_from(Category).join(
        Product, Category.id == Product.category_id
    ).join(
        TransactionItem, Product.id == TransactionItem.product_id
    ).join(
        Transaction, TransactionItem.transaction_id == Transaction.id
    ).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(Category.id, Category.name).order_by(desc('total_revenue')).all()
    
    # Inventory analysis
    inventory_report = db.session.query(
        Product.name,
        Product.sku,
        Product.stock_quantity,
        Product.min_stock_level,
        Product.price,
        Product.cost_price,
        Category.name.label('category_name'),
        Supplier.name.label('supplier_name')
    ).select_from(Product).join(
        Category, Product.category_id == Category.id
    ).join(
        Supplier, Product.supplier_id == Supplier.id
    ).filter(
        Product.is_active == True
    ).order_by(Product.stock_quantity.asc()).all()
    
    # Convert Row objects to dictionaries for JSON serialization
    daily_sales = [{
        'date': str(row.date),
        'total_revenue': float(row.total_revenue or 0),
        'total_profit': float(row.total_profit or 0)
    } for row in daily_sales]
    
    monthly_sales = [{
        'month': str(row.month),
        'total_revenue': float(row.total_revenue or 0),
        'total_profit': float(row.total_profit or 0)
    } for row in monthly_sales]
    
    top_products = [{
        'name': row.name,
        'total_sold': float(row.total_sold or 0),
        'total_revenue': float(row.total_revenue or 0),
        'total_profit': float(row.total_profit or 0),
        'avg_profit_per_unit': float(row.avg_profit_per_unit or 0)
    } for row in top_products]
    
    category_analysis = [{
        'name': row.name,
        'total_transactions': int(row.total_transactions or 0),
        'total_sold': float(row.total_sold or 0),
        'total_revenue': float(row.total_revenue or 0),
        'total_profit': float(row.total_profit or 0)
    } for row in category_analysis]
    
    inventory_report = [{
        'name': row.name,
        'sku': row.sku,
        'stock_quantity': int(row.stock_quantity or 0),
        'min_stock_level': int(row.min_stock_level or 0),
        'price': float(row.price or 0),
        'cost_price': float(row.cost_price or 0),
        'category_name': row.category_name,
        'supplier_name': row.supplier_name
    } for row in inventory_report]
    
    # Low stock items
    low_stock_items = [item for item in inventory_report if item['stock_quantity'] <= item['min_stock_level']]
    
    # Calculate key metrics
    total_revenue = sum(sale['total_revenue'] or 0 for sale in daily_sales)
    total_profit = sum(sale['total_profit'] or 0 for sale in daily_sales)
    profit_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
    
    return render_template('reports.html',
                         daily_sales=daily_sales,
                         monthly_sales=monthly_sales,
                         top_products=top_products,
                         category_analysis=category_analysis,
                         inventory_report=inventory_report,
                         low_stock_items=low_stock_items,
                         total_revenue=total_revenue,
                         total_profit=total_profit,
                         profit_margin=profit_margin,
                         start_date=start_date,
                         end_date=end_date,
                         report_type=report_type)

@app.route('/export/pdf')
@login_required
def export_pdf():
    """Export reports as PDF"""
    try:
        # Get the same data as reports route
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        # Get analytics data
        daily_sales, category_analysis, top_products, inventory_report = get_reports_data(start_date, end_date)
        
        # Create PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center
        )
        story.append(Paragraph(f'POS System Analytics Report', title_style))
        story.append(Paragraph(f'Period: {start_date} to {end_date}', styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Daily Sales Table
        if daily_sales:
            story.append(Paragraph('Daily Sales and Profit', styles['Heading2']))
            sales_data = [['Date', 'Revenue (₸)', 'Profit (₸)']]
            for sale in daily_sales:
                sales_data.append([
                    str(sale.date),
                    f"{sale.total_revenue or 0:.2f}",
                    f"{sale.total_profit or 0:.2f}"
                ])
            
            sales_table = Table(sales_data)
            sales_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(sales_table)
            story.append(Spacer(1, 20))
        
        # Top Products Table
        if top_products:
            story.append(Paragraph('Top Selling Products', styles['Heading2']))
            products_data = [['Product', 'Sold', 'Revenue (₸)', 'Profit (₸)']]
            for product in top_products:
                products_data.append([
                    product.name,
                    f"{product.total_sold:.0f}",
                    f"{product.total_revenue:.2f}",
                    f"{product.total_profit or 0:.2f}"
                ])
            
            products_table = Table(products_data)
            products_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(products_table)
            story.append(Spacer(1, 20))
        
        # Category Analysis Table
        if category_analysis:
            story.append(Paragraph('Category Analysis', styles['Heading2']))
            category_data = [['Category', 'Transactions', 'Revenue (₸)', 'Profit (₸)']]
            for category in category_analysis:
                category_data.append([
                    category.name,
                    str(category.total_transactions),
                    f"{category.total_revenue:.2f}",
                    f"{category.total_profit or 0:.2f}"
                ])
            
            category_table = Table(category_data)
            category_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(category_table)
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'pos_report_{start_date}_{end_date}.pdf',
            mimetype='application/pdf'
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/export/excel')
@login_required
def export_excel():
    """Export reports as Excel"""
    try:
        # Get the same data as reports route
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date:
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        # Get analytics data
        daily_sales, category_analysis, top_products, inventory_report = get_reports_data(start_date, end_date)
        
        # Create Excel file
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Daily Sales Sheet
            if daily_sales:
                sales_df = pd.DataFrame([
                    {
                        'Date': sale.date,
                        'Revenue (₸)': sale.total_revenue or 0,
                        'Profit (₸)': sale.total_profit or 0
                    } for sale in daily_sales
                ])
                sales_df.to_excel(writer, sheet_name='Daily Sales', index=False)
            
            # Top Products Sheet
            if top_products:
                products_df = pd.DataFrame([
                    {
                        'Product': product.name,
                        'Quantity Sold': product.total_sold,
                        'Revenue (₸)': product.total_revenue,
                        'Profit (₸)': product.total_profit or 0,
                        'Avg Profit per Unit (₸)': product.avg_profit_per_unit or 0
                    } for product in top_products
                ])
                products_df.to_excel(writer, sheet_name='Top Products', index=False)
            
            # Category Analysis Sheet
            if category_analysis:
                categories_df = pd.DataFrame([
                    {
                        'Category': category.name,
                        'Total Transactions': category.total_transactions,
                        'Total Sold': category.total_sold,
                        'Revenue (₸)': category.total_revenue,
                        'Profit (₸)': category.total_profit or 0,
                        'Profit Margin (%)': (category.total_profit / category.total_revenue * 100) if category.total_revenue > 0 else 0
                    } for category in category_analysis
                ])
                categories_df.to_excel(writer, sheet_name='Category Analysis', index=False)
            
            # Inventory Report Sheet
            if inventory_report:
                inventory_df = pd.DataFrame([
                    {
                        'Product': item.name,
                        'SKU': item.sku,
                        'Stock Quantity': item.stock_quantity,
                        'Min Stock Level': item.min_stock_level,
                        'Price (₸)': item.price,
                        'Cost Price (₸)': item.cost_price,
                        'Profit per Unit (₸)': item.price - item.cost_price,
                        'Category': item.category_name,
                        'Supplier': item.supplier_name,
                        'Status': 'Low Stock' if item.stock_quantity <= item.min_stock_level else 'OK'
                    } for item in inventory_report
                ])
                inventory_df.to_excel(writer, sheet_name='Inventory Report', index=False)
        
        buffer.seek(0)
        
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f'pos_report_{start_date}_{end_date}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def get_reports_data(start_date, end_date):
    """Helper function to get reports data"""
    # Sales by day with profit calculation
    daily_sales = db.session.query(
        func.date(Transaction.created_at).label('date'),
        func.sum(Transaction.total_amount).label('total_revenue'),
        func.sum(
            TransactionItem.quantity * (Product.price - Product.cost_price)
        ).label('total_profit')
    ).select_from(Transaction).join(
        TransactionItem, Transaction.id == TransactionItem.transaction_id
    ).join(
        Product, TransactionItem.product_id == Product.id
    ).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(func.date(Transaction.created_at)).all()
    
    # Top selling products with profit
    top_products = db.session.query(
        Product.name,
        func.sum(TransactionItem.quantity).label('total_sold'),
        func.sum(TransactionItem.total_price).label('total_revenue'),
        func.sum(
            TransactionItem.quantity * (Product.price - Product.cost_price)
        ).label('total_profit'),
        func.avg(Product.price - Product.cost_price).label('avg_profit_per_unit')
    ).select_from(Product).join(
        TransactionItem, Product.id == TransactionItem.product_id
    ).join(
        Transaction, TransactionItem.transaction_id == Transaction.id
    ).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(Product.id, Product.name).order_by(desc('total_sold')).limit(10).all()
    
    # Category analysis - most popular categories
    category_analysis = db.session.query(
        Category.name,
        func.count(TransactionItem.id).label('total_transactions'),
        func.sum(TransactionItem.quantity).label('total_sold'),
        func.sum(TransactionItem.total_price).label('total_revenue'),
        func.sum(
            TransactionItem.quantity * (Product.price - Product.cost_price)
        ).label('total_profit')
    ).select_from(Category).join(
        Product, Category.id == Product.category_id
    ).join(
        TransactionItem, Product.id == TransactionItem.product_id
    ).join(
        Transaction, TransactionItem.transaction_id == Transaction.id
    ).filter(
        Transaction.status == TransactionStatus.COMPLETED,
        func.date(Transaction.created_at) >= start_date,
        func.date(Transaction.created_at) <= end_date
    ).group_by(Category.id, Category.name).order_by(desc('total_revenue')).all()
    
    # Inventory analysis
    inventory_report = db.session.query(
        Product.name,
        Product.sku,
        Product.stock_quantity,
        Product.min_stock_level,
        Product.price,
        Product.cost_price,
        Category.name.label('category_name'),
        Supplier.name.label('supplier_name')
    ).select_from(Product).join(
        Category, Product.category_id == Category.id
    ).join(
        Supplier, Product.supplier_id == Supplier.id
    ).filter(
        Product.is_active == True
    ).order_by(Product.stock_quantity.asc()).all()
    
    # Convert Row objects to dictionaries for JSON serialization
    daily_sales_data = [{
        'date': str(row.date),
        'total_revenue': float(row.total_revenue or 0),
        'total_profit': float(row.total_profit or 0)
    } for row in daily_sales]
    
    category_analysis_data = [{
        'name': row.name,
        'total_transactions': int(row.total_transactions or 0),
        'total_sold': float(row.total_sold or 0),
        'total_revenue': float(row.total_revenue or 0),
        'total_profit': float(row.total_profit or 0)
    } for row in category_analysis]
    
    top_products_data = [{
        'name': row.name,
        'total_sold': float(row.total_sold or 0),
        'total_revenue': float(row.total_revenue or 0),
        'total_profit': float(row.total_profit or 0),
        'avg_profit_per_unit': float(row.avg_profit_per_unit or 0)
    } for row in top_products]
    
    inventory_report_data = [{
        'name': row.name,
        'sku': row.sku,
        'stock_quantity': int(row.stock_quantity or 0),
        'min_stock_level': int(row.min_stock_level or 0),
        'price': float(row.price or 0),
        'cost_price': float(row.cost_price or 0),
        'category_name': row.category_name,
        'supplier_name': row.supplier_name
    } for row in inventory_report]
    
    return daily_sales_data, category_analysis_data, top_products_data, inventory_report_data

# API Routes for POS functionality
@app.route('/api/transaction/start', methods=['POST'])
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

@app.route('/api/transaction/current')
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

@app.route('/api/suspended_transactions', methods=['GET'])
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

@app.route('/api/transaction/restore', methods=['POST'])
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

@app.route('/api/products/<int:product_id>/upload-image', methods=['POST'])
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

@app.route('/api/products/<int:product_id>/delete-image', methods=['DELETE'])
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
        
        category = Category(  # type: ignore
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
        
        supplier = Supplier(  # type: ignore
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