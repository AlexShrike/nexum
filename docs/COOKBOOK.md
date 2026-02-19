# Nexum Cookbook

Real-world recipes for implementing common banking scenarios with Nexum. Each recipe includes complete setup instructions, code examples, and expected outputs.

---

## Table of Contents

1. [Set up a Microfinance Lender](#set-up-a-microfinance-lender)
2. [Set up a Digital Wallet](#set-up-a-digital-wallet)
3. [Add a New Payment Product](#add-a-new-payment-product)
4. [Implement KYC Workflow](#implement-kyc-workflow)
5. [Set up Multi-Tenant SaaS](#set-up-multi-tenant-saas)
6. [Monitor with Notifications](#monitor-with-notifications)
7. [Integrate with External Systems](#integrate-with-external-systems)

---

## Set up a Microfinance Lender

Create a complete microfinance operation with customer onboarding, loan products, disbursement, payments, and collections.

### Scenario Overview

**MicroLend Inc.** wants to provide small business loans to entrepreneurs in underserved markets. They need:
- Simple KYC process (basic ID verification)
- Loan products: $500-$10,000, 3-24 months, weekly payments
- Automated collections workflow
- SMS notifications for payment reminders

### Step 1: Configure Business Rules

```bash
# Set microfinance-specific business rules
export NEXUM_MAX_DAILY_TRANSACTION_LIMIT=5000.00
export NEXUM_MIN_ACCOUNT_BALANCE=0.00
export NEXUM_DEFAULT_CURRENCY=USD
export NEXUM_KYC_TIER_REQUIRED=TIER_1
export NEXUM_LOAN_GRACE_PERIOD_DAYS=7
export NEXUM_COLLECTION_ESCALATION_DAYS=14

# Enable SMS notifications
export NEXUM_TWILIO_ACCOUNT_SID=your_twilio_account_sid
export NEXUM_TWILIO_AUTH_TOKEN=your_twilio_auth_token
export NEXUM_TWILIO_FROM_NUMBER=+1234567890
```

### Step 2: Create Loan Products

```bash
# Create microloan product
curl -X POST http://localhost:8090/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "name": "Small Business Microloan",
    "product_type": "loan", 
    "currency": "USD",
    "description": "Short-term business loans for entrepreneurs",
    "product_code": "SBM001",
    "interest_rate": "0.24",
    "default_loan_term_months": 12,
    "max_loan_term_months": 24,
    "min_loan_amount": {
      "amount": "500.00",
      "currency": "USD"
    },
    "max_loan_amount": {
      "amount": "10000.00", 
      "currency": "USD"
    },
    "payment_frequency": "weekly",
    "late_payment_fee": {
      "amount": "25.00",
      "currency": "USD"
    },
    "grace_period_days": 7,
    "requires_kyc_tier": "tier_1"
  }'
```

**Expected response:**
```json
{
  "product_id": "prod_microloan_001",
  "name": "Small Business Microloan",
  "product_type": "loan",
  "interest_rate": "0.24",
  "status": "active",
  "created_at": "2024-02-19T15:32:00.000000"
}
```

### Step 3: Onboard Borrowers

```python
# Python script: onboard_borrower.py
import requests
import json

API_BASE = "http://localhost:8090"
JWT_TOKEN = "your_jwt_token"

def onboard_borrower(customer_data):
    """Complete borrower onboarding process"""
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {JWT_TOKEN}"
    }
    
    # Step 1: Create customer
    response = requests.post(f"{API_BASE}/customers", 
                           json=customer_data, headers=headers)
    customer = response.json()
    customer_id = customer["customer_id"]
    print(f"✓ Created customer: {customer_id}")
    
    # Step 2: Basic KYC verification
    kyc_data = {
        "status": "verified",
        "tier": "tier_1", 
        "documents": ["national_id", "proof_of_business"],
        "expiry_days": 365
    }
    
    response = requests.put(f"{API_BASE}/customers/{customer_id}/kyc",
                          json=kyc_data, headers=headers)
    print(f"✓ KYC verified: {response.json()['kyc_status']}")
    
    # Step 3: Create loan account
    account_data = {
        "customer_id": customer_id,
        "product_type": "loan",
        "currency": "USD",
        "name": "Business Loan Account"
    }
    
    response = requests.post(f"{API_BASE}/accounts",
                           json=account_data, headers=headers)
    account = response.json()
    print(f"✓ Created account: {account['account_id']}")
    
    return {
        "customer_id": customer_id,
        "account_id": account["account_id"],
        "kyc_status": "verified"
    }

# Example usage
borrower_data = {
    "first_name": "Maria",
    "last_name": "Santos",
    "email": "maria.santos@email.com",
    "phone": "+1-555-0123",
    "date_of_birth": "1985-08-15",
    "address": {
        "line1": "123 Market Street",
        "city": "Riverside", 
        "state": "CA",
        "postal_code": "92501",
        "country": "US"
    }
}

result = onboard_borrower(borrower_data)
print(f"Onboarding completed: {result}")
```

**Expected output:**
```
✓ Created customer: cust_maria_santos_001
✓ KYC verified: verified
✓ Created account: acc_loan_001
Onboarding completed: {'customer_id': 'cust_maria_santos_001', 'account_id': 'acc_loan_001', 'kyc_status': 'verified'}
```

### Step 4: Loan Origination and Disbursement

```bash
# Create loan application
curl -X POST http://localhost:8090/loans \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "customer_id": "cust_maria_santos_001",
    "terms": {
      "principal_amount": {
        "amount": "5000.00",
        "currency": "USD"  
      },
      "annual_interest_rate": "0.24",
      "term_months": 12,
      "payment_frequency": "weekly",
      "amortization_method": "equal_installment",
      "first_payment_date": "2024-02-26",
      "allow_prepayment": true,
      "grace_period_days": 7,
      "late_fee": {
        "amount": "25.00",
        "currency": "USD"
      }
    },
    "currency": "USD",
    "purpose": "Inventory purchase for grocery store",
    "collateral_description": "Store equipment and inventory"
  }'

# Expected response
{
  "loan_id": "loan_maria_001",
  "customer_id": "cust_maria_santos_001",
  "state": "originated",
  "terms": {
    "principal_amount": {"amount": "5000.00", "currency": "USD"},
    "weekly_payment": {"amount": "115.38", "currency": "USD"},
    "total_payments": 52,
    "total_interest": {"amount": "1000.00", "currency": "USD"}
  },
  "next_payment_date": "2024-02-26"
}

# Disburse loan to borrower's external account  
curl -X POST http://localhost:8090/loans/loan_maria_001/disburse \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "disbursement_method": "bank_transfer",
    "external_account": {
      "account_number": "12345678",
      "routing_number": "021000021",
      "bank_name": "First National Bank"
    },
    "disbursement_date": "2024-02-19"
  }'
```

### Step 5: Payment Processing and Collections

```python
# weekly_payment_processor.py
import requests
import json
from datetime import date, timedelta
from decimal import Decimal

def process_weekly_payments():
    """Process weekly loan payments and handle collections"""
    
    # Get all active loans  
    response = requests.get(f"{API_BASE}/loans?status=active", headers=headers)
    active_loans = response.json()["loans"]
    
    for loan in active_loans:
        loan_id = loan["loan_id"]
        next_payment_due = date.fromisoformat(loan["next_payment_date"])
        days_overdue = (date.today() - next_payment_due).days
        
        print(f"Processing loan {loan_id}, days overdue: {days_overdue}")
        
        if days_overdue == 1:
            # Send friendly reminder
            send_payment_reminder(loan, "friendly")
            
        elif days_overdue == 7:
            # Grace period ended - send formal notice
            send_payment_reminder(loan, "formal")
            
        elif days_overdue == 14:
            # Create collection case
            create_collection_case(loan)
            
        elif days_overdue > 30:
            # Escalate to manager
            escalate_collection_case(loan)

def send_payment_reminder(loan, reminder_type):
    """Send SMS payment reminder"""
    customer_id = loan["customer_id"]
    
    # Get customer phone number
    response = requests.get(f"{API_BASE}/customers/{customer_id}", headers=headers)
    customer = response.json()
    
    if reminder_type == "friendly":
        message = f"""
Hi {customer['first_name']}, your weekly payment of ${loan['weekly_payment']} 
is due today. Pay online at microlend.com/pay or visit our office. 
Questions? Call (555) 123-4567.
        """.strip()
    else:
        message = f"""
PAYMENT OVERDUE: {customer['first_name']}, your loan payment of 
${loan['weekly_payment']} was due {loan['days_past_due']} days ago. 
Please pay immediately to avoid late fees. Call (555) 123-4567.
        """.strip()
    
    # Send SMS via notification API
    notification_data = {
        "customer_id": customer_id,
        "template": "payment_reminder_sms",
        "channels": ["sms"],
        "data": {
            "customer_name": customer["first_name"],
            "payment_amount": loan["weekly_payment"],
            "days_overdue": loan.get("days_past_due", 0),
            "message": message
        }
    }
    
    requests.post(f"{API_BASE}/notifications/send", 
                 json=notification_data, headers=headers)
    print(f"✓ Sent {reminder_type} reminder to {customer['first_name']}")

def create_collection_case(loan):
    """Create collection case for overdue loan"""
    case_data = {
        "loan_id": loan["loan_id"],
        "customer_id": loan["customer_id"],
        "case_type": "overdue_loan",
        "priority": "medium",
        "outstanding_balance": loan["current_balance"],
        "days_past_due": loan["days_past_due"],
        "assigned_collector": "collector_001"
    }
    
    response = requests.post(f"{API_BASE}/collections/cases",
                           json=case_data, headers=headers)
    case = response.json()
    print(f"✓ Created collection case: {case['case_id']}")
    
    return case

# Run weekly payment processing
if __name__ == "__main__":
    process_weekly_payments()
```

### Step 6: Reporting and Analytics

```bash
# Get portfolio performance report
curl "http://localhost:8090/reports/portfolio-performance?start_date=2024-01-01&end_date=2024-02-19" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

**Expected response:**
```json
{
  "report_period": {
    "start_date": "2024-01-01",
    "end_date": "2024-02-19"
  },
  "portfolio_summary": {
    "total_loans_originated": 47,
    "total_principal_disbursed": {"amount": "235000.00", "currency": "USD"},
    "active_loans": 42,
    "paid_off_loans": 3,
    "defaulted_loans": 2,
    "current_portfolio_balance": {"amount": "198450.00", "currency": "USD"}
  },
  "performance_metrics": {
    "average_loan_size": {"amount": "5000.00", "currency": "USD"},
    "average_term_months": 12,
    "default_rate": 4.3,
    "portfolio_yield": 22.1,
    "collection_rate": 94.2
  },
  "aging_analysis": {
    "current": {"amount": "165340.00", "percentage": 83.3},
    "1_30_days": {"amount": "18750.00", "percentage": 9.4},
    "31_60_days": {"amount": "8970.00", "percentage": 4.5},
    "over_60_days": {"amount": "5390.00", "percentage": 2.7}
  }
}
```

---

## Set up a Digital Wallet

Build a digital wallet service with instant P2P transfers, merchant payments, and compliance monitoring.

### Scenario Overview

**PayFast Wallet** wants to offer a mobile-first digital wallet with:
- Instant account opening with minimal KYC
- P2P transfers with phone number lookup
- QR code payments for merchants
- Real-time fraud monitoring
- Integration with external payment rails

### Step 1: Configure Wallet Products

```bash
# Create digital wallet account product
curl -X POST http://localhost:8090/products \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "name": "PayFast Digital Wallet",
    "product_type": "checking",
    "currency": "USD", 
    "description": "Mobile digital wallet for payments and transfers",
    "product_code": "PFWALLET",
    "minimum_balance": {
      "amount": "0.00",
      "currency": "USD"
    },
    "daily_transaction_limit": {
      "amount": "2500.00",
      "currency": "USD"
    },
    "monthly_transaction_limit": {
      "amount": "10000.00", 
      "currency": "USD"
    },
    "transaction_fee": {
      "amount": "0.00",
      "currency": "USD"
    },
    "requires_kyc_tier": "tier_0",
    "allow_negative_balance": false,
    "instant_transfers": true
  }'
```

### Step 2: Quick Account Opening API

```python
# quick_wallet_signup.py
import requests
import json
import uuid

def create_wallet_account(phone_number, first_name, last_name, email=None):
    """Create wallet account with minimal KYC"""
    
    # Generate customer ID from phone number for uniqueness
    customer_data = {
        "first_name": first_name,
        "last_name": last_name,
        "phone": phone_number,
        "email": email or f"{phone_number.replace('+', '').replace('-', '')}@temp-email.com",
        "kyc_status": "none",  # Start with no KYC
        "metadata": {
            "signup_channel": "mobile_app",
            "signup_timestamp": "2024-02-19T15:32:00.000000",
            "device_id": str(uuid.uuid4())
        }
    }
    
    # Create customer
    response = requests.post(f"{API_BASE}/customers", 
                           json=customer_data, headers=headers)
    customer = response.json()
    customer_id = customer["customer_id"]
    
    # Create wallet account
    account_data = {
        "customer_id": customer_id,
        "product_type": "checking",
        "currency": "USD",
        "name": "PayFast Wallet",
        "daily_transaction_limit": {
            "amount": "500.00",  # Lower limit for unverified users
            "currency": "USD"
        }
    }
    
    response = requests.post(f"{API_BASE}/accounts",
                           json=account_data, headers=headers)
    account = response.json()
    
    # Create phone number lookup record for P2P transfers
    lookup_data = {
        "phone_number": phone_number,
        "account_id": account["account_id"],
        "customer_id": customer_id,
        "is_active": True
    }
    
    response = requests.post(f"{API_BASE}/phone-lookup",
                           json=lookup_data, headers=headers)
    
    print(f"✓ Wallet created for {first_name} {last_name}")
    print(f"  Customer ID: {customer_id}")
    print(f"  Account ID: {account['account_id']}")
    print(f"  Phone: {phone_number}")
    
    return {
        "customer_id": customer_id,
        "account_id": account["account_id"],
        "wallet_number": phone_number,
        "daily_limit": "500.00",
        "kyc_status": "none"
    }

# Create sample wallet accounts
wallets = [
    create_wallet_account("+1-555-0101", "Alice", "Johnson", "alice@email.com"),
    create_wallet_account("+1-555-0102", "Bob", "Wilson", "bob@email.com"),
    create_wallet_account("+1-555-0103", "Carol", "Davis", "carol@email.com")
]
```

### Step 3: P2P Transfer Implementation

```bash
# Send money by phone number
curl -X POST http://localhost:8090/transfers/p2p \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -d '{
    "sender_phone": "+1-555-0101",
    "recipient_phone": "+1-555-0102",
    "amount": {
      "amount": "50.00",
      "currency": "USD"
    },
    "description": "Lunch money",
    "memo": "Thanks for lunch!",
    "idempotency_key": "p2p_alice_to_bob_001"
  }'
```

**Expected response:**
```json
{
  "transfer_id": "xfer_p2p_001",
  "status": "completed",
  "sender": {
    "phone": "+1-555-0101",
    "name": "Alice J."
  },
  "recipient": {
    "phone": "+1-555-0102", 
    "name": "Bob W."
  },
  "amount": {"amount": "50.00", "currency": "USD"},
  "description": "Lunch money",
  "processing_time_ms": 1247,
  "created_at": "2024-02-19T15:35:00.000000"
}
```

### Step 4: QR Code Payment System

```python
# qr_payment_system.py
import qrcode
import json
import uuid
from decimal import Decimal

def generate_payment_qr(merchant_id, amount=None, description=None):
    """Generate QR code for merchant payment"""
    
    payment_data = {
        "type": "payment_request",
        "merchant_id": merchant_id,
        "amount": str(amount) if amount else None,
        "currency": "USD",
        "description": description,
        "qr_id": str(uuid.uuid4()),
        "expires_at": "2024-02-19T16:35:00.000000"  # 1 hour expiry
    }
    
    # Generate QR code
    qr_payload = json.dumps(payment_data)
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    
    qr_image = qr.make_image(fill_color="black", back_color="white")
    qr_filename = f"qr_payment_{payment_data['qr_id']}.png"
    qr_image.save(qr_filename)
    
    print(f"✓ Generated QR code: {qr_filename}")
    print(f"  Merchant: {merchant_id}")
    print(f"  Amount: ${amount or 'Variable'}")
    
    return payment_data

def process_qr_payment(qr_data, payer_account_id, actual_amount=None):
    """Process payment from QR code scan"""
    
    # Parse QR code data
    if isinstance(qr_data, str):
        qr_data = json.loads(qr_data)
    
    # Use QR amount or allow user to enter amount
    payment_amount = Decimal(qr_data["amount"]) if qr_data["amount"] else actual_amount
    
    if not payment_amount:
        raise ValueError("Payment amount required")
    
    # Create payment transaction
    payment_request = {
        "transaction_type": "payment",
        "from_account_id": payer_account_id,
        "to_account_id": qr_data["merchant_id"],
        "amount": {
            "amount": str(payment_amount),
            "currency": qr_data["currency"]
        },
        "description": f"QR Payment: {qr_data.get('description', 'Merchant Payment')}",
        "channel": "mobile",
        "reference": f"QR_{qr_data['qr_id']}",
        "metadata": {
            "payment_method": "qr_code",
            "qr_id": qr_data["qr_id"],
            "merchant_id": qr_data["merchant_id"]
        }
    }
    
    # Process payment
    response = requests.post(f"{API_BASE}/transactions",
                           json=payment_request, headers=headers)
    
    payment_result = response.json()
    print(f"✓ QR Payment processed: {payment_result['transaction_id']}")
    
    return payment_result

# Example usage
# Generate QR for coffee shop
coffee_shop_qr = generate_payment_qr(
    merchant_id="merch_coffee_corner_001",
    amount=Decimal("4.50"),
    description="Coffee Corner - Latte"
)

# Customer scans and pays
payment = process_qr_payment(coffee_shop_qr, "acc_alice_wallet_001")
```

### Step 5: Real-time Fraud Monitoring

```python
# fraud_monitoring.py
import requests
from decimal import Decimal
from datetime import datetime, timedelta

class WalletFraudMonitor:
    """Real-time fraud monitoring for wallet transactions"""
    
    def __init__(self, api_base, jwt_token):
        self.api_base = api_base
        self.headers = {"Authorization": f"Bearer {jwt_token}"}
    
    def check_transaction_risk(self, transaction_data):
        """Analyze transaction for fraud risk"""
        
        account_id = transaction_data.get("from_account_id")
        amount = Decimal(transaction_data["amount"]["amount"])
        
        risk_score = 0
        risk_factors = []
        
        # Check velocity (transactions per hour)
        velocity = self._check_velocity(account_id)
        if velocity > 10:
            risk_score += 30
            risk_factors.append(f"High velocity: {velocity} transactions in last hour")
        
        # Check amount patterns
        if amount > Decimal("1000"):
            risk_score += 20
            risk_factors.append(f"Large amount: ${amount}")
        
        # Check time of day (3AM-6AM is higher risk)
        hour = datetime.now().hour
        if 3 <= hour <= 6:
            risk_score += 15
            risk_factors.append("Unusual time: late night transaction")
        
        # Check new recipient
        if self._is_new_recipient(account_id, transaction_data.get("to_account_id")):
            risk_score += 10
            risk_factors.append("New recipient")
        
        # Determine risk level and action
        if risk_score >= 50:
            action = "block"
        elif risk_score >= 30:
            action = "review"
        else:
            action = "allow"
        
        return {
            "risk_score": risk_score,
            "risk_level": self._get_risk_level(risk_score),
            "action": action,
            "risk_factors": risk_factors
        }
    
    def _check_velocity(self, account_id):
        """Check transaction velocity for account"""
        one_hour_ago = datetime.now() - timedelta(hours=1)
        
        response = requests.get(
            f"{self.api_base}/transactions",
            params={
                "account_id": account_id,
                "since": one_hour_ago.isoformat(),
                "status": "completed"
            },
            headers=self.headers
        )
        
        transactions = response.json().get("transactions", [])
        return len(transactions)
    
    def _is_new_recipient(self, sender_account, recipient_account):
        """Check if recipient is new for this sender"""
        response = requests.get(
            f"{self.api_base}/transactions",
            params={
                "from_account_id": sender_account,
                "to_account_id": recipient_account,
                "limit": 1
            },
            headers=self.headers
        )
        
        transactions = response.json().get("transactions", [])
        return len(transactions) == 0
    
    def _get_risk_level(self, risk_score):
        """Convert risk score to level"""
        if risk_score >= 60:
            return "critical"
        elif risk_score >= 40:
            return "high"
        elif risk_score >= 20:
            return "medium"
        else:
            return "low"

# Integration with transaction processing
def process_wallet_transaction(transaction_data):
    """Process wallet transaction with fraud checking"""
    
    # Check for fraud risk
    fraud_monitor = WalletFraudMonitor(API_BASE, JWT_TOKEN)
    risk_analysis = fraud_monitor.check_transaction_risk(transaction_data)
    
    print(f"Risk Analysis: {risk_analysis}")
    
    if risk_analysis["action"] == "block":
        return {
            "status": "blocked",
            "reason": "Transaction blocked due to fraud risk",
            "risk_factors": risk_analysis["risk_factors"]
        }
    
    elif risk_analysis["action"] == "review":
        # Flag for manual review but allow transaction
        transaction_data["metadata"] = transaction_data.get("metadata", {})
        transaction_data["metadata"]["fraud_review_required"] = True
        transaction_data["metadata"]["risk_score"] = risk_analysis["risk_score"]
    
    # Process transaction
    response = requests.post(f"{API_BASE}/transactions",
                           json=transaction_data, headers=headers)
    
    result = response.json()
    result["fraud_check"] = risk_analysis
    
    return result
```

### Step 6: External Payment Rails Integration

```python
# external_payment_integration.py
import requests
import json

class PaymentRailsIntegration:
    """Integration with external payment networks"""
    
    def add_funds_from_bank_account(self, wallet_account_id, bank_account, amount):
        """Add funds to wallet from external bank account via ACH"""
        
        # Create ACH debit request
        ach_request = {
            "type": "ach_debit",
            "source_account": {
                "account_number": bank_account["account_number"],
                "routing_number": bank_account["routing_number"],
                "account_type": "checking",
                "account_holder_name": bank_account["account_holder_name"]
            },
            "destination_account_id": wallet_account_id,
            "amount": amount,
            "description": "Wallet funding",
            "processing_date": "2024-02-20"  # Next business day
        }
        
        response = requests.post(f"{API_BASE}/ach/debit",
                               json=ach_request, headers=headers)
        
        ach_transaction = response.json()
        
        print(f"✓ ACH debit initiated: {ach_transaction['ach_id']}")
        print(f"  Amount: ${amount['amount']}")
        print(f"  Expected settlement: {ach_transaction['settlement_date']}")
        
        return ach_transaction
    
    def send_funds_to_bank_account(self, wallet_account_id, bank_account, amount):
        """Send funds from wallet to external bank account"""
        
        # Verify wallet has sufficient funds
        balance_response = requests.get(f"{API_BASE}/accounts/{wallet_account_id}/balance",
                                      headers=headers)
        balance = balance_response.json()
        
        available_amount = Decimal(balance["available_balance"]["amount"])
        requested_amount = Decimal(amount["amount"])
        
        if available_amount < requested_amount:
            raise ValueError(f"Insufficient funds: ${available_amount} available, ${requested_amount} requested")
        
        # Create ACH credit request
        ach_request = {
            "type": "ach_credit",
            "source_account_id": wallet_account_id,
            "destination_account": {
                "account_number": bank_account["account_number"],
                "routing_number": bank_account["routing_number"],
                "account_type": bank_account["account_type"],
                "account_holder_name": bank_account["account_holder_name"]
            },
            "amount": amount,
            "description": "Wallet withdrawal",
            "processing_date": "2024-02-20"
        }
        
        response = requests.post(f"{API_BASE}/ach/credit",
                               json=ach_request, headers=headers)
        
        return response.json()

# Example: Customer adds money to wallet
bank_account = {
    "account_number": "1234567890",
    "routing_number": "021000021", 
    "account_type": "checking",
    "account_holder_name": "Alice Johnson"
}

payment_rails = PaymentRailsIntegration()
funding_result = payment_rails.add_funds_from_bank_account(
    wallet_account_id="acc_alice_wallet_001",
    bank_account=bank_account,
    amount={"amount": "200.00", "currency": "USD"}
)
```

---

## Add a New Payment Product

Create a custom payment product with specific business rules, fees, and behaviors.

### Scenario Overview

**Regional Bank** wants to launch a "Student Checking Account" with special features:
- No monthly maintenance fee for students under 25
- Free ATM withdrawals at partner networks
- Overdraft protection with parental account linking
- Cashback rewards on certain merchant categories
- Mobile check deposit with hold policies

### Step 1: Define Product Configuration

```python
# student_checking_product.py
from decimal import Decimal
from core_banking.products import ProductConfiguration, ProductType
from core_banking.currency import Money, Currency

def create_student_checking_product():
    """Create student checking account product configuration"""
    
    product = ProductConfiguration(
        name="Student Advantage Checking",
        product_type=ProductType.CHECKING,
        currency=Currency.USD,
        description="Fee-free checking account designed for students",
        product_code="STUDENT_CHK_001",
        
        # Balance requirements
        minimum_balance=Money(Decimal('0.00'), Currency.USD),
        minimum_balance_fee=None,  # No minimum balance fee
        
        # Transaction limits  
        daily_withdrawal_limit=Money(Decimal('800.00'), Currency.USD),
        daily_transaction_limit=Money(Decimal('3000.00'), Currency.USD),
        monthly_transaction_limit=Money(Decimal('20000.00'), Currency.USD),
        
        # Fees
        monthly_maintenance_fee=Money(Decimal('0.00'), Currency.USD),  # Free for students
        transaction_fee=None,  # No per-transaction fees
        overdraft_fee=Money(Decimal('25.00'), Currency.USD),
        overdraft_limit=Money(Decimal('200.00'), Currency.USD),
        
        # Special features
        allow_negative_balance=True,  # Overdraft protection
        auto_pay_fees_from_balance=False,  # Don't auto-pay from linked account
        send_low_balance_alerts=True,
        low_balance_alert_threshold=Money(Decimal('50.00'), Currency.USD),
        
        # Student-specific rules
        requires_kyc_tier=KYCTier.TIER_1,
        max_account_age_for_benefits=25,  # Benefits until age 25
        partner_atm_networks=["Allpoint", "MoneyPass", "SUM"],
        cashback_categories=["restaurants", "gas_stations", "bookstores"],
        cashback_rate=Decimal('0.01'),  # 1% cashback
        
        # Mobile deposit limits
        mobile_deposit_daily_limit=Money(Decimal('2000.00'), Currency.USD),
        mobile_deposit_check_hold_days=2,  # 2-day hold on mobile deposits
        
        # Parental account linking
        allow_parental_oversight=True,
        overdraft_source_account_required=True
    )
    
    return product

# Register product with the system
def register_student_product():
    """Register student checking product"""
    
    product = create_student_checking_product()
    
    # Save product configuration
    product_data = {
        "name": product.name,
        "product_type": product.product_type.value,
        "currency": product.currency.code,
        "description": product.description,
        "product_code": product.product_code,
        "configuration": product.__dict__
    }
    
    response = requests.post(f"{API_BASE}/products",
                           json=product_data, headers=headers)
    
    product_result = response.json()
    print(f"✓ Student product registered: {product_result['product_id']}")
    
    return product_result

# Register the product
student_product = register_student_product()
```

### Step 2: Custom Account Opening Logic

```python
# student_account_opening.py
from datetime import date, datetime
from decimal import Decimal

def open_student_checking_account(student_data, parental_data=None):
    """Open student checking account with special validation"""
    
    # Validate student eligibility
    birth_date = date.fromisoformat(student_data["date_of_birth"])
    age = (date.today() - birth_date).days // 365
    
    if age > 25:
        raise ValueError("Student checking account requires age 25 or under")
    
    if age < 18 and not parental_data:
        raise ValueError("Parental information required for minors")
    
    # Create student customer
    customer_data = {
        "first_name": student_data["first_name"],
        "last_name": student_data["last_name"],
        "email": student_data["email"],
        "phone": student_data["phone"],
        "date_of_birth": student_data["date_of_birth"],
        "address": student_data["address"],
        "metadata": {
            "customer_type": "student",
            "enrollment_status": student_data.get("enrollment_status", "enrolled"),
            "school_name": student_data.get("school_name"),
            "expected_graduation": student_data.get("expected_graduation")
        }
    }
    
    response = requests.post(f"{API_BASE}/customers",
                           json=customer_data, headers=headers)
    student = response.json()
    student_id = student["customer_id"]
    
    # Handle parental account for minors
    parental_account_id = None
    if age < 18 and parental_data:
        parental_account_id = create_parental_oversight_account(
            parental_data, student_id
        )
    
    # Create student checking account
    account_data = {
        "customer_id": student_id,
        "product_type": "checking",
        "currency": "USD",
        "name": "Student Advantage Checking",
        "product_code": "STUDENT_CHK_001",
        
        # Apply student-specific limits
        "daily_withdrawal_limit": {
            "amount": "800.00",
            "currency": "USD"
        },
        "overdraft_limit": {
            "amount": "200.00" if age >= 18 else "100.00",  # Lower for minors
            "currency": "USD"
        },
        
        # Link parental oversight if applicable
        "metadata": {
            "student_account": True,
            "student_age": age,
            "parental_oversight_account": parental_account_id,
            "benefits_expire_date": calculate_benefits_expiry(birth_date),
            "cashback_enabled": True,
            "mobile_deposit_enabled": age >= 16  # Mobile deposit for 16+
        }
    }
    
    response = requests.post(f"{API_BASE}/accounts",
                           json=account_data, headers=headers)
    account = response.json()
    
    # Set up overdraft protection if parental account exists
    if parental_account_id:
        setup_overdraft_protection(account["account_id"], parental_account_id)
    
    # Activate cashback rewards
    activate_cashback_rewards(account["account_id"])
    
    print(f"✓ Student checking account opened")
    print(f"  Student: {student['first_name']} {student['last_name']}")
    print(f"  Account: {account['account_id']}")
    print(f"  Age: {age}")
    print(f"  Parental oversight: {'Yes' if parental_account_id else 'No'}")
    
    return {
        "student_customer_id": student_id,
        "account_id": account["account_id"],
        "parental_account_id": parental_account_id,
        "benefits_expire_date": account["metadata"]["benefits_expire_date"]
    }

def calculate_benefits_expiry(birth_date):
    """Calculate when student benefits expire (25th birthday)"""
    birth_date = date.fromisoformat(birth_date) if isinstance(birth_date, str) else birth_date
    expiry_date = birth_date.replace(year=birth_date.year + 25)
    return expiry_date.isoformat()

def setup_overdraft_protection(student_account_id, parental_account_id):
    """Set up overdraft protection with parental account"""
    
    overdraft_config = {
        "protected_account_id": student_account_id,
        "funding_account_id": parental_account_id,
        "max_overdraft_amount": {
            "amount": "200.00",
            "currency": "USD"
        },
        "overdraft_fee": {
            "amount": "25.00", 
            "currency": "USD"
        },
        "notification_settings": {
            "notify_student": True,
            "notify_parent": True,
            "notification_threshold": {
                "amount": "50.00",
                "currency": "USD"
            }
        }
    }
    
    response = requests.post(f"{API_BASE}/overdraft-protection",
                           json=overdraft_config, headers=headers)
    
    return response.json()

# Example: Open account for college student
student_info = {
    "first_name": "Emma",
    "last_name": "Thompson",
    "email": "emma.thompson@university.edu",
    "phone": "+1-555-0199",
    "date_of_birth": "2002-09-15",  # 21 years old
    "address": {
        "line1": "123 College Avenue",
        "line2": "Dorm 4, Room 201",
        "city": "University City",
        "state": "CA",
        "postal_code": "90210",
        "country": "US"
    },
    "school_name": "State University",
    "enrollment_status": "full_time",
    "expected_graduation": "2026-05-15"
}

student_account = open_student_checking_account(student_info)
```

### Step 3: Implement Cashback Rewards

```python
# cashback_rewards.py
from decimal import Decimal, ROUND_HALF_UP

class CashbackRewardsEngine:
    """Manages cashback rewards for student checking accounts"""
    
    CASHBACK_CATEGORIES = {
        "restaurants": {"rate": Decimal("0.02"), "monthly_cap": Decimal("25.00")},
        "gas_stations": {"rate": Decimal("0.015"), "monthly_cap": Decimal("20.00")},
        "bookstores": {"rate": Decimal("0.05"), "monthly_cap": Decimal("50.00")},
        "streaming": {"rate": Decimal("0.01"), "monthly_cap": Decimal("10.00")},
        "default": {"rate": Decimal("0.005"), "monthly_cap": Decimal("5.00")}
    }
    
    def __init__(self, api_base, jwt_token):
        self.api_base = api_base
        self.headers = {"Authorization": f"Bearer {jwt_token}"}
    
    def calculate_cashback(self, transaction):
        """Calculate cashback for a transaction"""
        
        # Only calculate for debit transactions
        if transaction["transaction_type"] != "debit":
            return None
        
        account_id = transaction["account_id"]
        amount = Decimal(transaction["amount"]["amount"])
        merchant_category = transaction.get("metadata", {}).get("merchant_category", "default")
        
        # Check if account is eligible for cashback
        if not self._is_cashback_eligible(account_id):
            return None
        
        # Get cashback rate and cap for category
        category_config = self.CASHBACK_CATEGORIES.get(merchant_category, 
                                                      self.CASHBACK_CATEGORIES["default"])
        
        # Calculate cashback amount
        cashback_amount = (amount * category_config["rate"]).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # Check monthly cap
        monthly_cashback = self._get_monthly_cashback(account_id, merchant_category)
        remaining_cap = category_config["monthly_cap"] - monthly_cashback
        
        # Apply cap if necessary
        if cashback_amount > remaining_cap:
            cashback_amount = remaining_cap
        
        # Minimum cashback is $0.01
        if cashback_amount < Decimal('0.01'):
            return None
        
        return {
            "amount": cashback_amount,
            "currency": "USD",
            "category": merchant_category,
            "rate": category_config["rate"],
            "monthly_remaining": remaining_cap - cashback_amount
        }
    
    def award_cashback(self, account_id, transaction_id, cashback_data):
        """Award cashback to account"""
        
        # Create cashback credit transaction
        cashback_transaction = {
            "transaction_type": "credit",
            "to_account_id": account_id,
            "amount": {
                "amount": str(cashback_data["amount"]),
                "currency": cashback_data["currency"]
            },
            "description": f"Cashback reward - {cashback_data['category']}",
            "reference": f"CASHBACK_{transaction_id}",
            "channel": "system",
            "metadata": {
                "cashback_reward": True,
                "source_transaction_id": transaction_id,
                "category": cashback_data["category"],
                "cashback_rate": str(cashback_data["rate"])
            }
        }
        
        response = requests.post(f"{self.api_base}/transactions",
                               json=cashback_transaction, headers=self.headers)
        
        cashback_result = response.json()
        
        # Log cashback award
        print(f"✓ Cashback awarded: ${cashback_data['amount']} for {cashback_data['category']}")
        
        return cashback_result
    
    def _is_cashback_eligible(self, account_id):
        """Check if account is eligible for cashback"""
        response = requests.get(f"{self.api_base}/accounts/{account_id}",
                              headers=self.headers)
        account = response.json()
        
        return account.get("metadata", {}).get("cashback_enabled", False)
    
    def _get_monthly_cashback(self, account_id, category):
        """Get total cashback earned this month for category"""
        from datetime import date
        
        # Get first day of current month
        today = date.today()
        month_start = today.replace(day=1)
        
        # Query cashback transactions for this month and category
        response = requests.get(f"{self.api_base}/transactions", params={
            "account_id": account_id,
            "transaction_type": "credit",
            "description_contains": f"Cashback reward - {category}",
            "since": month_start.isoformat()
        }, headers=self.headers)
        
        transactions = response.json().get("transactions", [])
        
        total_cashback = sum(Decimal(tx["amount"]["amount"]) for tx in transactions)
        return total_cashback

# Integration with transaction processing
def process_transaction_with_cashback(transaction_data):
    """Process transaction and award cashback if applicable"""
    
    # Process the original transaction
    response = requests.post(f"{API_BASE}/transactions",
                           json=transaction_data, headers=headers)
    transaction = response.json()
    
    # Calculate and award cashback
    if transaction["status"] == "completed":
        cashback_engine = CashbackRewardsEngine(API_BASE, JWT_TOKEN)
        cashback_data = cashback_engine.calculate_cashback(transaction)
        
        if cashback_data:
            cashback_result = cashback_engine.award_cashback(
                transaction["account_id"],
                transaction["transaction_id"],
                cashback_data
            )
            
            transaction["cashback_awarded"] = cashback_data
    
    return transaction

# Example: Student buys textbooks (bookstore category - 5% cashback)
textbook_purchase = {
    "transaction_type": "debit",
    "from_account_id": "acc_emma_student_001",
    "amount": {
        "amount": "250.00",
        "currency": "USD"
    },
    "description": "University Bookstore - Textbooks",
    "channel": "debit_card",
    "metadata": {
        "merchant_category": "bookstores",
        "merchant_name": "University Bookstore",
        "card_present": True
    }
}

result = process_transaction_with_cashback(textbook_purchase)
print(f"Textbook purchase: ${result['amount']['amount']}")
print(f"Cashback earned: ${result.get('cashback_awarded', {}).get('amount', '0.00')}")
```

---

## Implement KYC Workflow

Create a comprehensive KYC (Know Your Customer) workflow with document collection, verification, and compliance tracking.

### Scenario Overview

**Credit Union** needs a KYC workflow that:
- Collects required documents based on account type and risk level
- Integrates with ID verification services (Jumio, Onfido, etc.)
- Tracks KYC status and expiration dates
- Supports different verification tiers
- Maintains compliance audit trail

### Step 1: Define KYC Workflow Configuration

```python
# kyc_workflow_config.py
from dataclasses import dataclass
from typing import List, Dict, Optional
from enum import Enum

class KYCTier(Enum):
    TIER_0 = "tier_0"  # No verification - limited functionality
    TIER_1 = "tier_1"  # Basic verification - standard accounts
    TIER_2 = "tier_2"  # Enhanced verification - higher limits  
    TIER_3 = "tier_3"  # Full verification - business accounts

class DocumentType(Enum):
    DRIVERS_LICENSE = "drivers_license"
    PASSPORT = "passport"
    NATIONAL_ID = "national_id"
    SSN_CARD = "ssn_card"
    PROOF_OF_ADDRESS = "proof_of_address"
    PROOF_OF_INCOME = "proof_of_income"
    EMPLOYER_LETTER = "employer_letter"
    BANK_STATEMENT = "bank_statement"
    BUSINESS_LICENSE = "business_license"
    ARTICLES_OF_INCORPORATION = "articles_of_incorporation"

@dataclass
class KYCRequirement:
    tier: KYCTier
    required_documents: List[DocumentType]
    optional_documents: List[DocumentType]
    verification_methods: List[str]
    transaction_limits: Dict[str, str]
    validity_days: int
    description: str

# Define KYC requirements for each tier
KYC_REQUIREMENTS = {
    KYCTier.TIER_0: KYCRequirement(
        tier=KYCTier.TIER_0,
        required_documents=[],
        optional_documents=[],
        verification_methods=["phone_verification"],
        transaction_limits={"daily": "500.00", "monthly": "2000.00"},
        validity_days=30,
        description="Basic phone verification only"
    ),
    
    KYCTier.TIER_1: KYCRequirement(
        tier=KYCTier.TIER_1,
        required_documents=[DocumentType.DRIVERS_LICENSE, DocumentType.SSN_CARD],
        optional_documents=[DocumentType.PROOF_OF_ADDRESS],
        verification_methods=["document_verification", "identity_verification"],
        transaction_limits={"daily": "5000.00", "monthly": "25000.00"},
        validity_days=365,
        description="Standard verification for personal accounts"
    ),
    
    KYCTier.TIER_2: KYCRequirement(
        tier=KYCTier.TIER_2,
        required_documents=[
            DocumentType.DRIVERS_LICENSE,
            DocumentType.SSN_CARD,
            DocumentType.PROOF_OF_ADDRESS,
            DocumentType.PROOF_OF_INCOME
        ],
        optional_documents=[DocumentType.BANK_STATEMENT, DocumentType.EMPLOYER_LETTER],
        verification_methods=["document_verification", "identity_verification", "address_verification"],
        transaction_limits={"daily": "25000.00", "monthly": "100000.00"},
        validity_days=730,
        description="Enhanced verification for high-value accounts"
    ),
    
    KYCTier.TIER_3: KYCRequirement(
        tier=KYCTier.TIER_3,
        required_documents=[
            DocumentType.BUSINESS_LICENSE,
            DocumentType.ARTICLES_OF_INCORPORATION,
            DocumentType.PROOF_OF_ADDRESS,
            DocumentType.BANK_STATEMENT
        ],
        optional_documents=[DocumentType.EMPLOYER_LETTER],
        verification_methods=[
            "document_verification", 
            "business_verification", 
            "beneficial_ownership_verification"
        ],
        transaction_limits={"daily": "100000.00", "monthly": "1000000.00"},
        validity_days=365,
        description="Full business verification"
    )
}

def get_kyc_requirements(account_type: str, customer_type: str = "individual") -> KYCRequirement:
    """Get KYC requirements based on account type and customer type"""
    
    # Define account type to KYC tier mapping
    ACCOUNT_KYC_MAPPING = {
        ("checking", "individual"): KYCTier.TIER_1,
        ("savings", "individual"): KYCTier.TIER_1,
        ("credit_line", "individual"): KYCTier.TIER_2,
        ("loan", "individual"): KYCTier.TIER_2,
        ("business_checking", "business"): KYCTier.TIER_3,
        ("business_savings", "business"): KYCTier.TIER_3,
        ("business_loan", "business"): KYCTier.TIER_3,
        ("wallet", "individual"): KYCTier.TIER_0
    }
    
    required_tier = ACCOUNT_KYC_MAPPING.get((account_type, customer_type), KYCTier.TIER_1)
    return KYC_REQUIREMENTS[required_tier]

# Usage
requirements = get_kyc_requirements("credit_line", "individual")
print(f"KYC Tier: {requirements.tier.value}")
print(f"Required docs: {[doc.value for doc in requirements.required_documents]}")
print(f"Transaction limits: {requirements.transaction_limits}")
```

### Step 2: Document Collection Workflow

```python
# kyc_document_workflow.py
import uuid
import base64
import requests
from datetime import datetime, timedelta

class KYCDocumentWorkflow:
    """Manages KYC document collection and verification workflow"""
    
    def __init__(self, api_base, jwt_token):
        self.api_base = api_base
        self.headers = {"Authorization": f"Bearer {jwt_token}"}
    
    def start_kyc_process(self, customer_id, target_tier, account_type="checking"):
        """Start KYC process for customer"""
        
        # Get requirements for target tier
        requirements = get_kyc_requirements(account_type)
        
        # Create KYC case
        kyc_case = {
            "customer_id": customer_id,
            "target_tier": target_tier,
            "account_type": account_type,
            "status": "document_collection",
            "required_documents": [doc.value for doc in requirements.required_documents],
            "optional_documents": [doc.value for doc in requirements.optional_documents],
            "verification_methods": requirements.verification_methods,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "case_id": str(uuid.uuid4())
        }
        
        # Save KYC case
        response = requests.post(f"{self.api_base}/kyc/cases",
                               json=kyc_case, headers=self.headers)
        
        case_result = response.json()
        
        # Send document collection instructions to customer
        self._send_document_instructions(customer_id, kyc_case)
        
        print(f"✓ KYC process started for customer {customer_id}")
        print(f"  Case ID: {case_result['case_id']}")
        print(f"  Target tier: {target_tier}")
        print(f"  Required documents: {len(kyc_case['required_documents'])}")
        
        return case_result
    
    def upload_document(self, case_id, document_type, file_data, filename):
        """Upload KYC document"""
        
        # Create document record
        document = {
            "case_id": case_id,
            "document_type": document_type,
            "filename": filename,
            "file_data": base64.b64encode(file_data).decode('utf-8'),
            "upload_timestamp": datetime.now().isoformat(),
            "status": "uploaded",
            "document_id": str(uuid.uuid4())
        }
        
        # Save document
        response = requests.post(f"{self.api_base}/kyc/documents",
                               json=document, headers=self.headers)
        
        document_result = response.json()
        
        # Update case status
        self._update_case_progress(case_id)
        
        print(f"✓ Document uploaded: {document_type}")
        print(f"  Document ID: {document_result['document_id']}")
        print(f"  Status: {document_result['status']}")
        
        return document_result
    
    def verify_documents(self, case_id, verification_service="jumio"):
        """Send documents for verification"""
        
        # Get case and documents
        case_response = requests.get(f"{self.api_base}/kyc/cases/{case_id}",
                                   headers=self.headers)
        case = case_response.json()
        
        docs_response = requests.get(f"{self.api_base}/kyc/documents?case_id={case_id}",
                                   headers=self.headers)
        documents = docs_response.json()["documents"]
        
        verification_results = []
        
        for document in documents:
            if document["status"] == "uploaded":
                # Send to verification service
                verification_result = self._verify_document_with_service(
                    document, verification_service
                )
                
                verification_results.append(verification_result)
                
                # Update document status
                update_data = {
                    "status": verification_result["status"],
                    "verification_result": verification_result,
                    "verified_at": datetime.now().isoformat()
                }
                
                requests.patch(f"{self.api_base}/kyc/documents/{document['document_id']}",
                             json=update_data, headers=self.headers)
        
        # Check if all documents are verified
        self._check_verification_completion(case_id)
        
        return verification_results
    
    def _verify_document_with_service(self, document, service="jumio"):
        """Verify document with external service (mock implementation)"""
        
        # This would integrate with actual verification services
        # Jumio, Onfido, IDology, etc.
        
        # Mock verification logic
        document_type = document["document_type"]
        
        if document_type == "drivers_license":
            return {
                "status": "verified",
                "verification_service": service,
                "confidence_score": 0.95,
                "extracted_data": {
                    "full_name": "John Michael Smith",
                    "date_of_birth": "1990-05-15",
                    "license_number": "DL123456789",
                    "expiry_date": "2028-05-15",
                    "state": "CA"
                },
                "verification_checks": {
                    "document_authenticity": "pass",
                    "face_match": "pass", 
                    "data_extraction": "pass",
                    "fraud_detection": "pass"
                }
            }
        
        elif document_type == "ssn_card":
            return {
                "status": "verified",
                "verification_service": service,
                "confidence_score": 0.92,
                "extracted_data": {
                    "full_name": "John Michael Smith",
                    "ssn": "XXX-XX-1234"  # Masked for security
                },
                "verification_checks": {
                    "ssn_validation": "pass",
                    "name_match": "pass"
                }
            }
        
        else:
            return {
                "status": "verified",
                "verification_service": service,
                "confidence_score": 0.88
            }
    
    def _check_verification_completion(self, case_id):
        """Check if KYC verification is complete"""
        
        # Get case and documents
        case_response = requests.get(f"{self.api_base}/kyc/cases/{case_id}",
                                   headers=self.headers)
        case = case_response.json()
        
        docs_response = requests.get(f"{self.api_base}/kyc/documents?case_id={case_id}",
                                   headers=self.headers)
        documents = docs_response.json()["documents"]
        
        # Check if all required documents are verified
        required_docs = set(case["required_documents"])
        verified_docs = set(doc["document_type"] for doc in documents 
                          if doc["status"] == "verified")
        
        if required_docs.issubset(verified_docs):
            # All required documents verified - complete KYC
            self._complete_kyc_verification(case_id)
        else:
            missing_docs = required_docs - verified_docs
            print(f"Missing documents: {list(missing_docs)}")
    
    def _complete_kyc_verification(self, case_id):
        """Complete KYC verification process"""
        
        # Update case status
        case_update = {
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "verification_result": "approved"
        }
        
        requests.patch(f"{self.api_base}/kyc/cases/{case_id}",
                     json=case_update, headers=self.headers)
        
        # Update customer KYC status
        case_response = requests.get(f"{self.api_base}/kyc/cases/{case_id}",
                                   headers=self.headers)
        case = case_response.json()
        
        customer_update = {
            "status": "verified",
            "tier": case["target_tier"],
            "verified_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=365)).isoformat()
        }
        
        requests.put(f"{self.api_base}/customers/{case['customer_id']}/kyc",
                   json=customer_update, headers=self.headers)
        
        # Send completion notification
        self._send_kyc_completion_notification(case["customer_id"], case["target_tier"])
        
        print(f"✓ KYC verification completed for case {case_id}")
        print(f"  Customer tier: {case['target_tier']}")
    
    def _send_kyc_completion_notification(self, customer_id, tier):
        """Send KYC completion notification to customer"""
        
        notification_data = {
            "customer_id": customer_id,
            "template": "kyc_verification_completed",
            "channels": ["email", "sms"],
            "data": {
                "verification_tier": tier,
                "completion_date": datetime.now().strftime("%B %d, %Y"),
                "new_limits": KYC_REQUIREMENTS[KYCTier(tier)].transaction_limits
            }
        }
        
        requests.post(f"{self.api_base}/notifications/send",
                     json=notification_data, headers=self.headers)

# Example usage: Complete KYC process
def example_kyc_process():
    """Example of complete KYC process"""
    
    kyc_workflow = KYCDocumentWorkflow(API_BASE, JWT_TOKEN)
    
    # Start KYC process
    kyc_case = kyc_workflow.start_kyc_process(
        customer_id="cust_john_smith_001",
        target_tier="tier_2",
        account_type="credit_line"
    )
    
    case_id = kyc_case["case_id"]
    
    # Simulate document uploads
    with open("drivers_license.jpg", "rb") as f:
        dl_data = f.read()
    
    with open("ssn_card.jpg", "rb") as f:
        ssn_data = f.read()
    
    # Upload documents
    kyc_workflow.upload_document(case_id, "drivers_license", dl_data, "dl.jpg")
    kyc_workflow.upload_document(case_id, "ssn_card", ssn_data, "ssn.jpg")
    
    # Verify documents
    verification_results = kyc_workflow.verify_documents(case_id)
    
    print("KYC process completed!")
    for result in verification_results:
        print(f"  {result['document_type']}: {result['status']}")

# Run example
example_kyc_process()
```

---

## Set up Multi-Tenant SaaS

Configure Nexum for multi-tenant deployment where multiple financial institutions share the same infrastructure with complete data isolation.

### Scenario Overview

**BankTech SaaS** wants to provide Nexum as a service to multiple community banks and credit unions with:
- Complete data isolation between tenants
- Tenant-specific configuration and branding
- Usage-based billing and quotas
- Centralized management console
- Tenant onboarding automation

### Step 1: Multi-Tenant Configuration

```bash
# Enable multi-tenant mode
export NEXUM_MULTI_TENANT_ENABLED=true
export NEXUM_TENANT_ISOLATION_STRATEGY=shared_table
export NEXUM_TENANT_HEADER_NAME=X-Tenant-ID
export NEXUM_TENANT_SUBDOMAIN_ENABLED=true
export NEXUM_DEFAULT_SUBSCRIPTION_TIER=basic

# Database configuration for multi-tenancy
export NEXUM_DATABASE_URL=postgresql://nexum_saas:password@localhost:5432/nexum_saas
export NEXUM_ENABLE_TENANT_QUOTAS=true
export NEXUM_ENABLE_USAGE_TRACKING=true
```

### Step 2: Tenant Management API

```python
# tenant_management.py
import requests
import json
from datetime import datetime, timedelta

class TenantManager:
    """Manages multi-tenant operations"""
    
    def __init__(self, api_base, admin_token):
        self.api_base = api_base
        self.headers = {"Authorization": f"Bearer {admin_token}"}
    
    def create_tenant(self, tenant_data):
        """Create a new tenant (financial institution)"""
        
        tenant_config = {
            "name": tenant_data["institution_name"],
            "code": tenant_data["institution_code"],
            "display_name": tenant_data["display_name"],
            "description": tenant_data.get("description", ""),
            "contact_email": tenant_data["admin_email"],
            "contact_phone": tenant_data.get("phone"),
            "subscription_tier": tenant_data.get("subscription_tier", "basic"),
            
            # Quotas based on subscription tier
            "max_users": self._get_user_quota(tenant_data.get("subscription_tier", "basic")),
            "max_accounts": self._get_account_quota(tenant_data.get("subscription_tier", "basic")),
            "max_daily_transactions": self._get_transaction_quota(tenant_data.get("subscription_tier", "basic")),
            
            # Tenant-specific settings
            "settings": {
                "default_currency": tenant_data.get("currency", "USD"),
                "timezone": tenant_data.get("timezone", "America/New_York"),
                "business_hours": tenant_data.get("business_hours", "09:00-17:00"),
                "allow_overdrafts": tenant_data.get("allow_overdrafts", True),
                "max_daily_transaction_limit": tenant_data.get("daily_limit", "10000.00"),
                "kyc_tier_required": tenant_data.get("kyc_requirement", "tier_1"),
                
                # Branding
                "logo_url": tenant_data.get("logo_url"),
                "primary_color": tenant_data.get("brand_color", "#2563eb"),
                "institution_website": tenant_data.get("website"),
                
                # Notification settings
                "email_from_address": f"noreply@{tenant_data['institution_code'].lower()}.banktech.com",
                "sms_enabled": tenant_data.get("sms_enabled", True),
                "email_enabled": tenant_data.get("email_enabled", True)
            }
        }
        
        response = requests.post(f"{self.api_base}/admin/tenants",
                               json=tenant_config, headers=self.headers)
        
        tenant_result = response.json()
        
        # Set up tenant subdomain
        if tenant_result["tenant_id"]:
            self._setup_tenant_subdomain(tenant_result["tenant_id"], tenant_data["institution_code"])
        
        # Create initial admin user for tenant
        admin_user = self._create_tenant_admin(tenant_result["tenant_id"], tenant_data)
        
        print(f"✓ Tenant created: {tenant_result['name']}")
        print(f"  Tenant ID: {tenant_result['tenant_id']}")
        print(f"  Code: {tenant_result['code']}")
        print(f"  Subdomain: {tenant_data['institution_code'].lower()}.banktech.com")
        print(f"  Admin user: {admin_user['username']}")
        
        return {
            **tenant_result,
            "admin_user": admin_user,
            "subdomain": f"{tenant_data['institution_code'].lower()}.banktech.com"
        }
    
    def _get_user_quota(self, tier):
        """Get user quota based on subscription tier"""
        quotas = {
            "free": 5,
            "basic": 25,
            "professional": 100,
            "enterprise": 500
        }
        return quotas.get(tier, 25)
    
    def _get_account_quota(self, tier):
        """Get account quota based on subscription tier"""
        quotas = {
            "free": 100,
            "basic": 1000,
            "professional": 10000,
            "enterprise": 100000
        }
        return quotas.get(tier, 1000)
    
    def _get_transaction_quota(self, tier):
        """Get daily transaction quota based on subscription tier"""
        quotas = {
            "free": 100,
            "basic": 1000,
            "professional": 10000,
            "enterprise": 100000
        }
        return quotas.get(tier, 1000)
    
    def _create_tenant_admin(self, tenant_id, tenant_data):
        """Create initial admin user for tenant"""
        
        admin_user = {
            "username": f"admin@{tenant_data['institution_code'].lower()}",
            "email": tenant_data["admin_email"],
            "full_name": tenant_data.get("admin_name", "Administrator"),
            "password": self._generate_secure_password(),
            "roles": ["admin"],
            "tenant_id": tenant_id,
            "is_active": True,
            "metadata": {
                "is_tenant_admin": True,
                "created_by_system": True
            }
        }
        
        # Create user with tenant context
        headers_with_tenant = {
            **self.headers,
            "X-Tenant-ID": tenant_id
        }
        
        response = requests.post(f"{self.api_base}/auth/users",
                               json=admin_user, headers=headers_with_tenant)
        
        user_result = response.json()
        
        # Send welcome email with login credentials
        self._send_tenant_welcome_email(tenant_id, admin_user, tenant_data)
        
        return user_result
    
    def _setup_tenant_subdomain(self, tenant_id, institution_code):
        """Set up DNS/routing for tenant subdomain"""
        
        # This would integrate with your DNS provider or load balancer
        # For demo purposes, just log the configuration needed
        
        subdomain_config = {
            "tenant_id": tenant_id,
            "subdomain": f"{institution_code.lower()}.banktech.com",
            "target": f"{self.api_base}",
            "tenant_header": tenant_id
        }
        
        print(f"  DNS Configuration needed:")
        print(f"    CNAME: {subdomain_config['subdomain']} -> banktech.com")
        print(f"    Routing rule: Add X-Tenant-ID: {tenant_id} header")
        
        return subdomain_config

def create_community_bank_tenant():
    """Example: Create tenant for Community Bank"""
    
    tenant_manager = TenantManager(API_BASE, ADMIN_JWT_TOKEN)
    
    tenant_data = {
        "institution_name": "First Community Bank of Riverside",
        "institution_code": "FCBR",
        "display_name": "FC Bank",
        "description": "Community bank serving Riverside County since 1952",
        "admin_email": "admin@firstcommunitybank.com",
        "admin_name": "Sarah Johnson",
        "phone": "+1-555-0123",
        "website": "https://www.firstcommunitybank.com",
        "currency": "USD",
        "timezone": "America/Los_Angeles",
        "subscription_tier": "professional",
        "logo_url": "https://fcbank.com/logo.png",
        "brand_color": "#1e3a8a",
        "daily_limit": "25000.00",
        "allow_overdrafts": True,
        "kyc_requirement": "tier_2",
        "sms_enabled": True,
        "email_enabled": True
    }
    
    tenant = tenant_manager.create_tenant(tenant_data)
    return tenant

# Create example tenant
community_bank = create_community_bank_tenant()
```

### Step 3: Tenant-Aware API Middleware

```python
# tenant_middleware.py
import jwt
from fastapi import Request, HTTPException
from contextlib import asynccontextmanager

class TenantMiddleware:
    """Middleware for tenant context management"""
    
    def __init__(self, tenant_manager):
        self.tenant_manager = tenant_manager
    
    async def __call__(self, request: Request, call_next):
        """Process request with tenant context"""
        
        # Extract tenant ID from request
        tenant_id = await self._extract_tenant_id(request)
        
        if tenant_id:
            # Validate tenant exists and is active
            tenant = self.tenant_manager.get_tenant(tenant_id)
            if not tenant or not tenant.is_active:
                raise HTTPException(status_code=403, detail="Tenant not active")
            
            # Set tenant context
            with tenant_context(tenant_id):
                # Add tenant info to request state
                request.state.tenant_id = tenant_id
                request.state.tenant = tenant
                
                response = await call_next(request)
                
                # Add tenant-specific response headers
                response.headers["X-Tenant-ID"] = tenant_id
                response.headers["X-Tenant-Name"] = tenant.display_name
                
                return response
        else:
            # No tenant context - super admin mode
            response = await call_next(request)
            return response
    
    async def _extract_tenant_id(self, request: Request) -> str:
        """Extract tenant ID from various sources"""
        
        # Method 1: X-Tenant-ID header (highest priority)
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            return tenant_id
        
        # Method 2: Subdomain extraction
        host = request.url.hostname
        if host and "." in host:
            subdomain = host.split(".")[0]
            if subdomain not in ["www", "api", "admin"]:
                # Look up tenant by subdomain/code
                tenant = self.tenant_manager.get_tenant_by_code(subdomain.upper())
                if tenant:
                    return tenant.id
        
        # Method 3: JWT token tenant claim
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, verify=False)  # In production, verify signature
                return payload.get("tenant_id")
            except:
                pass
        
        return None

# Integration with FastAPI
from fastapi import FastAPI, Depends
from core_banking.tenancy import get_current_tenant, TenantManager

app = FastAPI()
tenant_middleware = TenantMiddleware(TenantManager(storage))

@app.middleware("http")
async def tenant_middleware_func(request: Request, call_next):
    return await tenant_middleware(request, call_next)

@app.get("/customers")
async def list_customers(tenant_id: str = Depends(get_current_tenant)):
    """List customers for current tenant"""
    
    # This automatically filters by tenant_id due to TenantAwareStorage
    customers = customer_manager.list_customers()
    
    return {
        "tenant_id": tenant_id,
        "customers": customers
    }

@app.post("/accounts")
async def create_account(account_data: CreateAccountRequest, 
                        tenant_id: str = Depends(get_current_tenant)):
    """Create account in tenant context"""
    
    # Validate tenant quotas
    if not quota_manager.check_quota(tenant_id, "accounts", 1):
        raise HTTPException(status_code=429, detail="Account quota exceeded")
    
    account = account_manager.create_account(account_data)
    
    # Increment usage counter
    quota_manager.increment_usage(tenant_id, "accounts", 1)
    
    return account
```

### Step 4: Usage Tracking and Billing

```python
# usage_tracking.py
from datetime import datetime, date, timedelta
from decimal import Decimal
import calendar

class UsageTracker:
    """Tracks tenant usage for billing purposes"""
    
    def __init__(self, storage):
        self.storage = storage
        
    def track_api_call(self, tenant_id, endpoint, method="GET"):
        """Track API call for billing"""
        
        usage_record = {
            "tenant_id": tenant_id,
            "usage_type": "api_call",
            "resource": f"{method} {endpoint}",
            "quantity": 1,
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat()
        }
        
        self.storage.save("usage_records", str(uuid.uuid4()), usage_record)
    
    def track_transaction(self, tenant_id, transaction_type, amount):
        """Track transaction processing for billing"""
        
        usage_record = {
            "tenant_id": tenant_id,
            "usage_type": "transaction_processing",
            "resource": transaction_type,
            "quantity": 1,
            "amount": str(amount),
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat()
        }
        
        self.storage.save("usage_records", str(uuid.uuid4()), usage_record)
    
    def track_storage(self, tenant_id, bytes_used):
        """Track storage usage for billing"""
        
        usage_record = {
            "tenant_id": tenant_id,
            "usage_type": "storage",
            "resource": "database_storage",
            "quantity": bytes_used,
            "timestamp": datetime.now().isoformat(),
            "date": date.today().isoformat()
        }
        
        self.storage.save("usage_records", str(uuid.uuid4()), usage_record)
    
    def generate_monthly_bill(self, tenant_id, year, month):
        """Generate monthly usage bill for tenant"""
        
        # Get usage records for the month
        month_start = date(year, month, 1)
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        
        usage_records = self.storage.find("usage_records", {
            "tenant_id": tenant_id,
            "date_gte": month_start.isoformat(),
            "date_lte": month_end.isoformat()
        })
        
        # Calculate costs based on usage
        billing_rates = {
            "api_call": Decimal("0.001"),      # $0.001 per API call
            "transaction_processing": Decimal("0.10"),  # $0.10 per transaction
            "storage": Decimal("0.000001"),    # $0.000001 per byte per month
        }
        
        usage_summary = {}
        total_cost = Decimal("0.00")
        
        for record in usage_records:
            usage_type = record["usage_type"]
            quantity = record["quantity"]
            
            if usage_type not in usage_summary:
                usage_summary[usage_type] = {
                    "quantity": 0,
                    "rate": billing_rates.get(usage_type, Decimal("0")),
                    "cost": Decimal("0.00")
                }
            
            usage_summary[usage_type]["quantity"] += quantity
            usage_summary[usage_type]["cost"] = (
                usage_summary[usage_type]["quantity"] * 
                usage_summary[usage_type]["rate"]
            )
            
            total_cost += usage_summary[usage_type]["rate"] * Decimal(str(quantity))
        
        # Generate bill
        bill = {
            "tenant_id": tenant_id,
            "billing_period": f"{year}-{month:02d}",
            "usage_summary": usage_summary,
            "total_cost": str(total_cost),
            "currency": "USD",
            "generated_at": datetime.now().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(),
            "status": "pending"
        }
        
        # Save bill
        bill_id = f"bill_{tenant_id}_{year}_{month:02d}"
        self.storage.save("billing_records", bill_id, bill)
        
        print(f"✓ Monthly bill generated for tenant {tenant_id}")
        print(f"  Period: {year}-{month:02d}")
        print(f"  Total cost: ${total_cost}")
        
        # Send bill to tenant
        self._send_bill_notification(tenant_id, bill)
        
        return bill
    
    def _send_bill_notification(self, tenant_id, bill):
        """Send billing notification to tenant"""
        
        tenant = tenant_manager.get_tenant(tenant_id)
        
        notification_data = {
            "recipient": tenant.contact_email,
            "template": "monthly_bill",
            "data": {
                "tenant_name": tenant.name,
                "billing_period": bill["billing_period"],
                "total_cost": bill["total_cost"],
                "due_date": bill["due_date"],
                "usage_summary": bill["usage_summary"]
            }
        }
        
        # Send email notification
        requests.post(f"{API_BASE}/notifications/send-email",
                     json=notification_data, headers=headers)

# Integration with API endpoints
usage_tracker = UsageTracker(storage)

@app.middleware("http")
async def usage_tracking_middleware(request: Request, call_next):
    """Track API usage for billing"""
    
    # Get tenant ID from request
    tenant_id = getattr(request.state, 'tenant_id', None)
    
    if tenant_id:
        # Track API call
        usage_tracker.track_api_call(
            tenant_id, 
            request.url.path, 
            request.method
        )
    
    response = await call_next(request)
    return response

# Monthly billing job
def run_monthly_billing():
    """Generate bills for all tenants"""
    
    today = date.today()
    last_month = today.replace(day=1) - timedelta(days=1)
    
    # Get all active tenants
    tenants = tenant_manager.list_tenants(is_active=True)
    
    for tenant in tenants:
        try:
            bill = usage_tracker.generate_monthly_bill(
                tenant.id, 
                last_month.year, 
                last_month.month
            )
            print(f"✓ Bill generated for {tenant.name}: ${bill['total_cost']}")
        except Exception as e:
            print(f"✗ Failed to generate bill for {tenant.name}: {e}")

# Schedule monthly billing (would use cron in production)
run_monthly_billing()
```

This comprehensive cookbook provides practical, real-world examples of implementing common banking scenarios with Nexum, complete with code examples, API calls, and expected outputs.