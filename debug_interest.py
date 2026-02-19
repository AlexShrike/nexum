#!/usr/bin/env python3

"""Debug script for interest accrual"""

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
    
    savings_account = account_manager.create_account(
        customer_id=customer.id,
        product_type=ProductType.SAVINGS,
        currency=Currency.USD,
        name="Interest Test Savings",
        interest_rate=Decimal('0.02')  # 2% APY
    )
    
    print(f"Created account {savings_account.id} with state: {savings_account.state}")
    print(f"Account interest rate: {savings_account.interest_rate}")
    
    # Give account a balance
    deposit = transaction_processor.deposit(
        account_id=savings_account.id,
        amount=Money(Decimal('1000.00'), Currency.USD),
        description="Initial deposit",
        channel=TransactionChannel.ONLINE
    )
    processed_deposit = transaction_processor.process_transaction(deposit.id)
    print(f"Processed deposit: {processed_deposit.state}")
    
    balance = account_manager.get_book_balance(savings_account.id)
    print(f"Account balance: {balance.to_string()}")
    
    # Check if account would be found by daily accrual
    all_accounts_data = storage.load_all(account_manager.accounts_table)
    accounts = [account_manager._account_from_dict(data) for data in all_accounts_data]
    active_accounts = [acc for acc in accounts if acc.state.value == "active"]
    print(f"Total accounts: {len(accounts)}")
    print(f"Active accounts: {len(active_accounts)}")
    for acc in accounts:
        print(f"  Account {acc.id}: state={acc.state}, product={acc.product_type}, rate={acc.interest_rate}")
    
    # Test rate config lookup
    rate_config = interest_engine._get_rate_config_for_account(savings_account)
    print(f"Rate config: {rate_config}")
    if rate_config:
        print(f"  Annual rate: {rate_config.annual_rate}")
    
    # Check if already processed
    accrual_date = date.today()
    already_processed = interest_engine._is_accrual_processed(savings_account.id, accrual_date)
    print(f"Already processed for {accrual_date}: {already_processed}")
    
    # Try manual accrual calculation
    if rate_config:
        accrual = interest_engine._calculate_daily_accrual(savings_account, rate_config, accrual_date)
        print(f"Calculated accrual: {accrual}")
        if accrual:
            print(f"  Amount: {accrual.accrued_amount.to_string()}")
    
    # Run daily accrual
    results = interest_engine.run_daily_accrual(accrual_date)
    print(f"Accrual results: {results}")

if __name__ == "__main__":
    main()