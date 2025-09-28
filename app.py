import os
from flask import Flask, render_template, request, redirect, url_for, session
from config import Config
from werkzeug.middleware.proxy_fix import ProxyFix
from models import db, Product, Transaction, User, UserRole
from models import TransactionStatus
from flask_login import LoginManager, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from data_initialization import initialize_sample_data
from datetime import datetime
from sqlalchemy import desc, func, inspect


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
    
    # Initialize CSRF protection
    csrf = CSRFProtect()
    csrf.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Жүйеге кіру қажет / Необходимо войти в систему'
    login_manager.login_message_category = 'info'
    
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
    
    # Register blueprints
    from views.auth import auth_bp
    from views.pos import pos_bp
    from views.inventory import inventory_bp
    from views.reports import reports_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(reports_bp)
    
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

# Main dashboard route
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

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)