"""Nexum Core Banking Dashboard - FastAPI Application"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any

# Add parent to path so core_banking package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Import core banking components
from core_banking.api_old import BankingSystem, banking_system
from core_banking.currency import Money, Currency
from core_banking.accounts import ProductType, AccountState
from core_banking.customers import KYCStatus, KYCTier
from core_banking.transactions import TransactionType, TransactionChannel
from core_banking.loans import LoanState


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    
    app = FastAPI(
        title="Nexum Core Banking Dashboard",
        description="Production dashboard for core banking operations",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files directory
    static_dir = Path(__file__).resolve().parent / "static"

    # API Routes
    
    @app.get("/api/dashboard/overview")
    async def get_dashboard_overview():
        """Get dashboard overview with KPIs and recent activity"""
        try:
            system = banking_system
            
            # Get customers
            customers = system.customer_manager.get_all_customers()
            total_customers = len(customers)
            
            # Get accounts 
            accounts = system.account_manager.get_all_accounts()
            total_accounts = len(accounts)
            active_accounts = len([a for a in accounts if a.state == AccountState.ACTIVE])
            
            # Calculate total deposits and loan portfolio
            total_deposits = Decimal('0')
            total_loan_portfolio = Decimal('0')
            
            for account in accounts:
                if account.state == AccountState.ACTIVE:
                    try:
                        # Try to get balance - use different approaches based on what's available
                        if hasattr(system.account_manager, 'get_account_balance'):
                            balance = system.account_manager.get_account_balance(account.id)
                        elif hasattr(system.ledger, 'get_account_balance'):
                            balance = system.ledger.get_account_balance(account.id)
                        elif hasattr(system.ledger, 'get_balance'):
                            balance = system.ledger.get_balance(account.id)
                        else:
                            # Fallback - assume zero balance
                            balance = Money(Decimal('0'), Currency.USD)
                        
                        if account.product_type in [ProductType.SAVINGS, ProductType.CHECKING]:
                            total_deposits += balance.amount
                        elif account.product_type == ProductType.LOAN:
                            total_loan_portfolio += abs(balance.amount)  # Loans are negative balances
                    except Exception as e:
                        # Skip this account if we can't get balance
                        print(f"Could not get balance for account {account.id}: {e}")
                        continue
            
            # Get loans (simplified)
            loans = []
            active_loans = 0
            
            # Get recent transactions (last 20)
            try:
                recent_transactions = system.audit_trail.get_recent_events(limit=20)
                transactions_data = []
                for event in recent_transactions:
                    if hasattr(event, 'event_type') and 'transaction' in event.event_type.lower():
                        transactions_data.append({
                            'id': event.id,
                            'timestamp': event.timestamp.isoformat(),
                            'type': event.event_type,
                            'description': event.details.get('description', ''),
                            'amount': event.details.get('amount', '0'),
                            'status': 'completed'
                        })
                recent_transactions = transactions_data[:20]
            except Exception as e:
                print(f"Error getting recent transactions: {e}")
                recent_transactions = []
            
            # Active alerts (simplified)
            alerts = []
            
            return {
                'kpis': {
                    'total_customers': total_customers,
                    'total_accounts': total_accounts,
                    'active_loans': active_loans,
                    'total_deposits': str(total_deposits),
                    'total_loan_portfolio': str(total_loan_portfolio),
                    'overdue_amount': '0'
                },
                'recent_transactions': recent_transactions,
                'alerts': alerts,
                'charts': {
                    'account_openings': [],
                    'transaction_volume': [],
                    'loan_portfolio_growth': []
                }
            }
        except Exception as e:
            print(f"Error in dashboard overview: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/customers")
    async def get_customers(
        search: Optional[str] = Query(None, description="Search term"),
        kyc_status: Optional[str] = Query(None, description="Filter by KYC status"),
        limit: int = Query(100, description="Number of results")
    ):
        """Get customers with optional filtering"""
        try:
            system = banking_system
            customers = system.customer_manager.get_all_customers()
            
            # Apply search filter
            if search:
                search = search.lower()
                customers = [
                    c for c in customers 
                    if (search in c.first_name.lower() or 
                        search in c.last_name.lower() or
                        search in c.email.lower())
                ]
            
            # Apply KYC status filter
            if kyc_status:
                try:
                    status_enum = KYCStatus[kyc_status.upper()]
                    customers = [c for c in customers if c.kyc_status == status_enum]
                except KeyError:
                    pass
            
            # Limit results
            customers = customers[:limit]
            
            # Get account counts for each customer
            result = []
            for customer in customers:
                try:
                    customer_accounts = system.account_manager.get_customer_accounts(customer.id)
                    result.append({
                        'id': customer.id,
                        'first_name': customer.first_name,
                        'last_name': customer.last_name,
                        'email': customer.email,
                        'phone': customer.phone,
                        'kyc_status': customer.kyc_status.value,
                        'kyc_tier': customer.kyc_tier.value if customer.kyc_tier else None,
                        'risk_rating': getattr(customer, 'risk_rating', 'low'),
                        'account_count': len(customer_accounts),
                        'created_at': customer.created_at.isoformat() if hasattr(customer, 'created_at') else None
                    })
                except Exception as e:
                    print(f"Error processing customer {customer.id}: {e}")
                    continue
            
            return {'customers': result, 'total': len(result)}
            
        except Exception as e:
            print(f"Error in get_customers: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/accounts")
    async def get_accounts(
        account_type: Optional[str] = Query(None, description="Filter by account type"),
        status: Optional[str] = Query(None, description="Filter by status"),
        currency: Optional[str] = Query(None, description="Filter by currency"),
        limit: int = Query(100, description="Number of results")
    ):
        """Get accounts with optional filtering"""
        try:
            system = banking_system
            accounts = system.account_manager.get_all_accounts()
            
            # Apply filters
            if account_type:
                try:
                    type_enum = ProductType[account_type.upper()]
                    accounts = [a for a in accounts if a.product_type == type_enum]
                except KeyError:
                    pass
            
            if status:
                try:
                    status_enum = AccountState[status.upper()]
                    accounts = [a for a in accounts if a.state == status_enum]
                except KeyError:
                    pass
            
            # Limit results
            accounts = accounts[:limit]
            
            # Build response with balances and customer info
            result = []
            for account in accounts:
                try:
                    # Try different balance methods
                    balance = Money(Decimal('0'), Currency.USD)  # Default fallback
                    try:
                        if hasattr(system.account_manager, 'get_account_balance'):
                            balance = system.account_manager.get_account_balance(account.id)
                        elif hasattr(system.ledger, 'get_account_balance'):
                            balance = system.ledger.get_account_balance(account.id)
                    except Exception:
                        pass
                    
                    customer = system.customer_manager.get_customer(account.customer_id)
                    
                    result.append({
                        'id': account.id,
                        'account_number': account.account_number,
                        'customer_id': account.customer_id,
                        'customer_name': f"{customer.first_name} {customer.last_name}" if customer else "Unknown",
                        'product_type': account.product_type.value,
                        'state': account.state.value,
                        'balance': str(balance.amount),
                        'currency': balance.currency.code,
                        'name': account.name,
                        'created_at': account.created_at.isoformat()
                    })
                except Exception as e:
                    print(f"Error processing account {account.id}: {e}")
                    continue
            
            return {'accounts': result, 'total': len(result)}
            
        except Exception as e:
            print(f"Error in get_accounts: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/transactions")
    async def get_transactions(
        start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
        end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
        transaction_type: Optional[str] = Query(None, description="Filter by type"),
        status: Optional[str] = Query(None, description="Filter by status"),
        min_amount: Optional[float] = Query(None, description="Minimum amount"),
        max_amount: Optional[float] = Query(None, description="Maximum amount"),
        limit: int = Query(100, description="Number of results")
    ):
        """Get transactions with filtering options"""
        try:
            system = banking_system
            
            # Get recent audit events (transactions are logged as events)
            events = system.audit_trail.get_recent_events(limit=500)
            
            transactions = []
            for event in events:
                if 'transaction' in event.event_type.lower():
                    amount_str = event.details.get('amount', '0')
                    try:
                        # Parse amount string
                        clean_amount = amount_str.replace('$', '').replace(',', '').replace('USD', '').strip()
                        amount = float(clean_amount)
                    except (ValueError, AttributeError):
                        amount = 0.0
                    
                    # Apply filters
                    if min_amount is not None and amount < min_amount:
                        continue
                    if max_amount is not None and amount > max_amount:
                        continue
                    
                    # Parse dates if provided
                    event_date = event.timestamp.date()
                    if start_date:
                        try:
                            start = datetime.fromisoformat(start_date).date()
                            if event_date < start:
                                continue
                        except ValueError:
                            pass
                    
                    if end_date:
                        try:
                            end = datetime.fromisoformat(end_date).date()
                            if event_date > end:
                                continue
                        except ValueError:
                            pass
                    
                    transactions.append({
                        'id': event.id,
                        'timestamp': event.timestamp.isoformat(),
                        'type': event.event_type,
                        'description': event.details.get('description', ''),
                        'amount': amount_str,
                        'from_account': event.details.get('from_account_id'),
                        'to_account': event.details.get('to_account_id'),
                        'status': 'completed',
                        'reference': event.details.get('reference')
                    })
            
            # Apply limit
            transactions = transactions[:limit]
            
            return {'transactions': transactions, 'total': len(transactions)}
            
        except Exception as e:
            print(f"Error in get_transactions: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Serve main HTML
    @app.get("/", response_class=HTMLResponse)
    def index():
        return (static_dir / "index.html").read_text()

    # Static files (mount last — it's a catch-all sub-app)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app