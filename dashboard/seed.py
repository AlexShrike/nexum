#!/usr/bin/env python3
"""Seed script for Nexum Core Banking Dashboard

Generates realistic demo data:
- 100 customers with realistic names and mixed KYC statuses
- 150 accounts (savings, checking, loan accounts)
- 500 transactions (deposits, withdrawals, transfers, loan payments)
- 20 loans (various statuses: active, paid off, overdue)
- 10 credit lines
- Compliance alerts
- Audit trail entries

Run with: python -m dashboard.seed
"""

import sys
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta
import random

# Add parent to path so core_banking package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import shared client data
from shared_clients import ALL_CLIENTS

from core_banking.api_old import banking_system, BankingSystem
from core_banking.currency import Money, Currency
from core_banking.accounts import ProductType
from core_banking.customers import KYCStatus, KYCTier, Address
from core_banking.transactions import TransactionType, TransactionChannel
from core_banking.loans import LoanTerms, PaymentFrequency, AmortizationMethod, LoanState
from core_banking.credit import TransactionCategory

# Using shared client fixture data from ALL_CLIENTS

TRANSACTION_DESCRIPTIONS = [
    'ATM Withdrawal', 'Online Transfer', 'Direct Deposit', 'Check Deposit',
    'Wire Transfer', 'Mobile Payment', 'Card Purchase', 'Interest Payment',
    'Fee Charge', 'Loan Payment', 'Bill Payment', 'Refund', 'Cash Deposit',
    'International Transfer', 'Merchant Payment', 'Subscription Payment',
    'Insurance Payment', 'Utility Payment', 'Rent Payment', 'Salary Deposit'
]

def random_date_in_range(start_date, end_date):
    """Generate a random date between start and end dates"""
    delta = end_date - start_date
    random_days = random.randint(0, delta.days)
    return start_date + timedelta(days=random_days)

def create_customers(system):
    """Create demo customers using shared client fixtures"""
    print(f"Creating {len(ALL_CLIENTS)} customers from shared fixtures...")
    customers = []
    
    for i, client_data in enumerate(ALL_CLIENTS):
        # Split full name into first/last
        name_parts = client_data["full_name"].split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else "Unknown"
        
        # Use shared client data
        email = client_data["email"]
        phone = client_data["phone"]
        
        # Random date of birth (18-80 years old)
        birth_year = random.randint(1943, 2005)
        birth_month = random.randint(1, 12)
        birth_day = random.randint(1, 28)
        date_of_birth = datetime(birth_year, birth_month, birth_day)
        
        # Parse address from shared data
        address_line = client_data["address"]
        city = client_data["city"]
        country = client_data["country"]
        
        # Create address object
        address = Address(
            line1=address_line,
            line2=None,
            city=city,
            state="CA",  # Default state
            postal_code=f"{random.randint(10000, 99999)}",
            country=country
        )
        
        try:
            customer = system.customer_manager.create_customer(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                date_of_birth=date_of_birth,
                address=address,
                external_id=client_data["external_id"]
            )
            
            # Map risk_rating to KYC status
            risk_rating = client_data["risk_rating"]
            kyc_level = client_data["kyc_level"]
            
            # Map risk to KYC status
            if risk_rating == "low":
                kyc_status = KYCStatus.VERIFIED if kyc_level in ["full", "enhanced"] else KYCStatus.PENDING
            elif risk_rating == "medium":
                kyc_status = KYCStatus.VERIFIED if kyc_level == "enhanced" else KYCStatus.PENDING
            elif risk_rating == "high":
                kyc_status = KYCStatus.PENDING if kyc_level == "enhanced" else KYCStatus.REJECTED
            else:  # critical
                kyc_status = KYCStatus.REJECTED
            
            if kyc_status != KYCStatus.NONE:
                # Map kyc_level to tier
                if kyc_level == "full":
                    kyc_tier = KYCTier.TIER_3  # Full KYC
                elif kyc_level == "enhanced":
                    kyc_tier = KYCTier.TIER_2  # Enhanced KYC
                else:  # basic
                    kyc_tier = KYCTier.TIER_1  # Basic KYC
                    
                documents = ['passport', 'driver_license', 'utility_bill']
                
                system.customer_manager.update_kyc_status(
                    customer.id,
                    kyc_status,
                    kyc_tier,
                    documents,
                    expiry_days=365 if kyc_status == KYCStatus.VERIFIED else None
                )
            
            customers.append(customer)
            
        except Exception as e:
            print(f"Error creating customer {i} ({client_data['external_id']}): {e}")
            continue
    
    print(f"Created {len(customers)} customers successfully")
    return customers

def create_accounts(system, customers, count=150):
    """Create demo accounts for customers"""
    print(f"Creating {count} accounts...")
    accounts = []
    
    # For now, just create savings and checking accounts to get the dashboard working
    product_types = [ProductType.SAVINGS, ProductType.CHECKING]
    type_weights = [50, 50]  # Equal split
    
    for i in range(count):
        customer = random.choice(customers)
        product_type = random.choices(product_types, weights=type_weights)[0]
        
        account_names = {
            ProductType.SAVINGS: f"{customer.first_name}'s Savings",
            ProductType.CHECKING: f"{customer.first_name}'s Checking"
        }
        
        try:
            # Deposit accounts
            interest_rate = Decimal(str(random.uniform(0.01, 0.05))) if product_type == ProductType.SAVINGS else None
            minimum_balance = Money(Decimal(str(random.choice([0, 100, 500, 1000]))), Currency.USD)
            
            account = system.account_manager.create_account(
                customer_id=customer.id,
                product_type=product_type,
                currency=Currency.USD,
                name=account_names[product_type],
                interest_rate=interest_rate,
                minimum_balance=minimum_balance
            )
            
            # Make initial deposits
            initial_balance = random.uniform(1000, 50000)
            system.transaction_processor.deposit(
                account.id,
                Money(Decimal(str(initial_balance)), Currency.USD),
                "Initial deposit",
                TransactionChannel.ONLINE
            )
            
            accounts.append(account)
            
        except Exception as e:
            print(f"Error creating account {i}: {e}")
            continue
    
    print(f"Created {len(accounts)} accounts successfully")
    return accounts

def create_transactions(system, accounts, count=500):
    """Create demo transactions"""
    print(f"Creating {count} transactions...")
    
    # Focus on deposit accounts for now
    deposit_accounts = [a for a in accounts if a.product_type in [ProductType.SAVINGS, ProductType.CHECKING]]
    
    transactions = []
    
    for i in range(count):
        try:
            # Choose transaction type based on weights
            tx_types = ['deposit', 'withdrawal', 'transfer']
            tx_weights = [40, 30, 30]
            tx_type = random.choices(tx_types, weights=tx_weights)[0]
            
            if tx_type == 'deposit' and deposit_accounts:
                account = random.choice(deposit_accounts)
                amount = Money(Decimal(str(random.uniform(50, 5000))), Currency.USD)
                description = random.choice(TRANSACTION_DESCRIPTIONS)
                
                system.transaction_processor.deposit(
                    account.id,
                    amount,
                    description,
                    random.choice(list(TransactionChannel))
                )
                transactions.append(f"Deposit: {amount} to {account.id}")
                
            elif tx_type == 'withdrawal' and deposit_accounts:
                account = random.choice(deposit_accounts)
                balance = system.ledger.get_balance(account.id)
                if balance.amount > 100:
                    max_withdrawal = min(float(balance.amount) - 100, 2000)
                    amount = Money(Decimal(str(random.uniform(50, max_withdrawal))), Currency.USD)
                    description = random.choice(TRANSACTION_DESCRIPTIONS)
                    
                    system.transaction_processor.withdraw(
                        account.id,
                        amount,
                        description,
                        random.choice(list(TransactionChannel))
                    )
                    transactions.append(f"Withdrawal: {amount} from {account.id}")
                    
            elif tx_type == 'transfer' and len(deposit_accounts) >= 2:
                from_account = random.choice(deposit_accounts)
                to_accounts = [a for a in deposit_accounts if a.id != from_account.id]
                to_account = random.choice(to_accounts)
                
                balance = system.ledger.get_balance(from_account.id)
                if balance.amount > 100:
                    max_transfer = min(float(balance.amount) - 100, 1000)
                    amount = Money(Decimal(str(random.uniform(50, max_transfer))), Currency.USD)
                    description = f"Transfer to {to_account.account_number}"
                    
                    system.transaction_processor.transfer(
                        from_account.id,
                        to_account.id,
                        amount,
                        description,
                        random.choice(list(TransactionChannel))
                    )
                    transactions.append(f"Transfer: {amount} from {from_account.id} to {to_account.id}")
                    
        except Exception as e:
            print(f"Error creating transaction {i}: {e}")
            continue
    
    print(f"Created {len(transactions)} transactions successfully")
    return transactions

def main():
    """Main seeding function"""
    print("🏦 Nexum Core Banking - Seed Data Generator")
    print("=" * 50)
    
    # Initialize the banking system manually for seeding
    system = BankingSystem(use_sqlite=True)
    
    try:
        # Create customers using shared fixtures
        customers = create_customers(system)
        
        if not customers:
            print("❌ No customers created, aborting seed process")
            return
        
        # Create accounts
        accounts = create_accounts(system, customers, 150)
        
        if not accounts:
            print("❌ No accounts created, aborting seed process")
            return
        
        # Create transactions
        transactions = create_transactions(system, accounts, 500)
        
        print("=" * 50)
        print("✅ Demo data generation completed!")
        print(f"📊 Summary:")
        print(f"   • {len(customers)} customers created")
        print(f"   • {len(accounts)} accounts created")
        print(f"   • {len(transactions)} transactions created")
        print("")
        print("🚀 Start the dashboard with:")
        print("   cd /Users/alexshrike/.openclaw/workspace/core-banking")
        print("   python -m dashboard")
        print("")
        print("🌐 Then visit: http://localhost:8890")
        
    except Exception as e:
        print(f"❌ Error during seeding: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()