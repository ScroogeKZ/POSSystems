from flask import Blueprint, render_template, request, jsonify, send_file, session, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Product, Supplier, Category, Transaction, TransactionItem, Payment, User
from models import PaymentMethod, TransactionStatus, UnitType, UserRole
from datetime import datetime, timedelta
from sqlalchemy import desc, func
import io
import pandas as pd
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

reports_bp = Blueprint('reports', __name__)

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

@reports_bp.route('/reports')
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

@reports_bp.route('/export/pdf', methods=['POST'])
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
                    str(sale['date']),
                    f"{sale['total_revenue'] or 0:.2f}",
                    f"{sale['total_profit'] or 0:.2f}"
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
                    product['name'],
                    f"{product['total_sold']:.0f}",
                    f"{product['total_revenue']:.2f}",
                    f"{product['total_profit'] or 0:.2f}"
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
                    category['name'],
                    str(category['total_transactions']),
                    f"{category['total_revenue']:.2f}",
                    f"{category['total_profit'] or 0:.2f}"
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

@reports_bp.route('/export/excel', methods=['POST'])
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
                        'Date': sale['date'],
                        'Revenue (₸)': sale['total_revenue'] or 0,
                        'Profit (₸)': sale['total_profit'] or 0
                    } for sale in daily_sales
                ])
                sales_df.to_excel(writer, sheet_name='Daily Sales', index=False)
            
            # Top Products Sheet
            if top_products:
                products_df = pd.DataFrame([
                    {
                        'Product': product['name'],
                        'Quantity Sold': product['total_sold'],
                        'Revenue (₸)': product['total_revenue'],
                        'Profit (₸)': product['total_profit'] or 0,
                        'Avg Profit per Unit (₸)': product['avg_profit_per_unit'] or 0
                    } for product in top_products
                ])
                products_df.to_excel(writer, sheet_name='Top Products', index=False)
            
            # Category Analysis Sheet
            if category_analysis:
                categories_df = pd.DataFrame([
                    {
                        'Category': category['name'],
                        'Total Transactions': category['total_transactions'],
                        'Total Sold': category['total_sold'],
                        'Revenue (₸)': category['total_revenue'],
                        'Profit (₸)': category['total_profit'] or 0,
                        'Profit Margin (%)': (category['total_profit'] / category['total_revenue'] * 100) if category['total_revenue'] > 0 else 0
                    } for category in category_analysis
                ])
                categories_df.to_excel(writer, sheet_name='Category Analysis', index=False)
            
            # Inventory Report Sheet
            if inventory_report:
                inventory_df = pd.DataFrame([
                    {
                        'Product': item['name'],
                        'SKU': item['sku'],
                        'Stock Quantity': item['stock_quantity'],
                        'Min Stock Level': item['min_stock_level'],
                        'Price (₸)': item['price'],
                        'Cost Price (₸)': item['cost_price'],
                        'Profit per Unit (₸)': item['price'] - item['cost_price'],
                        'Category': item['category_name'],
                        'Supplier': item['supplier_name'],
                        'Status': 'Low Stock' if item['stock_quantity'] <= item['min_stock_level'] else 'OK'
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

@reports_bp.route('/api/analytics/top_products')
@login_required
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

@reports_bp.route('/api/analytics/sales_summary')
@login_required
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