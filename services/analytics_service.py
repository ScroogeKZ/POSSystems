"""
Analytics and reporting business logic service
"""
from datetime import datetime, timedelta
from sqlalchemy import func, desc, text
from models import db, Transaction, TransactionItem, Product, Category, Supplier, TransactionStatus


class AnalyticsService:
    """Service for handling analytics and reporting business logic"""
    
    @staticmethod
    def get_sales_summary(start_date=None, end_date=None):
        """Get sales summary for date range"""
        if not start_date:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if not end_date:
            end_date = datetime.now()
        
        # Get total sales
        total_sales = db.session.query(
            func.sum(Transaction.total_amount)
        ).filter(
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.completed_at.between(start_date, end_date)
        ).scalar() or 0
        
        # Get transaction count
        transaction_count = Transaction.query.filter(
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.completed_at.between(start_date, end_date)
        ).count()
        
        # Get average transaction value
        avg_transaction = total_sales / transaction_count if transaction_count > 0 else 0
        
        return {
            'total_sales': float(total_sales),
            'transaction_count': transaction_count,
            'avg_transaction_value': float(avg_transaction),
            'period_start': start_date,
            'period_end': end_date
        }
    
    @staticmethod
    def get_top_products(limit=10, start_date=None, end_date=None):
        """Get top selling products"""
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        top_products = db.session.query(
            Product.id,
            Product.name,
            Product.price,
            Product.cost_price,
            func.sum(TransactionItem.quantity).label('total_sold'),
            func.sum(TransactionItem.total_price).label('total_revenue'),
            func.sum((Product.price - Product.cost_price) * TransactionItem.quantity).label('total_profit')
        ).join(
            TransactionItem, Product.id == TransactionItem.product_id
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.completed_at.between(start_date, end_date)
        ).group_by(
            Product.id, Product.name, Product.price, Product.cost_price
        ).order_by(
            desc('total_sold')
        ).limit(limit).all()
        
        return [{
            'id': row.id,
            'name': row.name,
            'price': float(row.price),
            'cost_price': float(row.cost_price),
            'total_sold': float(row.total_sold),
            'total_revenue': float(row.total_revenue),
            'total_profit': float(row.total_profit),
            'avg_profit_per_unit': float(row.total_profit / row.total_sold) if row.total_sold > 0 else 0
        } for row in top_products]
    
    @staticmethod
    def get_category_analysis(start_date=None, end_date=None):
        """Get sales analysis by category"""
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        
        category_analysis = db.session.query(
            Category.name,
            func.sum(TransactionItem.total_price).label('total_revenue'),
            func.sum((Product.price - Product.cost_price) * TransactionItem.quantity).label('total_profit'),
            func.count(TransactionItem.id).label('total_transactions')
        ).join(
            Product, Category.id == Product.category_id
        ).join(
            TransactionItem, Product.id == TransactionItem.product_id
        ).join(
            Transaction, TransactionItem.transaction_id == Transaction.id
        ).filter(
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.completed_at.between(start_date, end_date)
        ).group_by(
            Category.name
        ).order_by(
            desc('total_revenue')
        ).all()
        
        return [{
            'name': row.name,
            'total_revenue': float(row.total_revenue),
            'total_profit': float(row.total_profit),
            'total_transactions': int(row.total_transactions)
        } for row in category_analysis]
    
    @staticmethod
    def get_daily_sales(days=30):
        """Get daily sales for the last N days"""
        start_date = datetime.now() - timedelta(days=days)
        
        daily_sales = db.session.query(
            func.date(Transaction.completed_at).label('date'),
            func.sum(Transaction.total_amount).label('total_revenue'),
            func.sum(Transaction.total_amount - Transaction.subtotal + 
                    func.coalesce(func.sum(
                        (Product.price - Product.cost_price) * TransactionItem.quantity
                    ), 0)).label('total_profit'),
            func.count(Transaction.id).label('transaction_count')
        ).join(
            TransactionItem, Transaction.id == TransactionItem.transaction_id
        ).join(
            Product, TransactionItem.product_id == Product.id
        ).filter(
            Transaction.status == TransactionStatus.COMPLETED,
            Transaction.completed_at >= start_date
        ).group_by(
            func.date(Transaction.completed_at)
        ).order_by(
            func.date(Transaction.completed_at)
        ).all()
        
        return [{
            'date': row.date.strftime('%Y-%m-%d'),
            'total_revenue': float(row.total_revenue),
            'total_profit': float(row.total_profit or 0),
            'transaction_count': int(row.transaction_count)
        } for row in daily_sales]
    
    @staticmethod
    def get_inventory_report():
        """Get inventory status report"""
        inventory_report = db.session.query(
            Product.id,
            Product.name,
            Product.sku,
            Product.stock_quantity,
            Product.min_stock_level,
            Product.price,
            Product.cost_price,
            Category.name.label('category_name'),
            Supplier.name.label('supplier_name')
        ).join(
            Category, Product.category_id == Category.id
        ).join(
            Supplier, Product.supplier_id == Supplier.id
        ).filter(
            Product.is_active == True
        ).order_by(
            Product.name
        ).all()
        
        return [{
            'id': row.id,
            'name': row.name,
            'sku': row.sku,
            'stock_quantity': int(row.stock_quantity),
            'min_stock_level': int(row.min_stock_level),
            'price': float(row.price),
            'cost_price': float(row.cost_price),
            'profit_margin': float((row.price - row.cost_price) / row.price * 100) if row.price > 0 else 0,
            'category_name': row.category_name,
            'supplier_name': row.supplier_name,
            'stock_status': 'low' if row.stock_quantity <= row.min_stock_level else 'normal'
        } for row in inventory_report]
    
    @staticmethod
    def get_low_stock_products():
        """Get products with low stock"""
        low_stock = Product.query.filter(
            Product.stock_quantity <= Product.min_stock_level,
            Product.is_active == True
        ).order_by(
            Product.stock_quantity
        ).all()
        
        return [{
            'id': product.id,
            'name': product.name,
            'sku': product.sku,
            'stock_quantity': product.stock_quantity,
            'min_stock_level': product.min_stock_level,
            'shortage': product.min_stock_level - product.stock_quantity
        } for product in low_stock]