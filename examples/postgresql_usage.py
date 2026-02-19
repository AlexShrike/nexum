#!/usr/bin/env python3
"""
Example: Using PostgreSQL backend with ACID transactions

This example demonstrates how to use the new PostgreSQL storage backend
with atomic transactions for production banking operations.
"""

import os
import sys
from decimal import Decimal
from datetime import datetime, timezone, date

# Add the core banking module to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core_banking.config import NexumConfig
from core_banking.storage import PostgreSQLStorage, InMemoryStorage
from core_banking.migrations import MigrationManager
from core_banking.currency import Money, Currency
from core_banking.customers import CustomerManager
from core_banking.accounts import AccountManager, ProductType
from core_banking.transactions import TransactionProcessor, TransactionType, TransactionChannel


def main():
    print("🏦 Nexum Core Banking - PostgreSQL Production Example")
    print("=" * 60)
    
    # 1. Configuration
    print("\n1. 🔧 Configuration Setup")
    config = NexumConfig()
    print(f"   Database URL: {config.database_url}")
    print(f"   Log Level: {config.log_level}")
    
    # 2. Storage Backend Selection
    print("\n2. 💾 Storage Backend Selection")
    try:
        if config.database_url.startswith('postgresql://'):
            print("   Using PostgreSQL backend (production)")
            storage = PostgreSQLStorage(config.database_url)
            backend_type = "PostgreSQL"
        else:
            print("   Using InMemory backend (development)")
            storage = InMemoryStorage()
            backend_type = "InMemory"
    except ImportError:
        print("   PostgreSQL not available, using InMemory backend")
        storage = InMemoryStorage()
        backend_type = "InMemory"
    except Exception as e:
        print(f"   Database connection failed: {e}")
        print("   Falling back to InMemory backend")
        storage = InMemoryStorage()
        backend_type = "InMemory"
    
    # 3. Database Migrations
    print(f"\n3. 🔄 Database Migrations ({backend_type})")
    migration_manager = MigrationManager(storage)
    
    status = migration_manager.get_migration_status()
    print(f"   Current version: {status['current_version']}")
    print(f"   Latest version: {status['latest_version']}")
    print(f"   Pending migrations: {status['pending_count']}")
    
    if status['needs_migration']:
        print("   Applying pending migrations...")
        applied = migration_manager.migrate_up()
        print(f"   ✅ Applied {len(applied)} migrations")
    else:
        print("   ✅ Database is up to date")
    
    # 4. Initialize Banking System
    print(f"\n4. 🏗️  Banking System Initialization")
    customer_manager = CustomerManager(storage)
    account_manager = AccountManager(storage)
    transaction_processor = TransactionProcessor(storage)
    
    print("   ✅ Banking system initialized")
    
    # 5. Atomic Business Operations
    print(f"\n5. ⚡ Atomic Business Operations")
    
    try:
        # Use atomic transaction for creating customer and account
        with storage.atomic():
            print("   Creating customer and account atomically...")
            
            # Create customer
            customer_data = {
                'first_name': 'John',
                'last_name': 'Doe',
                'email': 'john.doe@example.com',
                'phone': '+1-555-0123',
                'date_of_birth': '1985-06-15'
            }
            
            customer = customer_manager.create_customer(**customer_data)
            print(f"   ✅ Customer created: {customer.id}")
            
            # Create checking account
            account = account_manager.create_account(
                customer_id=customer.id,
                product_type=ProductType.CHECKING,
                currency=Currency.USD,
                initial_balance=Money(Decimal('1000.00'), Currency.USD)
            )
            print(f"   ✅ Account created: {account.id}")
            
            print("   ✅ Customer and account created atomically")
    
    except Exception as e:
        print(f"   ❌ Transaction failed: {e}")
        print("   🔄 All changes rolled back automatically")
    
    # 6. Atomic Transaction Processing
    print(f"\n6. 💳 Atomic Transaction Processing")
    
    try:
        # Create a deposit transaction
        deposit_transaction = transaction_processor.create_transaction(
            transaction_type=TransactionType.DEPOSIT,
            amount=Money(Decimal('500.00'), Currency.USD),
            description="Salary deposit",
            channel=TransactionChannel.ACH,
            to_account_id=account.id,
            reference="SAL-2024-001"
        )
        
        print(f"   Transaction created: {deposit_transaction.id}")
        print(f"   Status: {deposit_transaction.state}")
        
        # Process transaction atomically (this uses the atomic() context internally)
        processed_transaction = transaction_processor.process_transaction(deposit_transaction.id)
        
        print(f"   ✅ Transaction processed: {processed_transaction.state}")
        print(f"   Journal Entry: {processed_transaction.journal_entry_id}")
        
        # Check account balance
        updated_account = account_manager.get_account(account.id)
        print(f"   💰 Updated balance: {updated_account.balance}")
        
    except Exception as e:
        print(f"   ❌ Transaction processing failed: {e}")
    
    # 7. System Status
    print(f"\n7. 📊 System Status")
    print(f"   Storage Backend: {backend_type}")
    print(f"   Migration Version: {migration_manager.get_current_version()}")
    print(f"   Total Customers: {len(customer_manager.list_customers())}")
    print(f"   Total Accounts: {len(account_manager.list_accounts())}")
    
    # 8. Cleanup
    print(f"\n8. 🧹 Cleanup")
    storage.close()
    print("   ✅ Storage connection closed")
    
    print(f"\n🎉 Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()