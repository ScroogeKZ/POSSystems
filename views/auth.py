"""
Authentication views for POS system
"""
import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, UserRole
from utils.helpers import log_operation, require_role

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')




@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
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
            return redirect(next_page) if next_page else redirect(url_for('main.index'))
        else:
            flash('Қате логин немесе құпия сөз / Неверный логин или пароль', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """User logout"""
    log_operation('logout', f'User logged out: {current_user.username}')
    logout_user()
    flash('Сіз жүйеден шықтыңыз / Вы вышли из системы', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register', methods=['GET', 'POST'])
@login_required
@require_role(UserRole.ADMIN)
def register():
    """Register new user (admin only)"""
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
        return redirect(url_for('auth.users'))
    
    return render_template('auth/register.html')


@auth_bp.route('/users')
@login_required
@require_role(UserRole.MANAGER)
def users():
    """List all users (manager and admin only)"""
    users = User.query.all()
    return render_template('auth/users.html', users=users)