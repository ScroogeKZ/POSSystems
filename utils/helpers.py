"""
Helper utilities for POS system
"""
import os
import secrets
import string
import uuid
import imghdr
from datetime import datetime
from functools import wraps
from flask import session, request, flash, redirect, url_for, current_app
from flask_login import current_user
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps
from models import db, OperationLog, UserRole


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


def log_operation(action, description=None, entity_type=None, entity_id=None, old_values=None, new_values=None):
    """Log user operations"""
    if current_user.is_authenticated:
        log = OperationLog()
        log.user_id = current_user.id
        log.action = action
        log.description = description
        log.entity_type = entity_type
        log.entity_id = entity_id
        log.old_values = old_values
        log.new_values = new_values
        log.ip_address = request.remote_addr
        log.user_agent = request.user_agent.string
        
        db.session.add(log)
        db.session.commit()


def require_role(required_role):
    """Decorator to require specific user role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Жүйеге кіру қажет / Необходимо войти в систему', 'error')
                return redirect(url_for('login'))
            
            if not current_user.can_access(required_role):
                flash('Бұл әрекетке рұқсат жоқ / Недостаточно прав доступа', 'error')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator