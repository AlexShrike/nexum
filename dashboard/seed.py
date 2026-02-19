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

from core_banking.api_old import banking_system
from core_banking.currency import Money, Currency
from core_banking.accounts import ProductType
from core_banking.customers import KYCStatus, KYCTier, Address
from core_banking.transactions import TransactionType, TransactionChannel
from core_banking.loans import LoanTerms, PaymentFrequency, AmortizationMethod, LoanState
from core_banking.credit import TransactionCategory

# Sample data
FIRST_NAMES = [
    'James', 'Mary', 'John', 'Patricia', 'Robert', 'Jennifer', 'Michael', 'Linda',
    'William', 'Elizabeth', 'David', 'Barbara', 'Richard', 'Susan', 'Joseph', 'Jessica',
    'Thomas', 'Sarah', 'Christopher', 'Karen', 'Charles', 'Nancy', 'Daniel', 'Lisa',
    'Matthew', 'Betty', 'Anthony', 'Helen', 'Mark', 'Sandra', 'Donald', 'Donna',
    'Steven', 'Carol', 'Paul', 'Ruth', 'Andrew', 'Sharon', 'Joshua', 'Michelle',
    'Kenneth', 'Laura', 'Kevin', 'Sarah', 'Brian', 'Kimberly', 'George', 'Deborah',
    'Edward', 'Dorothy', 'Ronald', 'Lisa', 'Timothy', 'Nancy', 'Jason', 'Karen',
    'Jeffrey', 'Betty', 'Ryan', 'Helen', 'Jacob', 'Sandra', 'Gary', 'Donna',
    'Nicholas', 'Carol', 'Eric', 'Ruth', 'Jonathan', 'Sharon', 'Stephen', 'Michelle',
    'Larry', 'Laura', 'Justin', 'Sarah', 'Scott', 'Kimberly', 'Brandon', 'Deborah',
    'Benjamin', 'Dorothy', 'Samuel', 'Lisa', 'Gregory', 'Nancy', 'Frank', 'Karen',
    'Raymond', 'Betty', 'Alexander', 'Helen', 'Patrick', 'Sandra', 'Jack', 'Donna',
    'Dennis', 'Carol', 'Jerry', 'Ruth', 'Tyler', 'Sharon', 'Aaron', 'Michelle'
]

LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
    'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
    'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson',
    'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker',
    'Young', 'Allen', 'King', 'Wright', 'Scott', 'Torres', 'Nguyen', 'Hill',
    'Flores', 'Green', 'Adams', 'Nelson', 'Baker', 'Hall', 'Rivera', 'Campbell',
    'Mitchell', 'Carter', 'Roberts', 'Gomez', 'Phillips', 'Evans', 'Turner', 'Diaz',
    'Parker', 'Cruz', 'Edwards', 'Collins', 'Reyes', 'Stewart', 'Morris', 'Morales',
    'Murphy', 'Cook', 'Rogers', 'Gutierrez', 'Ortiz', 'Morgan', 'Cooper', 'Peterson',
    'Bailey', 'Reed', 'Kelly', 'Howard', 'Ramos', 'Kim', 'Cox', 'Ward', 'Richardson',
    'Watson', 'Brooks', 'Chavez', 'Wood', 'James', 'Bennett', 'Gray', 'Mendoza'
]

CITIES = [
    'New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia',
    'San Antonio', 'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville',
    'Fort Worth', 'Columbus', 'Charlotte', 'San Francisco', 'Indianapolis',
    'Seattle', 'Denver', 'Washington', 'Boston', 'El Paso', 'Nashville',
    'Detroit', 'Oklahoma City', 'Portland', 'Las Vegas', 'Memphis', 'Louisville',
    'Baltimore', 'Milwaukee', 'Albuquerque', 'Tucson', 'Fresno', 'Sacramento',
    'Kansas City', 'Long Beach', 'Mesa', 'Atlanta', 'Colorado Springs', 'Virginia Beach',
    'Raleigh', 'Omaha', 'Miami', 'Oakland', 'Minneapolis', 'Tulsa', 'Wichita',
    'New Orleans', 'Arlington'
]

STATES = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA', 'HI', 'ID',
    'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS',
    'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK',
    'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
]

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

def create_customers(system, count=100):
    """Create demo customers with realistic data"""
    print(f"Creating {count} customers...")
    customers = []
    
    for i in range(count):
        first_name = random.choice(FIRST_NAMES)
        last_name = random.choice(LAST_NAMES)
        
        # Create email based on name
        email_name = f"{first_name.lower()}.{last_name.lower()}"
        email_domain = random.choice(['gmail.com', 'yahoo.com', 'outlook.com', 'company.com'])
        email = f"{email_name}{random.randint(1, 999)}@{email_domain}"
        
        # Random phone number
        phone = f"+1-{random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}"
        
        # Random date of birth (18-80 years old)
        birth_year = random.randint(1943, 2005)
        birth_month = random.randint(1, 12)
        birth_day = random.randint(1, 28)
        date_of_birth = datetime(birth_year, birth_month, birth_day)
        
        # Random address
        address = Address(
            line1=f"{random.randint(100, 9999)} {random.choice(['Main', 'Oak', 'Pine', 'Park', 'First', 'Second', 'Third'])} {random.choice(['St', 'Ave', 'Blvd', 'Dr', 'Way'])}",
            line2=random.choice([None, None, None, f"Apt {random.randint(1, 200)}", f"Suite {random.randint(100, 999)}"]),
            city=random.choice(CITIES),
            state=random.choice(STATES),
            postal_code=f"{random.randint(10000, 99999)}",
            country="US"
        )
        
        try:
            customer = system.customer_manager.create_customer(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone=phone,
                date_of_birth=date_of_birth,
                address=address
            )
            
            # Set random KYC status
            kyc_statuses = list(KYCStatus)
            kyc_weights = [10, 20, 60, 5, 5]  # More verified customers
            kyc_status = random.choices(kyc_statuses, weights=kyc_weights)[0]
            
            if kyc_status != KYCStatus.NONE:
                kyc_tiers = list(KYCTier)
                kyc_tier = random.choice(kyc_tiers)
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
            print(f"Error creating customer {i}: {e}")
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
    
    system = banking_system
    
    try:
        # Create customers
        customers = create_customers(system, 100)
        
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