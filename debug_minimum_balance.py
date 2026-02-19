#!/usr/bin/env python3

"""Debug script for minimum balance"""

from decimal import Decimal
from datetime import date, datetime, timezone
from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.ledger import GeneralLedger
from core_banking.accounts import AccountManager, ProductType
from core_banking.customers import CustomerManager, KYCStatus, KYCTier
from core_banking.compliance import ComplianceEngine
from core_banking.transactions import TransactionProcessor, TransactionChannel
from core_banking.interest import InterestEngine

def main():
    # Setup (same as test)
    storage = InMemoryStorage()
    audit_trail = AuditTrail(storage)
    ledger = GeneralLedger(storage, audit_trail)
    account_manager = AccountManager(storage, ledger, audit_trail)
    customer_manager = CustomerManager(storage, audit_trail)
    compliance_engine = ComplianceEngine(storage, customer_manager, audit_trail)
    transaction_processor = TransactionProcessor(
        storage, ledger, account_manager,
        customer_manager, compliance_engine, audit_trail
    )
    interest_engine = InterestEngine(
        storage, ledger, account_manager,
        transaction_processor, audit_trail
    )
    
    # Create customer and account
    customer = customer_manager.create_customer(
        first_name="Alice",
        last_name="Johnson",
        email="alice@example.com"
    )
    
    customer_manager.update_kyc_status(
        customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2
    )
    
    # Create account with minimum balance
    savings_account = account_manager.create_account(
        customer_id=customer.id,
        product_type=ProductType.SAVINGS,
        currency=Currency.USD,
        name="Interest Test Savings",
        interest_rate=Decimal('0.02'),  # 2% APY
        minimum_balance=Money(Decimal('100.00'), Currency.USD)  # $100 minimum
    )
    
    print(f"Created account with minimum_balance: {savings_account.minimum_balance}")
    
    # Give account a balance below minimum ($50)
    deposit = transaction_processor.deposit(
        account_id=savings_account.id,
        amount=Money(Decimal('50.00'), Currency.USD),  # Below $100 minimum
        description="Small deposit",
        channel=TransactionChannel.ONLINE
    )
    processed_deposit = transaction_processor.process_transaction(deposit.id)
    print(f"Processed deposit: {processed_deposit.state}")
    
    balance = account_manager.get_book_balance(savings_account.id)
    print(f"Account balance: {balance.to_string()}")
    
    # Test rate config lookup
    rate_config = interest_engine._get_rate_config_for_account(savings_account)
    print(f"Rate config minimum_balance: {rate_config.minimum_balance}")
    
    # Check minimum balance comparison
    if rate_config.minimum_balance:
        meets_minimum = balance >= rate_config.minimum_balance
        print(f"Balance {balance.to_string()} >= minimum {rate_config.minimum_balance.to_string()}: {meets_minimum}")
    else:
        print("No minimum balance requirement")
    
    # Try manual accrual calculation
    accrual = interest_engine._calculate_daily_accrual(savings_account, rate_config, date.today())
    print(f"Calculated accrual: {accrual}")
    
    # Run daily accrual
    results = interest_engine.run_daily_accrual()
    print(f"Accrual results: {results}")

if __name__ == "__main__":
    main()