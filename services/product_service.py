"""
Product and inventory business logic service
"""
from models import db, Product, Category, Supplier, Transaction, TransactionItem, TransactionStatus
from sqlalchemy import or_, desc, func
from utils.helpers import log_operation
from utils.image_processing import process_product_image, delete_product_image, generate_unique_filename
from utils.language import translate_name, get_language


class ProductService:
    """Service for handling product and inventory business logic"""
    
    @staticmethod
    def search_products(query='', category_id=None, limit=20):
        """Search products with filters"""
        products_query = Product.query.filter_by(is_active=True)
        
        if query:
            products_query = products_query.filter(
                or_(
                    Product.name.ilike(f'%{query}%'),
                    Product.sku.ilike(f'%{query}%'),
                    Product.barcode.ilike(f'%{query}%')
                )
            )
        
        if category_id:
            products_query = products_query.filter_by(category_id=category_id)
        
        products = products_query.limit(min(limit, 50)).all()
        
        # Translate product names for current language
        for product in products:
            product.translated_name = translate_name(product.name)
        
        return products
    
    @staticmethod
    def search_by_barcode(barcode):
        """Search product by barcode"""
        if not barcode:
            return None
        
        product = Product.query.filter_by(barcode=barcode, is_active=True).first()
        if product:
            product.translated_name = translate_name(product.name)
        
        return product
    
    @staticmethod
    def get_popular_products(limit=10, days=30):
        """Get popular products based on sales"""
        from datetime import datetime, timedelta
        
        # Calculate date range
        start_date = datetime.now() - timedelta(days=days)
        
        # Query for popular products based on transaction items
        popular_products = db.session.query(
            Product.id,
            Product.name,
            Product.price,
            Product.stock_quantity,
            func.sum(TransactionItem.quantity).label('total_sold'),
            func.count(TransactionItem.id).label('transaction_count')
        ).join(
            TransactionItem, Product.id == TransactionItem.product_id
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.completed_at >= start_date,
            Product.is_active == True
        ).group_by(
            Product.id, Product.name, Product.price, Product.stock_quantity
        ).order_by(
            desc('total_sold')
        ).limit(limit).all()
        
        return popular_products
    
    @staticmethod
    def create_product(data):
        """Create new product"""
        # Validate required fields
        required_fields = ['name', 'price', 'category_id', 'supplier_id']
        for field in required_fields:
            if not data.get(field):
                raise ValueError(f'Поле {field} обязательно')
        
        # Check if SKU already exists
        if data.get('sku') and Product.query.filter_by(sku=data['sku']).first():
            raise ValueError('SKU уже существует')
        
        # Check if barcode already exists
        if data.get('barcode') and Product.query.filter_by(barcode=data['barcode']).first():
            raise ValueError('Штрихкод уже существует')
        
        product = Product()
        for key, value in data.items():
            if hasattr(product, key):
                setattr(product, key, value)
        
        db.session.add(product)
        db.session.commit()
        
        log_operation('product_create', f'Product created: {product.name}', 'product', product.id)
        
        return product
    
    @staticmethod
    def update_product(product_id, data):
        """Update existing product"""
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('Товар не найден')
        
        # Store old values for logging
        old_values = {
            'name': product.name,
            'price': float(product.price),
            'stock_quantity': product.stock_quantity
        }
        
        # Update product fields
        for key, value in data.items():
            if hasattr(product, key) and key != 'id':
                setattr(product, key, value)
        
        db.session.commit()
        
        # Store new values for logging
        new_values = {
            'name': product.name,
            'price': float(product.price),
            'stock_quantity': product.stock_quantity
        }
        
        log_operation('product_update', f'Product updated: {product.name}', 'product', product.id, old_values, new_values)
        
        return product
    
    @staticmethod
    def update_stock(product_id, quantity, operation='set'):
        """Update product stock"""
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('Товар не найден')
        
        old_stock = product.stock_quantity
        
        if operation == 'add':
            product.stock_quantity += quantity
        elif operation == 'subtract':
            if product.stock_quantity < quantity:
                raise ValueError('Недостаточно товара на складе')
            product.stock_quantity -= quantity
        else:  # set
            product.stock_quantity = quantity
        
        db.session.commit()
        
        log_operation(
            'inventory_update',
            f'Stock updated for {product.name}: {old_stock} -> {product.stock_quantity}',
            'product',
            product.id,
            {'stock_quantity': old_stock},
            {'stock_quantity': product.stock_quantity}
        )
        
        return product
    
    @staticmethod
    def upload_product_image(product_id, file):
        """Upload and process product image"""
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('Товар не найден')
        
        # Generate unique filename
        filename = generate_unique_filename(file.filename)
        
        # Process and save image
        success, result = process_product_image(file, filename)
        if not success:
            raise ValueError(result)
        
        # Delete old image if exists
        if product.image_filename:
            delete_product_image(product.image_filename)
        
        # Update product with new image
        product.image_filename = filename
        db.session.commit()
        
        log_operation('product_image_upload', f'Image uploaded for {product.name}', 'product', product.id)
        
        return product
    
    @staticmethod
    def delete_product_image(product_id):
        """Delete product image"""
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('Товар не найден')
        
        if product.image_filename:
            delete_product_image(product.image_filename)
            product.image_filename = None
            db.session.commit()
            
            log_operation('product_image_delete', f'Image deleted for {product.name}', 'product', product.id)
        
        return product