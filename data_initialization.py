"""
Data initialization module for POS system
Handles creation of sample data for Kazakhstan market
"""
from typing import List
from datetime import datetime, timedelta
from models import (
    db, Category, Supplier, Product, PromoCode, 
    UnitType
)


def create_sample_categories() -> List[Category]:
    """Create sample categories for Kazakhstan market"""
    categories_data = [
        {"name": "Сүт өнімдері", "description": "Сүт, ірімшік, йогурт"},
        {"name": "Нан өнімдері", "description": "Нан, тоқаш, печенье"},
        {"name": "Сусындар", "description": "Шырын, газдалған сусындар, су"},
        {"name": "Ет өнімдері", "description": "Ет, шұжық, деликатестер"},
        {"name": "Жемістер мен көкөністер", "description": "Жаңа жемістер мен көкөністер"}
    ]
    
    categories = []
    for data in categories_data:
        category = Category()
        category.name = data["name"]
        category.description = data["description"]
        categories.append(category)
        db.session.add(category)
    
    return categories


def create_sample_supplier() -> Supplier:
    """Create sample supplier for Kazakhstan market"""
    supplier = Supplier()
    supplier.name = "ЖШС АлматыТрейд"
    supplier.contact_person = "Асылбек Нұрболов"
    supplier.phone = "+7 (727) 250-30-40"
    supplier.email = "orders@almatytrade.kz"
    supplier.address = "Алматы қ., Абай д-лы, 120, 050000"
    
    db.session.add(supplier)
    return supplier


def create_sample_products(supplier: Supplier, categories: List[Category]) -> List[Product]:
    """Create sample products for Kazakhstan market"""
    products_data = [
        {
            "sku": "MLK001", "name": "Сүт 3.2% 1л", "price": 320.00, "cost_price": 220.00,
            "stock_quantity": 50, "min_stock_level": 10, "unit_type": UnitType.PIECE,
            "category_idx": 0
        },
        {
            "sku": "BRD001", "name": "Нан ақ", "price": 180.00, "cost_price": 120.00,
            "stock_quantity": 30, "min_stock_level": 5, "unit_type": UnitType.PIECE,
            "category_idx": 1
        },
        {
            "sku": "JCE001", "name": "Апельсин шырыны 1л", "price": 580.00, "cost_price": 410.00,
            "stock_quantity": 25, "min_stock_level": 8, "unit_type": UnitType.PIECE,
            "category_idx": 2
        },
        {
            "sku": "CHE001", "name": "Ірімшік қазақстандық", "price": 2200.00, "cost_price": 1560.00,
            "stock_quantity": 15, "min_stock_level": 3, "unit_type": UnitType.KILOGRAM,
            "category_idx": 0
        },
        {
            "sku": "APL001", "name": "Алма қызыл", "price": 890.00, "cost_price": 590.00,
            "stock_quantity": 40, "min_stock_level": 10, "unit_type": UnitType.KILOGRAM,
            "category_idx": 4
        }
    ]
    
    products = []
    for data in products_data:
        product = Product()
        product.sku = data["sku"]
        product.name = data["name"]
        product.price = data["price"]
        product.cost_price = data["cost_price"]
        product.stock_quantity = data["stock_quantity"]
        product.min_stock_level = data["min_stock_level"]
        product.unit_type = data["unit_type"]
        product.supplier_id = supplier.id
        product.category_id = categories[data["category_idx"]].id
        
        products.append(product)
        db.session.add(product)
    
    return products


def create_sample_promo_codes() -> List[PromoCode]:
    """Create sample promo codes for testing"""
    promo_data = [
        {
            "code": "SAVE10", "name": "10% скидка", 
            "description": "Скидка 10% на любую покупку",
            "discount_type": "percentage", "discount_value": 10.00, 
            "min_amount": 500.00, "max_uses": 100, "current_uses": 0, 
            "is_active": True
        },
        {
            "code": "NEWCUSTOMER", "name": "Скидка новому клиенту", 
            "description": "200₸ скидка для новых клиентов",
            "discount_type": "fixed_amount", "discount_value": 200.00, 
            "min_amount": 1000.00, "max_uses": 50, "current_uses": 0, 
            "is_active": True
        },
        {
            "code": "WEEKEND", "name": "Выходная скидка", 
            "description": "15% скидка на выходные",
            "discount_type": "percentage", "discount_value": 15.00, 
            "min_amount": 300.00, "max_uses": None, "current_uses": 0, 
            "is_active": True, "start_date": datetime.utcnow(),
            "end_date": datetime.utcnow() + timedelta(days=30)
        }
    ]
    
    promos = []
    for data in promo_data:
        promo = PromoCode()
        for key, value in data.items():
            setattr(promo, key, value)
        
        promos.append(promo)
        db.session.add(promo)
    
    return promos


def initialize_sample_data() -> None:
    """Initialize database with sample data if empty"""
    if Category.query.count() == 0:
        # Create categories for Kazakhstan market
        categories = create_sample_categories()
        
        # Create Kazakhstan supplier
        supplier = create_sample_supplier()
        
        db.session.commit()
        
        # Create sample products for Kazakhstan market
        products = create_sample_products(supplier, categories)
        
        db.session.commit()
        
        # Create sample promo codes for testing
        if PromoCode.query.count() == 0:
            promos = create_sample_promo_codes()
            db.session.commit()