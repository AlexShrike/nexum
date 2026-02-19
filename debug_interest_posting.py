#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from decimal import Decimal
from datetime import date, timedelta
from core_banking.audit import AuditTrail
from core_banking.ledger import GeneralLedger
from core_banking.customers import CustomerManager
from core_banking.accounts import AccountManager, ProductType
from core_banking.transactions import TransactionProcessor, TransactionChannel
from core_banking.compliance import ComplianceEngine
from core_banking.interest import InterestEngine
from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage

def debug_interest_posting():
    print("=== DEBUG: Interest Posting ===")
    
    # Initialize system
    storage = InMemoryStorage()
    audit_trail = AuditTrail(storage)
    ledger = GeneralLedger(storage, audit_trail)
    customer_manager = CustomerManager(storage, audit_trail)
    account_manager = AccountManager(storage, ledger, audit_trail)
    compliance_engine = ComplianceEngine(storage, customer_manager, audit_trail)
    transaction_processor = TransactionProcessor(storage, ledger, account_manager, customer_manager, compliance_engine, audit_trail)
    interest_engine = InterestEngine(storage, ledger, account_manager, transaction_processor, audit_trail)
    
    # Create customer
    customer = customer_manager.create_customer(
        first_name="Test",
        last_name="Customer",
        email="test@example.com"
    )
    # Upgrade to TIER_2 for higher limits
    from core_banking.customers import KYCStatus, KYCTier
    customer_manager.update_kyc_status(customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2)
    print(f"Created customer: {customer.id}")
    
    # Create savings account
    savings_account = account_manager.create_account(
        customer_id=customer.id,
        product_type=ProductType.SAVINGS,
        currency=Currency.USD,
        name="Test Savings",
        interest_rate=Decimal('0.02')
    )
    print(f"Created account: {savings_account.id}")
    
    # Make deposit
    deposit = transaction_processor.deposit(
        account_id=savings_account.id,
        amount=Money(Decimal('2000.00'), Currency.USD),
        description="Test deposit",
        channel=TransactionChannel.BRANCH
    )
    processed_deposit = transaction_processor.process_transaction(deposit.id)
    print(f"Processed deposit: {processed_deposit.id}")
    
    # Check balance
    balance = account_manager.get_book_balance(savings_account.id)
    print(f"Account balance: {balance.to_string()}")
    
    # Run daily accrual for 5 days
    print("\n=== Running daily accrual ===")
    for i in range(5):
        accrual_date = date.today() - timedelta(days=i)
        print(f"Running accrual for {accrual_date}")
        results = interest_engine.run_daily_accrual(accrual_date)
        print(f"  Results: {results}")
    
    # Check unposted accruals
    print("\n=== Checking accruals ===")
    unposted_accruals = interest_engine._get_unposted_accruals(savings_account.id)
    print(f"Unposted accruals count: {len(unposted_accruals)}")
    for accrual in unposted_accruals:
        print(f"  Accrual: {accrual.accrual_date} - {accrual.accrued_amount.to_string()}")
    
    # Check all accruals in storage
    all_accruals_data = storage.find(interest_engine.accruals_table, {"posted": False})
    print(f"All unposted accruals in storage: {len(all_accruals_data)}")
    
    # Post monthly interest
    print("\n=== Posting monthly interest ===")
    current_month = date.today().month
    current_year = date.today().year
    print(f"Posting for month {current_month}/{current_year}")
    
    # Debug: Check what dates we're filtering for
    import calendar
    start_date = date(current_year, current_month, 1)
    end_date = date(current_year, current_month, calendar.monthrange(current_year, current_month)[1])
    print(f"Date range: {start_date} to {end_date}")
    
    # Debug the filtering logic
    all_accruals_data = storage.find(interest_engine.accruals_table, {"posted": False})
    accruals = [interest_engine._accrual_from_dict(data) for data in all_accruals_data]
    print(f"Total unposted accruals: {len(accruals)}")
    
    account_accruals = {}
    for accrual in accruals:
        accrual_date = accrual.accrual_date
        print(f"  Checking accrual date: {accrual_date}")
        print(f"    In range {start_date} <= {accrual_date} <= {end_date}? {start_date <= accrual_date <= end_date}")
        
        # Current month range for testing
        current_month_start = date.today().replace(day=1)
        current_month_end = date(current_month_start.year, current_month_start.month, 
                               calendar.monthrange(current_month_start.year, current_month_start.month)[1])
        print(f"    In current range {current_month_start} <= {accrual_date} <= {current_month_end}? {current_month_start <= accrual_date <= current_month_end}")
        
        if (start_date <= accrual_date <= end_date) or (current_month_start <= accrual_date <= current_month_end):
            if accrual.account_id not in account_accruals:
                account_accruals[accrual.account_id] = []
            account_accruals[accrual.account_id].append(accrual)
    
    print(f"Filtered account accruals: {len(account_accruals)}")
    for account_id, accruals_list in account_accruals.items():
        print(f"  Account {account_id}: {len(accruals_list)} accruals")
    
    # Test the _post_interest_for_account method directly  
    account_id = savings_account.id
    accruals_for_account = account_accruals[account_id]
    print(f"Trying to post {len(accruals_for_account)} accruals for account {account_id}")
    
    # Calculate total
    total_interest = Money(Decimal('0'), Currency.USD)
    for accrual in accruals_for_account:
        total_interest = total_interest + accrual.accrued_amount
        print(f"  Adding {accrual.accrued_amount.to_string()}, total now: {total_interest.to_string()}")
    
    print(f"Total interest to post: {total_interest.to_string()}")
    print(f"Is total >= $0.01? {total_interest.amount >= Decimal('0.01')}")
    
    try:
        transaction_id = interest_engine._post_interest_for_account(account_id, accruals_for_account)
        print(f"Posted transaction ID: {transaction_id}")
    except Exception as e:
        print(f"Error posting interest: {e}")
        import traceback
        traceback.print_exc()
    
    # Now try the full method
    results = interest_engine.post_monthly_interest(current_month, current_year)
    print(f"Full posting results: {results}")
    
    # Check final balance
    final_balance = account_manager.get_book_balance(savings_account.id)
    print(f"Final balance: {final_balance.to_string()}")

if __name__ == "__main__":
    debug_interest_posting()