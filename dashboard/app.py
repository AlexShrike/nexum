"""
Nexum Core Banking Dashboard - FastAPI Backend
Comprehensive banking dashboard with loans, credit lines, collections, and products
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from decimal import Decimal
import json

# Import core banking modules
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from core_banking.storage import SQLiteStorage
from core_banking.audit import AuditTrail
from core_banking.currency import Currency

app = FastAPI(title="Nexum Core Banking Dashboard", version="1.0")

# Initialize storage
storage = SQLiteStorage("core_banking.db")
audit_trail = AuditTrail(storage)

# Serve static files
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main dashboard page"""
    with open("dashboard/static/index.html", "r") as f:
        return f.read()

# Helper function to format currency
def format_currency_value(amount_str):
    try:
        return float(amount_str)
    except (ValueError, TypeError):
        return 0.0

# Overview API endpoints
@app.get("/api/overview")
async def get_overview():
    """Get dashboard overview statistics"""
    try:
        # Account summary
        all_accounts = storage.find("accounts", {})
        total_accounts = len(all_accounts)
        
        # Calculate balances by type
        balances_by_type = {
            'savings': 0.0,
            'checking': 0.0,
            'loan': 0.0,
            'credit_line': 0.0
        }
        
        for account in all_accounts:
            product_type = account.get('product_type', '')
            balance = format_currency_value(account.get('balance', 0))
            if product_type in balances_by_type:
                balances_by_type[product_type] += balance
        
        # Transaction volume (last 30 days) 
        thirty_days_ago = datetime.now()
        all_transactions = storage.load_all("transactions")
        recent_transactions = []
        
        for txn in all_transactions:
            try:
                txn_date = datetime.fromisoformat(txn['created_at'].replace('Z', '+00:00'))
                # Make both datetimes timezone-aware for comparison
                if txn_date.tzinfo is None:
                    txn_date = txn_date.replace(tzinfo=None)
                thirty_days_ago_naive = thirty_days_ago.replace(tzinfo=None)
                if txn_date > thirty_days_ago_naive - timedelta(days=30):
                    recent_transactions.append(txn)
            except (KeyError, ValueError, TypeError):
                continue
        
        # Collection summary
        all_cases = storage.load_all("collection_cases")
        active_cases = [case for case in all_cases if not case.get('resolved_at')]
        
        total_overdue = sum(
            format_currency_value(case.get('amount_overdue', 0)) 
            for case in active_cases
        )
        
        return {
            "accounts": {
                "total": total_accounts,
                "by_type": {
                    "savings": len([a for a in all_accounts if a.get('product_type') == 'savings']),
                    "checking": len([a for a in all_accounts if a.get('product_type') == 'checking']),
                    "loans": len([a for a in all_accounts if a.get('product_type') == 'loan']),
                    "credit_lines": len([a for a in all_accounts if a.get('product_type') == 'credit_line'])
                }
            },
            "balances": {
                "total_deposits": balances_by_type['savings'] + balances_by_type['checking'],
                "total_loans": abs(balances_by_type['loan']),
                "total_credit_used": balances_by_type['credit_line']
            },
            "transactions": {
                "count_30d": len(recent_transactions),
                "volume_30d": sum(format_currency_value(t.get('amount', 0)) for t in recent_transactions)
            },
            "collections": {
                "total_cases": len(active_cases),
                "total_overdue": total_overdue
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting overview: {str(e)}")

# Customer API endpoints
@app.get("/api/customers")
async def get_customers():
    """Get all customers"""
    try:
        customers = storage.find("customers", {})
        # Add account count for each customer
        for customer in customers:
            customer_accounts = storage.find("accounts", {"customer_id": customer["id"]})
            customer["account_count"] = len(customer_accounts)
            customer["total_balance"] = sum(
                format_currency_value(acc.get('balance', 0))
                for acc in customer_accounts
            )
        return customers
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting customers: {str(e)}")

@app.get("/api/customers/{customer_id}")
async def get_customer(customer_id: str):
    """Get customer details"""
    try:
        customer_data = storage.load("customers", customer_id)
        if not customer_data:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Get customer accounts
        accounts = storage.find("accounts", {"customer_id": customer_id})
        for account_data in accounts:
            account_data["balance"] = format_currency_value(account_data.get('balance', 0))
        
        customer_data["accounts"] = accounts
        return customer_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting customer: {str(e)}")

# Account API endpoints
@app.get("/api/accounts")
async def get_accounts(product_type: Optional[str] = None):
    """Get all accounts with optional filtering"""
    try:
        filters = {}
        if product_type:
            filters["product_type"] = product_type
        
        accounts = storage.find("accounts", filters)
        # Add balance and customer info
        for account_data in accounts:
            account_data["balance"] = format_currency_value(account_data.get('balance', 0))
            
            # Get customer info
            if account_data.get("customer_id"):
                customer = storage.load("customers", account_data["customer_id"])
                if customer:
                    account_data["customer_name"] = customer.get("name", "Unknown")
        
        return accounts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting accounts: {str(e)}")

@app.get("/api/accounts/{account_id}")
async def get_account(account_id: str):
    """Get account details"""
    try:
        account_data = storage.load("accounts", account_id)
        if not account_data:
            raise HTTPException(status_code=404, detail="Account not found")
        
        account_data["balance"] = format_currency_value(account_data.get('balance', 0))
        
        # Get recent transactions
        transactions = storage.find("transactions", {})
        account_transactions = [
            t for t in transactions 
            if t.get("from_account_id") == account_id or t.get("to_account_id") == account_id
        ]
        account_transactions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        account_data["recent_transactions"] = account_transactions[:10]
        
        return account_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting account: {str(e)}")

# Transaction API endpoints
@app.get("/api/transactions")
async def get_transactions(
    limit: int = Query(50, le=100),
    account_id: Optional[str] = None,
    transaction_type: Optional[str] = None
):
    """Get transactions with optional filtering"""
    try:
        transactions = storage.load_all("transactions")
        
        # Apply filters
        if account_id:
            transactions = [
                t for t in transactions 
                if t.get("from_account_id") == account_id or t.get("to_account_id") == account_id
            ]
        if transaction_type:
            transactions = [t for t in transactions if t.get("transaction_type") == transaction_type]
        
        # Sort by created_at desc and limit
        transactions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        transactions = transactions[:limit]
        
        # Enrich with account names
        for txn in transactions:
            if txn.get("from_account_id"):
                from_account = storage.load("accounts", txn["from_account_id"])
                if from_account:
                    txn["from_account_name"] = from_account.get("name", "Unknown")
            
            if txn.get("to_account_id"):
                to_account = storage.load("accounts", txn["to_account_id"])
                if to_account:
                    txn["to_account_name"] = to_account.get("name", "Unknown")
        
        return transactions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting transactions: {str(e)}")

# Loan API endpoints
@app.get("/api/loans")
async def get_loans(
    status: Optional[str] = None,
    loan_type: Optional[str] = None
):
    """Get all loans with optional filtering"""
    try:
        loans_data = storage.load_all("loans")
        
        # Apply status filter
        if status:
            loans_data = [loan for loan in loans_data if loan.get("state") == status]
        
        loans = []
        for loan_data in loans_data:
            # Get customer info
            customer = storage.load("customers", loan_data.get("customer_id", ""))
            customer_name = customer.get("name", "Unknown") if customer else "Unknown"
            
            # Extract loan information
            terms = loan_data.get("terms", {})
            principal = format_currency_value(terms.get("principal_amount", 0))
            balance = format_currency_value(loan_data.get("current_balance_amount", 0))
            rate = format_currency_value(terms.get("annual_interest_rate", 0)) * 100
            
            loans.append({
                "id": loan_data.get("id", ""),
                "loan_number": loan_data.get("id", "")[:8],
                "customer_id": loan_data.get("customer_id", ""),
                "customer_name": customer_name,
                "type": terms.get("amortization_method", "unknown"),
                "principal": principal,
                "balance": balance,
                "rate": rate,
                "status": loan_data.get("state", "unknown"),
                "next_payment_date": terms.get("first_payment_date"),
                "disbursed_date": loan_data.get("disbursed_date"),
                "monthly_payment": 0.0  # Simplified
            })
        
        return loans
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting loans: {str(e)}")

@app.get("/api/loans/{loan_id}")
async def get_loan_detail(loan_id: str):
    """Get loan detail with amortization schedule"""
    try:
        loan_data = storage.load("loans", loan_id)
        if not loan_data:
            raise HTTPException(status_code=404, detail="Loan not found")
        
        # Get customer info
        customer = storage.load("customers", loan_data.get("customer_id", ""))
        
        # Get amortization schedule
        schedule_entries = storage.find("amortization_schedules", {"loan_id": loan_id})
        schedule_data = []
        for entry in schedule_entries:
            schedule_data.append({
                "payment_number": entry.get("payment_number", 0),
                "payment_date": entry.get("payment_date", ""),
                "payment_amount": format_currency_value(entry.get("payment_amount", 0)),
                "principal_amount": format_currency_value(entry.get("principal_amount", 0)),
                "interest_amount": format_currency_value(entry.get("interest_amount", 0)),
                "remaining_balance": format_currency_value(entry.get("remaining_balance", 0))
            })
        
        # Get payment history
        payment_history = []
        payments = storage.find("loan_payments", {"loan_id": loan_id})
        for payment in payments:
            payment_history.append({
                "payment_date": payment.get("payment_date", ""),
                "payment_amount": format_currency_value(payment.get("payment_amount_amount", 0)),
                "principal_amount": format_currency_value(payment.get("principal_amount_amount", 0)),
                "interest_amount": format_currency_value(payment.get("interest_amount_amount", 0)),
                "late_fee": format_currency_value(payment.get("late_fee_amount", 0))
            })
        
        terms = loan_data.get("terms", {})
        
        return {
            "id": loan_data.get("id", ""),
            "customer": customer.get("name", "Unknown") if customer else "Unknown",
            "terms": {
                "principal_amount": format_currency_value(terms.get("principal_amount", 0)),
                "annual_interest_rate": format_currency_value(terms.get("annual_interest_rate", 0)) * 100,
                "term_months": terms.get("term_months", 0),
                "payment_frequency": terms.get("payment_frequency", "monthly"),
                "first_payment_date": terms.get("first_payment_date", ""),
                "disbursement_date": loan_data.get("disbursed_date", "")
            },
            "current_status": {
                "state": loan_data.get("state", "unknown"),
                "current_balance": format_currency_value(loan_data.get("current_balance_amount", 0)),
                "total_paid": format_currency_value(loan_data.get("total_paid_amount", 0)),
                "principal_paid": format_currency_value(loan_data.get("principal_paid_amount", 0)),
                "interest_paid": format_currency_value(loan_data.get("interest_paid_amount", 0)),
                "days_past_due": loan_data.get("days_past_due", 0)
            },
            "amortization_schedule": schedule_data,
            "payment_history": payment_history
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting loan detail: {str(e)}")

# Credit Lines API endpoints
@app.get("/api/credit-lines")
async def get_credit_lines():
    """Get all credit lines"""
    try:
        credit_accounts = storage.find("accounts", {"product_type": "credit_line"})
        credit_lines = []
        
        for account_data in credit_accounts:
            # Get customer info
            customer = storage.load("customers", account_data.get("customer_id", ""))
            
            balance = format_currency_value(account_data.get("balance", 0))
            credit_limit = format_currency_value(account_data.get("credit_limit_amount", 10000))
            available = credit_limit - balance
            
            credit_lines.append({
                "id": account_data.get("id", ""),
                "account_number": account_data.get("id", "")[:8],
                "customer_id": account_data.get("customer_id", ""),
                "customer_name": customer.get("name", "Unknown") if customer else "Unknown",
                "limit": credit_limit,
                "used": balance,
                "available": available,
                "status": account_data.get("status", "active"),
                "min_payment_due": 0.0  # Simplified
            })
        
        return credit_lines
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting credit lines: {str(e)}")

@app.get("/api/credit-lines/{account_id}")
async def get_credit_line_detail(account_id: str):
    """Get credit line detail with statements and history"""
    try:
        account_data = storage.load("accounts", account_id)
        if not account_data:
            raise HTTPException(status_code=404, detail="Credit line not found")
        
        # Get customer info
        customer = storage.load("customers", account_data.get("customer_id", ""))
        
        # Get statements
        statements = storage.find("credit_statements", {"account_id": account_id})
        statements_data = []
        for stmt in statements:
            statements_data.append({
                "id": stmt.get("id", ""),
                "statement_date": stmt.get("statement_date", ""),
                "due_date": stmt.get("due_date", ""),
                "current_balance": format_currency_value(stmt.get("current_balance_amount", 0)),
                "minimum_payment_due": format_currency_value(stmt.get("minimum_payment_due_amount", 0)),
                "status": stmt.get("status", "current")
            })
        
        # Get credit transactions
        credit_transactions = storage.find("credit_transactions", {"account_id": account_id})
        transactions_data = []
        for txn in credit_transactions:
            transactions_data.append({
                "transaction_date": txn.get("transaction_date", ""),
                "description": txn.get("description", ""),
                "category": txn.get("category", "unknown"),
                "amount": format_currency_value(txn.get("amount", 0))
            })
        
        balance = format_currency_value(account_data.get("balance", 0))
        credit_limit = format_currency_value(account_data.get("credit_limit_amount", 10000))
        
        return {
            "id": account_data.get("id", ""),
            "customer": customer.get("name", "Unknown") if customer else "Unknown",
            "credit_info": {
                "credit_limit": credit_limit,
                "current_balance": balance,
                "available_credit": credit_limit - balance,
                "status": account_data.get("status", "active")
            },
            "statements": statements_data,
            "transaction_history": transactions_data[:20]  # Last 20 transactions
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting credit line detail: {str(e)}")

# Collections API endpoints
@app.get("/api/collections/cases")
async def get_collection_cases(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    dpd_bucket: Optional[str] = None
):
    """Get collection cases with optional filtering"""
    try:
        cases_data = storage.load_all("collection_cases")
        cases = []
        
        for case_data in cases_data:
            # Skip resolved cases unless specifically requested
            if case_data.get("resolved_at") and status != "resolved":
                continue
            
            # Apply filters
            if status and case_data.get("status") != status:
                continue
            if priority and case_data.get("priority") != priority:
                continue
            
            days_past_due = case_data.get("days_past_due", 0)
            
            # Apply DPD bucket filter
            if dpd_bucket:
                bucket_ranges = {
                    "1-30": (1, 30),
                    "31-60": (31, 60),
                    "61-90": (61, 90),
                    "90+": (91, 999)
                }
                if dpd_bucket in bucket_ranges:
                    min_dpd, max_dpd = bucket_ranges[dpd_bucket]
                    if not (min_dpd <= days_past_due <= max_dpd):
                        continue
            
            # Get customer info
            customer = storage.load("customers", case_data.get("customer_id", ""))
            
            cases.append({
                "id": case_data.get("id", ""),
                "case_id": case_data.get("id", "")[:8],
                "customer_id": case_data.get("customer_id", ""),
                "customer_name": customer.get("name", "Unknown") if customer else "Unknown",
                "amount_overdue": format_currency_value(case_data.get("amount_overdue", 0)),
                "days_past_due": days_past_due,
                "status": case_data.get("status", "current"),
                "assigned_to": case_data.get("assigned_collector", "Unassigned"),
                "priority": case_data.get("priority", 1),
                "account_type": "loan" if case_data.get("loan_id") else "credit_line"
            })
        
        return cases
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting collection cases: {str(e)}")

@app.get("/api/collections/stats")
async def get_collection_stats():
    """Get collection statistics"""
    try:
        all_cases_data = storage.load_all("collection_cases")
        active_cases = [case for case in all_cases_data if not case.get("resolved_at")]
        
        # Calculate DPD bucket distribution
        dpd_buckets = {
            "0": 0,
            "1-30": 0,
            "31-60": 0,
            "61-90": 0,
            "90+": 0
        }
        
        total_overdue_by_bucket = {
            "1-30": 0.0,
            "31-60": 0.0,
            "61-90": 0.0,
            "90+": 0.0
        }
        
        status_counts = {}
        total_overdue = 0.0
        
        for case_data in active_cases:
            days_past_due = case_data.get("days_past_due", 0)
            amount_overdue = format_currency_value(case_data.get("amount_overdue", 0))
            status = case_data.get("status", "current")
            
            total_overdue += amount_overdue
            status_counts[status] = status_counts.get(status, 0) + 1
            
            if days_past_due == 0:
                dpd_buckets["0"] += 1
            elif 1 <= days_past_due <= 30:
                dpd_buckets["1-30"] += 1
                total_overdue_by_bucket["1-30"] += amount_overdue
            elif 31 <= days_past_due <= 60:
                dpd_buckets["31-60"] += 1
                total_overdue_by_bucket["31-60"] += amount_overdue
            elif 61 <= days_past_due <= 90:
                dpd_buckets["61-90"] += 1
                total_overdue_by_bucket["61-90"] += amount_overdue
            else:
                dpd_buckets["90+"] += 1
                total_overdue_by_bucket["90+"] += amount_overdue
        
        return {
            "total_cases": len(active_cases),
            "total_overdue_amount": total_overdue,
            "cases_by_status": status_counts,
            "dpd_distribution": dpd_buckets,
            "overdue_by_bucket": total_overdue_by_bucket,
            "recovery_rate": 65.0,  # Simplified
            "cases_resolved_6m": 45  # Simplified
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting collection stats: {str(e)}")

# Products API endpoints
@app.get("/api/products")
async def get_products(product_type: Optional[str] = None):
    """Get all products"""
    try:
        products_data = storage.load_all("products")
        
        if product_type:
            products_data = [p for p in products_data if p.get("product_type") == product_type]
        
        products = []
        for product_data in products_data:
            # Extract rate range
            rate_range = "N/A"
            interest_config = product_data.get("interest_config", {})
            if isinstance(interest_config, dict):
                if interest_config.get("rate"):
                    rate = float(interest_config["rate"]) * 100
                    rate_range = f"{rate:.2f}%"
                elif interest_config.get("rate_range"):
                    min_rate, max_rate = interest_config["rate_range"]
                    rate_range = f"{float(min_rate)*100:.2f}% - {float(max_rate)*100:.2f}%"
            
            # Extract term range
            term_range = "N/A"
            term_config = product_data.get("term_config", {})
            if isinstance(term_config, dict):
                min_term = term_config.get("min_term_months")
                max_term = term_config.get("max_term_months")
                if min_term and max_term:
                    term_range = f"{min_term}-{max_term} months"
            
            products.append({
                "id": product_data.get("id", ""),
                "name": product_data.get("name", ""),
                "product_code": product_data.get("product_code", ""),
                "type": product_data.get("product_type", ""),
                "rate_range": rate_range,
                "term_range": term_range,
                "status": product_data.get("status", "draft"),
                "active_accounts": 0  # Simplified
            })
        
        return products
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting products: {str(e)}")

@app.get("/api/products/{product_id}")
async def get_product_detail(product_id: str):
    """Get product detail"""
    try:
        product_data = storage.load("products", product_id)
        if not product_data:
            raise HTTPException(status_code=404, detail="Product not found")
        
        # Get performance metrics (simplified)
        performance_metrics = {
            "total_accounts": 0,
            "total_balance": 0.0,
            "avg_balance": 0.0,
            "delinquency_rate": 0.0
        }
        
        return {
            "id": product_data.get("id", ""),
            "name": product_data.get("name", ""),
            "description": product_data.get("description", ""),
            "product_code": product_data.get("product_code", ""),
            "product_type": product_data.get("product_type", ""),
            "currency": product_data.get("currency", "USD"),
            "status": product_data.get("status", "draft"),
            "created_at": product_data.get("created_at", ""),
            "configuration": {
                "interest_config": product_data.get("interest_config", {}),
                "fees": product_data.get("fees", []),
                "limit_config": product_data.get("limit_config", {}),
                "term_config": product_data.get("term_config", {}),
                "credit_config": product_data.get("credit_config", {})
            },
            "performance_metrics": performance_metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting product detail: {str(e)}")

def create_app():
    """Create and return the FastAPI app instance"""
    return app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8890)