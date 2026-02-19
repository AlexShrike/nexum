#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from decimal import Decimal
from datetime import date, timedelta
from core_banking.audit import AuditTrail
from core_banking.ledger import GeneralLedger
from core_banking.customers import CustomerManager, KYCStatus, KYCTier
from core_banking.accounts import AccountManager, ProductType
from core_banking.transactions import TransactionProcessor, TransactionChannel
from core_banking.compliance import ComplianceEngine
from core_banking.interest import InterestEngine
from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage

def debug_compound_interest():
    print("=== DEBUG: Compound Interest ===")
    
    # Initialize system
    storage = InMemoryStorage()
    audit_trail = AuditTrail(storage)
    ledger = GeneralLedger(storage, audit_trail)
    customer_manager = CustomerManager(storage, audit_trail)
    account_manager = AccountManager(storage, ledger, audit_trail)
    compliance_engine = ComplianceEngine(storage, customer_manager, audit_trail)
    transaction_processor = TransactionProcessor(storage, ledger, account_manager, customer_manager, compliance_engine, audit_trail)
    interest_engine = InterestEngine(storage, ledger, account_manager, transaction_processor, audit_trail)
    
    # Create customer and upgrade to TIER_2
    customer = customer_manager.create_customer(
        first_name="Test",
        last_name="Customer", 
        email="test@example.com"
    )
    customer_manager.update_kyc_status(customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2)
    print(f"Created customer: {customer.id}")
    
    # Create savings account with 5% interest rate
    savings_account = account_manager.create_account(
        customer_id=customer.id,
        product_type=ProductType.SAVINGS,
        currency=Currency.USD,
        name="Test Savings",
        interest_rate=Decimal('0.05')  # 5% APY
    )
    print(f"Created account: {savings_account.id}")
    
    # Deposit $10,000
    principal = Money(Decimal('10000.00'), Currency.USD)
    deposit = transaction_processor.deposit(
        account_id=savings_account.id,
        amount=principal,
        description="Principal deposit",
        channel=TransactionChannel.BRANCH
    )
    transaction_processor.process_transaction(deposit.id)
    
    initial_balance = account_manager.get_book_balance(savings_account.id)
    print(f"Initial balance: {initial_balance.to_string()}")
    
    # Track balances and interest over the first few months
    start_date = date(2024, 1, 1)
    
    for month in range(1, 3):  # First 2 months only for debugging
        print(f"\n=== MONTH {month} ===")
        
        # Get balance at start of month
        balance_start = account_manager.get_book_balance(savings_account.id)
        print(f"Balance at start of month {month}: {balance_start.to_string()}")
        
        # Run daily accrual for the entire month
        if month == 1:  # January
            month_start = date(2024, 1, 1)
            month_end = date(2024, 1, 31)
        elif month == 2:  # February
            month_start = date(2024, 2, 1)
            month_end = date(2024, 2, 29)  # 2024 is leap year
        else:  # March
            month_start = date(2024, 3, 1)
            month_end = date(2024, 3, 31)
            
        current_date = month_start
        daily_interest_total = Money(Decimal('0'), Currency.USD)
        
        while current_date <= month_end:
            # Check balance before accrual
            balance_before = account_manager.get_book_balance(savings_account.id)
            
            # Run accrual for this day
            results = interest_engine.run_daily_accrual(current_date)
            
            # Get the accrual that was created
            accruals = interest_engine._get_unposted_accruals(savings_account.id)
            if accruals:
                latest_accrual = max(accruals, key=lambda x: x.accrual_date)
                if latest_accrual.accrual_date == current_date:
                    daily_interest_total = daily_interest_total + latest_accrual.accrued_amount
                    manual_calc = latest_accrual.principal_balance.amount * latest_accrual.daily_rate
                    print(f"  {current_date}: Balance {balance_before.to_string()} -> Principal ${latest_accrual.principal_balance.to_string()} -> Rate {latest_accrual.daily_rate} -> Calc {manual_calc:.4f} -> Interest {latest_accrual.accrued_amount.to_string()}")
            
            current_date = current_date + timedelta(days=1)
        
        print(f"Total interest accrued in month {month}: {daily_interest_total.to_string()}")
        
        # Post monthly interest
        posting_results = interest_engine.post_monthly_interest(month, 2024)
        print(f"Posted transactions: {posting_results}")
        
        # Get balance after posting
        balance_end = account_manager.get_book_balance(savings_account.id)
        print(f"Balance after posting interest: {balance_end.to_string()}")
        
        # Calculate expected interest for verification
        daily_rate = Decimal('0.05') / Decimal('365')
        days_in_month = (month_end - month_start).days + 1
        expected_interest = balance_start.amount * daily_rate * days_in_month
        print(f"Expected interest (simple): USD {expected_interest:.2f}")

if __name__ == "__main__":
    debug_compound_interest()