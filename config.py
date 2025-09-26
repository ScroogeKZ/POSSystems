import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SESSION_SECRET')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///pos_system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # POS specific settings for Kazakhstan
    CURRENCY_SYMBOL = '₸'
    TAX_RATE = 0.12  # 12% VAT (Kazakhstan standard rate)
    RECEIPT_FOOTER = 'Рахмет сатып алғаныңыз үшін! / Спасибо за покупку!'
    COUNTRY_CODE = 'KZ'
    PHONE_FORMAT = '+7 (XXX) XXX-XX-XX'
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)