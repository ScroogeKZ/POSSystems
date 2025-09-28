import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SESSION_SECRET')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEBUG = os.environ.get('FLASK_ENV') != 'production'
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Image upload settings
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_IMAGE_WIDTH = 800
    MAX_IMAGE_HEIGHT = 600
    THUMBNAIL_SIZE = (200, 200)  # For POS display
    
    # POS specific settings for Kazakhstan
    CURRENCY_SYMBOL = '₸'
    TAX_RATE = 0.12  # 12% VAT (Kazakhstan standard rate)
    RECEIPT_FOOTER = 'Рахмет сатып алғаныңыз үшін! / Спасибо за покупку!'
    COUNTRY_CODE = 'KZ'
    PHONE_FORMAT = '+7 (XXX) XXX-XX-XX'
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Security settings for cookies
    SESSION_COOKIE_SECURE = os.environ.get('FLASK_ENV') == 'production'  # Only HTTPS in production
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookies
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection
    
    # CSRF settings
    WTF_CSRF_TIME_LIMIT = 3600  # CSRF token expires in 1 hour (3600 seconds)
    WTF_CSRF_SSL_STRICT = os.environ.get('FLASK_ENV') == 'production'  # Force HTTPS only in production
    
    # Redis caching settings
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = REDIS_URL
    CACHE_DEFAULT_TIMEOUT = 300