#!/usr/bin/env python3

"""Debug script for transaction reversal"""

from decimal import Decimal
from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.customers import CustomerManager
from core_banking.ledger import GeneralLedger
from core_banking.accounts import AccountManager, ProductType
from core_banking.transactions import TransactionProcessor, TransactionChannel

def main():
    # Setup
    storage = InMemoryStorage()
    audit_trail = AuditTrail(storage)
    customer_manager = CustomerManager(storage, audit_trail)
    ledger = GeneralLedger(storage, audit_trail)
    account_manager = AccountManager(storage, ledger, audit_trail)
    transaction_processor = TransactionProcessor(storage, account_manager, ledger, audit_trail)
    
    # Create customer and account
    customer = customer_manager.create_customer("Test", "Customer", "test@example.com")
    account = account_manager.create_account(
        customer_id=customer.id,
        product_type=ProductType.SAVINGS,
        currency=Currency.USD,
        name="Test Savings"
    )
    
    print(f"Initial balance: {account_manager.get_book_balance(account.id).to_string()}")
    
    # Create and process deposit
    deposit = transaction_processor.deposit(
        account_id=account.id,
        amount=Money(Decimal('100.00'), Currency.USD),
        description="Test deposit",
        channel=TransactionChannel.BRANCH
    )
    print(f"Created deposit transaction: {deposit.id}")
    print(f"Deposit from_account_id: {deposit.from_account_id}")
    print(f"Deposit to_account_id: {deposit.to_account_id}")
    
    processed_deposit = transaction_processor.process_transaction(deposit.id)
    print(f"Processed deposit, state: {processed_deposit.state}")
    print(f"Journal entry ID: {processed_deposit.journal_entry_id}")
    
    balance_after_deposit = account_manager.get_book_balance(account.id)
    print(f"Balance after deposit: {balance_after_deposit.to_string()}")
    
    # Create reversal
    reversal = transaction_processor.reverse_transaction(
        processed_deposit.id,
        "Test reversal"
    )
    print(f"Created reversal transaction: {reversal.id}")
    print(f"Reversal from_account_id: {reversal.from_account_id}")
    print(f"Reversal to_account_id: {reversal.to_account_id}")
    print(f"Reversal state: {reversal.state}")
    print(f"Reversal journal entry ID: {reversal.journal_entry_id}")
    
    final_balance = account_manager.get_book_balance(account.id)
    print(f"Final balance: {final_balance.to_string()}")
    
    # Check journal entries
    if processed_deposit.journal_entry_id:
        deposit_entry = ledger.get_journal_entry(processed_deposit.journal_entry_id)
        if deposit_entry:
            print(f"\nDeposit journal entry lines:")
            for line in deposit_entry.lines:
                print(f"  {line.account_id}: Dr {line.debit_amount.to_string()}, Cr {line.credit_amount.to_string()}")
    
    if reversal.journal_entry_id:
        reversal_entry = ledger.get_journal_entry(reversal.journal_entry_id)
        if reversal_entry:
            print(f"\nReversal journal entry lines:")
            for line in reversal_entry.lines:
                print(f"  {line.account_id}: Dr {line.debit_amount.to_string()}, Cr {line.credit_amount.to_string()}")

if __name__ == "__main__":
    main()