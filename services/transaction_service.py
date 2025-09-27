"""
Transaction business logic service
"""
from decimal import Decimal
from datetime import datetime
from flask import session
from flask_login import current_user
from models import db, Transaction, TransactionItem, Product, TransactionStatus, PaymentMethod, Payment, PromoCode
from sqlalchemy import func
from utils.helpers import generate_transaction_number, log_operation


class TransactionService:
    """Service for handling transaction business logic"""
    
    @staticmethod
    def start_transaction(cashier_name='Кассир', customer_name=''):
        """Start a new transaction"""
        transaction = Transaction()
        transaction.transaction_number = generate_transaction_number()
        transaction.status = TransactionStatus.PENDING
        transaction.cashier_name = cashier_name
        transaction.customer_name = customer_name
        transaction.user_id = current_user.id if current_user.is_authenticated else None
        
        db.session.add(transaction)
        db.session.commit()
        
        # Store transaction ID in session
        session['current_transaction_id'] = transaction.id
        
        return transaction
    
    @staticmethod
    def add_item_to_transaction(transaction_id, product_id, quantity):
        """Add item to transaction with stock validation"""
        transaction = Transaction.query.get(transaction_id)
        if not transaction or transaction.status != TransactionStatus.PENDING:
            raise ValueError('Транзакция недоступна')
        
        product = Product.query.get(product_id)
        if not product:
            raise ValueError('Товар не найден')
        
        quantity = Decimal(str(quantity))
        if quantity <= 0:
            raise ValueError('Неверное количество')
        
        # Check stock
        if product.stock_quantity < float(quantity):
            raise ValueError('Недостаточно товара на складе')
        
        # Create new item
        item = TransactionItem()
        item.transaction_id = transaction_id
        item.product_id = product.id
        item.quantity = quantity
        item.unit_price = product.price
        item.total_price = quantity * product.price
        item.discount_amount = Decimal('0.00')
        db.session.add(item)
        
        # Update transaction totals
        TransactionService.update_transaction_totals(transaction)
        db.session.commit()
        
        return item, transaction
    
    @staticmethod
    def update_transaction_totals(transaction):
        """Update transaction totals based on items"""
        if not transaction.items:
            transaction.subtotal = Decimal('0.00')
            transaction.discount_amount = Decimal('0.00')
            transaction.tax_amount = Decimal('0.00')
            transaction.total_amount = Decimal('0.00')
            return
        
        # Calculate subtotal from items
        subtotal = sum(item.total_price - item.discount_amount for item in transaction.items)
        
        # Apply transaction-level discount
        discount_amount = transaction.discount_amount or Decimal('0.00')
        
        # Calculate after discount
        after_discount = subtotal - discount_amount
        
        # Calculate tax (12% VAT for Kazakhstan)
        tax_rate = Decimal('0.12')  # 12% VAT
        tax_amount = after_discount * tax_rate
        
        # Calculate total
        total_amount = after_discount + tax_amount
        
        transaction.subtotal = subtotal
        transaction.tax_amount = tax_amount
        transaction.total_amount = total_amount
    
    @staticmethod
    def complete_transaction(transaction_id, payments):
        """Complete transaction with payments and stock updates"""
        transaction = Transaction.query.get(transaction_id)
        if not transaction or transaction.status != TransactionStatus.PENDING:
            raise ValueError('Транзакция недоступна')
        
        # Validate payment amounts
        total_payment = sum(Decimal(str(p['amount'])) for p in payments)
        if abs(total_payment - transaction.total_amount) > Decimal('0.01'):
            raise ValueError('Сумма оплаты не совпадает с общей суммой')
        
        # Create payment records
        for payment_data in payments:
            payment = Payment()
            payment.transaction_id = transaction.id
            payment.method = PaymentMethod(payment_data['method'])
            payment.amount = Decimal(str(payment_data['amount']))
            payment.reference_number = payment_data.get('reference_number')
            db.session.add(payment)
        
        # Update stock quantities
        for item in transaction.items:
            item.product.stock_quantity -= int(item.quantity)
        
        # Handle promo code usage increment if promo code was used
        if transaction.promo_code_used:
            promo = db.session.query(PromoCode).filter(
                func.upper(PromoCode.code) == transaction.promo_code_used.upper(),
                PromoCode.is_active == True
            ).with_for_update().first()
            
            if promo:
                if promo.max_uses and promo.current_uses >= promo.max_uses:
                    raise ValueError('Промокод исчерпан на момент завершения транзакции')
                promo.current_uses += 1
        
        # Complete transaction
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.utcnow()
        transaction.user_id = current_user.id if current_user.is_authenticated else None
        
        db.session.commit()
        
        # Log the completed sale
        log_operation(
            'sale_completed',
            f'Transaction {transaction.transaction_number} completed for ₸{transaction.total_amount}',
            'transaction',
            transaction.id,
            None,
            {
                'transaction_number': transaction.transaction_number,
                'total_amount': float(transaction.total_amount),
                'items_count': len(transaction.items),
                'payment_methods': [p['method'] for p in payments]
            }
        )
        
        # Clear current transaction from session
        session.pop('current_transaction_id', None)
        
        return transaction
    
    @staticmethod
    def suspend_transaction(transaction_id):
        """Suspend current transaction"""
        transaction = Transaction.query.get(transaction_id)
        if not transaction or transaction.status != TransactionStatus.PENDING:
            raise ValueError('Транзакция недоступна')
        
        transaction.status = TransactionStatus.SUSPENDED
        db.session.commit()
        
        # Clear current transaction from session
        session.pop('current_transaction_id', None)
        
        return transaction
    
    @staticmethod
    def restore_transaction(transaction_id):
        """Restore suspended transaction"""
        transaction = Transaction.query.get(transaction_id)
        if not transaction or transaction.status != TransactionStatus.SUSPENDED:
            raise ValueError('Транзакция недоступна для восстановления')
        
        transaction.status = TransactionStatus.PENDING
        db.session.commit()
        
        # Set as current transaction
        session['current_transaction_id'] = transaction.id
        
        return transaction