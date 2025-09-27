from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from flask_bcrypt import Bcrypt
from datetime import datetime
from enum import Enum
from sqlalchemy import func

db = SQLAlchemy()
bcrypt = Bcrypt()

class UserRole(Enum):
    CASHIER = "cashier"
    MANAGER = "manager"
    ADMIN = "admin"

class PaymentMethod(Enum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"

class TransactionStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"

class UnitType(Enum):
    PIECE = "шт."
    KILOGRAM = "кг."
    LITER = "л."
    METER = "м."
    PACK = "упак."

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.Enum(UserRole), default=UserRole.CASHIER)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='user', lazy=True, foreign_keys='Transaction.user_id')
    operation_logs = db.relationship('OperationLog', backref='user', lazy=True, foreign_keys='OperationLog.user_id')
    
    def set_password(self, password):
        """Set password hash using bcrypt"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """Check password against hash"""
        return bcrypt.check_password_hash(self.password_hash, password)
    
    @property
    def full_name(self):
        """Get user's full name"""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def is_cashier(self):
        return self.role == UserRole.CASHIER
    
    @property
    def is_manager(self):
        return self.role == UserRole.MANAGER
    
    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN
    
    def can_access(self, required_role):
        """Check if user has required role or higher"""
        role_hierarchy = {
            UserRole.CASHIER: 1,
            UserRole.MANAGER: 2,
            UserRole.ADMIN: 3
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(required_role, 0)

class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    products = db.relationship('Product', backref='supplier', lazy=True)
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy=True)

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    barcode = db.Column(db.String(50), unique=True, nullable=True)  # Barcode/QR code for scanning
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    unit_type = db.Column(db.Enum(UnitType), default=UnitType.PIECE)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    cost_price = db.Column(db.Numeric(10, 2), default=0.00)  # For profit calculation
    stock_quantity = db.Column(db.Integer, default=0)
    min_stock_level = db.Column(db.Integer, default=0)
    image_filename = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign keys
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    
    # Relationships
    transaction_items = db.relationship('TransactionItem', backref='product', lazy=True)
    purchase_order_items = db.relationship('PurchaseOrderItem', backref='product', lazy=True)
    
    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.min_stock_level
    
    @property
    def profit_margin(self):
        if self.cost_price > 0:
            return ((self.price - self.cost_price) / self.price * 100)
        return 0

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_number = db.Column(db.String(20), unique=True, nullable=False)
    status = db.Column(db.Enum(TransactionStatus), default=TransactionStatus.PENDING)
    subtotal = db.Column(db.Numeric(10, 2), default=0.00)
    discount_amount = db.Column(db.Numeric(10, 2), default=0.00)
    tax_amount = db.Column(db.Numeric(10, 2), default=0.00)
    total_amount = db.Column(db.Numeric(10, 2), default=0.00)
    cashier_name = db.Column(db.String(100))
    customer_name = db.Column(db.String(100))
    promo_code_used = db.Column(db.String(20))  # Store applied promo code
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Foreign key for user tracking
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationships
    items = db.relationship('TransactionItem', backref='transaction', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='transaction', lazy=True, cascade='all, delete-orphan')

class TransactionItem(db.Model):
    __tablename__ = 'transaction_items'
    
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Numeric(10, 3), nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    discount_amount = db.Column(db.Numeric(10, 2), default=0.00)
    total_price = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Foreign keys
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    method = db.Column(db.Enum(PaymentMethod), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    reference_number = db.Column(db.String(100))  # For card/transfer payments
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign key
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)

class OperationLog(db.Model):
    __tablename__ = 'operation_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(100), nullable=False)  # login, sale, inventory_update, etc.
    description = db.Column(db.Text)
    entity_type = db.Column(db.String(50))  # transaction, product, user, etc.
    entity_id = db.Column(db.Integer)  # ID of the affected entity
    old_values = db.Column(db.Text)  # JSON string of old values
    new_values = db.Column(db.Text)  # JSON string of new values
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign key
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_date = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')  # pending, received, cancelled
    total_amount = db.Column(db.Numeric(10, 2), default=0.00)
    notes = db.Column(db.Text)
    
    # Foreign key
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    
    # Relationships
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')

class PurchaseOrderItem(db.Model):
    __tablename__ = 'purchase_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(10, 2), nullable=False)
    total_cost = db.Column(db.Numeric(10, 2), nullable=False)
    
    # Foreign keys
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)

class DiscountRule(db.Model):
    __tablename__ = 'discount_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    discount_type = db.Column(db.String(20), nullable=False)  # percentage, fixed_amount
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    min_amount = db.Column(db.Numeric(10, 2), default=0.00)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    is_active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PromoCode(db.Model):
    __tablename__ = 'promo_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)  # Unique constraint handled separately
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    discount_type = db.Column(db.String(20), nullable=False)  # percentage, fixed_amount
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    min_amount = db.Column(db.Numeric(10, 2), default=0.00)
    max_uses = db.Column(db.Integer, default=None)  # None = unlimited
    current_uses = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add constraints and indexes for production
    __table_args__ = (
        db.Index('ix_promo_codes_upper_code', func.upper(code), unique=True),
        db.Index('ix_promo_codes_active', 'is_active'),
        db.CheckConstraint('discount_value >= 0', name='check_discount_value_positive'),
        db.CheckConstraint('current_uses >= 0', name='check_current_uses_positive'),
        db.CheckConstraint('max_uses IS NULL OR max_uses >= 0', name='check_max_uses_positive'),
    )