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
from core_banking.loans import LoanManager, LoanTerms, PaymentFrequency, AmortizationMethod
from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage

def debug_loan_state():
    print("=== DEBUG: Loan State After Save/Load ===")
    
    # Initialize system
    storage = InMemoryStorage()
    audit_trail = AuditTrail(storage)
    ledger = GeneralLedger(storage, audit_trail)
    customer_manager = CustomerManager(storage, audit_trail)
    account_manager = AccountManager(storage, ledger, audit_trail)
    compliance_engine = ComplianceEngine(storage, customer_manager, audit_trail)
    transaction_processor = TransactionProcessor(storage, ledger, account_manager, customer_manager, compliance_engine, audit_trail)
    loan_manager = LoanManager(storage, account_manager, transaction_processor, audit_trail)
    
    # Create customer and upgrade
    customer = customer_manager.create_customer(
        first_name="Test",
        last_name="Customer", 
        email="test@example.com"
    )
    customer_manager.update_kyc_status(customer.id, KYCStatus.VERIFIED, KYCTier.TIER_2)
    
    # Create disbursement account
    disbursement_account = account_manager.create_account(
        customer_id=customer.id,
        product_type=ProductType.CHECKING,
        currency=Currency.USD,
        name="Disbursement Account"
    )
    
    # Create loan terms
    past_date = date.today() - timedelta(days=15)
    terms = LoanTerms(
        principal_amount=Money(Decimal('4000.00'), Currency.USD),
        annual_interest_rate=Decimal('0.07'),
        term_months=48,
        payment_frequency=PaymentFrequency.MONTHLY,
        amortization_method=AmortizationMethod.EQUAL_INSTALLMENT,
        first_payment_date=past_date,
        grace_period_days=5
    )
    
    # Originate loan
    loan = loan_manager.originate_loan(
        customer_id=customer.id,
        terms=terms,
        currency=Currency.USD
    )
    print(f"After origination - State: {loan.state}, is_active: {loan.is_active}")
    
    # Disburse loan
    loan_manager.disburse_loan(loan.id, disbursement_account.id)
    
    # Get loan after disbursement
    loan_after_disbursement = loan_manager.get_loan(loan.id)
    print(f"After disbursement - State: {loan_after_disbursement.state}, is_active: {loan_after_disbursement.is_active}")
    
    # Manually set past due and save
    loan_after_disbursement.days_past_due = 10
    print(f"Before save - State: {loan_after_disbursement.state}, days_past_due: {loan_after_disbursement.days_past_due}, is_active: {loan_after_disbursement.is_active}")
    
    loan_manager._save_loan(loan_after_disbursement)
    
    # Load loan back from storage
    loan_reloaded = loan_manager.get_loan(loan.id)
    print(f"After reload - State: {loan_reloaded.state}, days_past_due: {loan_reloaded.days_past_due}, is_active: {loan_reloaded.is_active}")
    
    # Check what states are considered active
    from core_banking.loans import LoanState
    print(f"DISBURSED state: {LoanState.DISBURSED}")
    print(f"ACTIVE state: {LoanState.ACTIVE}")
    print(f"States that are active: {[state for state in LoanState if loan_reloaded.state in [LoanState.DISBURSED, LoanState.ACTIVE]]}")

if __name__ == "__main__":
    debug_loan_state()