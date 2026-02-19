"""
Reporting Engine Module

Dynamic reporting engine with configurable reports, regulatory templates,
and portfolio dashboards. Supports real-time dynamic reporting with
custom dimensions, metrics, and export formats.
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Union
from enum import Enum
import uuid
import csv
import io
import json

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType
from .ledger import GeneralLedger, AccountType
from .accounts import AccountManager, Account, ProductType, AccountState
from .loans import LoanManager, Loan, LoanState
from .credit import CreditLineManager
from .collections import CollectionsManager, DelinquencyStatus
from .customers import CustomerManager
from .products import ProductEngine
from .transactions import TransactionType


class ReportType(Enum):
    """Types of available reports"""
    PORTFOLIO_SUMMARY = "portfolio_summary"
    LOAN_PORTFOLIO = "loan_portfolio"
    DEPOSIT_PORTFOLIO = "deposit_portfolio"
    DELINQUENCY = "delinquency"
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    REGULATORY = "regulatory"
    CUSTOMER_SEGMENT = "customer_segment"
    PRODUCT_PERFORMANCE = "product_performance"
    COLLECTION_PERFORMANCE = "collection_performance"
    TRANSACTION_VOLUME = "transaction_volume"
    CUSTOM = "custom"


class ReportFormat(Enum):
    """Output formats for reports"""
    DICT = "dict"
    CSV = "csv"
    JSON = "json"


class AggregationType(Enum):
    """Types of aggregations for metrics"""
    SUM = "sum"
    COUNT = "count"
    AVERAGE = "average"
    MIN = "min"
    MAX = "max"
    PERCENTAGE = "percentage"


class ReportPeriod(Enum):
    """Report time periods"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class DimensionType(Enum):
    """Dimensions for grouping report data"""
    PRODUCT = "product"
    CURRENCY = "currency"
    BRANCH = "branch"
    CUSTOMER_TIER = "customer_tier"
    DELINQUENCY_STATUS = "delinquency_status"
    TRANSACTION_TYPE = "transaction_type"
    DATE = "date"


class MetricFormat(Enum):
    """Display formats for metrics"""
    MONEY = "money"
    PERCENTAGE = "percentage"
    COUNT = "count"
    DECIMAL = "decimal"


@dataclass
class MetricDefinition:
    """Definition of a metric to calculate"""
    name: str
    field: str
    aggregation: AggregationType
    format: MetricFormat = MetricFormat.DECIMAL
    
    def format_value(self, value: Any, currency: Currency = None) -> str:
        """Format a metric value for display"""
        if self.format == MetricFormat.MONEY and currency:
            if isinstance(value, Money):
                return value.to_string()
            return Money(Decimal(str(value)), currency).to_string()
        elif self.format == MetricFormat.PERCENTAGE:
            return f"{float(value):.2%}"
        elif self.format == MetricFormat.COUNT:
            return str(int(value))
        else:
            return str(value)


@dataclass
class ReportDefinition(StorageRecord):
    """Definition of a custom report"""
    name: str
    description: str
    report_type: ReportType
    dimensions: List[DimensionType] = field(default_factory=list)
    metrics: List[MetricDefinition] = field(default_factory=list)
    filters: Dict[str, Any] = field(default_factory=dict)
    period: ReportPeriod = ReportPeriod.MONTHLY
    created_by: str = ""
    is_template: bool = False
    
    def __post_init__(self):
        # Ensure dimensions and metrics are lists
        if not isinstance(self.dimensions, list):
            self.dimensions = []
        if not isinstance(self.metrics, list):
            self.metrics = []


@dataclass
class ReportResult:
    """Result of a report execution"""
    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    data: List[Dict[str, Any]] = field(default_factory=list)
    totals: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.metadata:
            self.metadata = {
                'row_count': len(self.data),
                'generation_time_ms': 0,
                'currency': 'USD'
            }


class ReportingEngine:
    """
    Dynamic reporting engine for banking operations
    """
    
    def __init__(
        self,
        storage: StorageInterface,
        ledger: GeneralLedger = None,
        account_manager: AccountManager = None,
        loan_manager: LoanManager = None,
        credit_manager: CreditLineManager = None,
        collections_manager: CollectionsManager = None,
        customer_manager: CustomerManager = None,
        product_engine: ProductEngine = None,
        audit_trail: AuditTrail = None
    ):
        self.storage = storage
        self.ledger = ledger
        self.account_manager = account_manager
        self.loan_manager = loan_manager
        self.credit_manager = credit_manager
        self.collections_manager = collections_manager
        self.customer_manager = customer_manager
        self.product_engine = product_engine
        self.audit_trail = audit_trail
        self.report_definitions_table = "report_definitions"
        
    def portfolio_summary(self, currency: Currency = Currency.USD) -> ReportResult:
        """
        Generate portfolio summary report with key metrics
        """
        start_time = datetime.now(timezone.utc)
        report_id = "portfolio_summary"
        
        # Initialize totals
        total_assets = Money(Decimal('0'), currency)
        total_liabilities = Money(Decimal('0'), currency)
        total_loans = Money(Decimal('0'), currency)
        total_deposits = Money(Decimal('0'), currency)
        npl_amount = Money(Decimal('0'), currency)
        
        data = []
        
        # Get all accounts
        if self.account_manager:
            accounts = self.account_manager.get_all_accounts()
            
            for account in accounts:
                if account.currency == currency and account.state == AccountState.ACTIVE:
                    balance = self.account_manager.get_account_balance(account.id)
                    
                    # Asset accounts
                    if account.is_asset_account:
                        total_assets = total_assets + balance
                        if account.is_deposit_product:
                            total_deposits = total_deposits + balance
                    
                    # Liability accounts  
                    elif account.is_liability_account:
                        total_liabilities = total_liabilities + balance
                        if account.is_loan_product:
                            total_loans = total_loans + balance
        
        # Get NPL amount
        if self.collections_manager:
            cases = self.collections_manager.get_all_cases()
            for case in cases:
                if case.status in [DelinquencyStatus.SERIOUS, DelinquencyStatus.DEFAULT]:
                    npl_amount = npl_amount + case.current_balance
        
        # Calculate NPL ratio
        npl_ratio = Decimal('0')
        if not total_loans.is_zero():
            npl_ratio = (npl_amount.amount / total_loans.amount) * 100
        
        # Calculate equity
        equity = total_assets - total_liabilities
        
        # Build summary data
        summary_data = {
            'total_assets': total_assets.amount,
            'total_liabilities': total_liabilities.amount,
            'equity': equity.amount,
            'total_loans': total_loans.amount,
            'total_deposits': total_deposits.amount,
            'npl_amount': npl_amount.amount,
            'npl_ratio': npl_ratio,
            'currency': currency.code
        }
        
        data.append(summary_data)
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=start_time.replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=end_time,
            data=data,
            totals=summary_data,
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code
            }
        )
    
    def loan_portfolio_report(
        self,
        filters: Dict[str, Any] = None
    ) -> ReportResult:
        """
        Generate loan portfolio report by product, status, delinquency
        """
        start_time = datetime.now(timezone.utc)
        report_id = "loan_portfolio"
        
        if not filters:
            filters = {}
        
        currency = Currency[filters.get('currency', 'USD')]
        data = []
        totals = {
            'total_loans': 0,
            'total_balance': Decimal('0'),
            'performing_balance': Decimal('0'),
            'non_performing_balance': Decimal('0'),
            'par_ratio': Decimal('0')
        }
        
        if self.loan_manager:
            loans = self.loan_manager.get_all_loans()
            
            # Group by product type and status
            grouped_data = {}
            
            for loan in loans:
                if loan.principal_amount.currency != currency:
                    continue
                
                # Apply filters
                if filters.get('product_type') and loan.product_type != filters['product_type']:
                    continue
                if filters.get('state') and loan.state != LoanState[filters['state']]:
                    continue
                
                # Get current balance
                current_balance = self.loan_manager.get_current_balance(loan.id)
                
                # Determine delinquency status
                delinquency_status = "CURRENT"
                if self.collections_manager:
                    case = self.collections_manager.get_case_by_loan(loan.id)
                    if case:
                        delinquency_status = case.status.value.upper()
                
                # Group key
                group_key = (loan.product_type.value, loan.state.value, delinquency_status)
                
                if group_key not in grouped_data:
                    grouped_data[group_key] = {
                        'product_type': loan.product_type.value,
                        'loan_state': loan.state.value,
                        'delinquency_status': delinquency_status,
                        'loan_count': 0,
                        'total_balance': Decimal('0'),
                        'currency': currency.code
                    }
                
                grouped_data[group_key]['loan_count'] += 1
                grouped_data[group_key]['total_balance'] += current_balance.amount
                
                # Update totals
                totals['total_loans'] += 1
                totals['total_balance'] += current_balance.amount
                
                if delinquency_status in ['CURRENT', 'EARLY']:
                    totals['performing_balance'] += current_balance.amount
                else:
                    totals['non_performing_balance'] += current_balance.amount
            
            data = list(grouped_data.values())
        
        # Calculate PAR ratio
        if totals['total_balance'] > 0:
            totals['par_ratio'] = (totals['non_performing_balance'] / totals['total_balance']) * 100
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=start_time.replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=end_time,
            data=data,
            totals=dict(totals),
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code,
                'filters_applied': filters
            }
        )
    
    def deposit_portfolio_report(
        self,
        filters: Dict[str, Any] = None
    ) -> ReportResult:
        """
        Generate deposit portfolio report by product, maturity, interest rate bands
        """
        start_time = datetime.now(timezone.utc)
        report_id = "deposit_portfolio"
        
        if not filters:
            filters = {}
        
        currency = Currency[filters.get('currency', 'USD')]
        data = []
        totals = {
            'total_accounts': 0,
            'total_balance': Decimal('0'),
            'average_balance': Decimal('0'),
            'weighted_avg_rate': Decimal('0')
        }
        
        if self.account_manager:
            accounts = self.account_manager.get_all_accounts()
            
            # Group deposit accounts
            grouped_data = {}
            
            for account in accounts:
                if not account.is_deposit_product or account.currency != currency:
                    continue
                
                if account.state != AccountState.ACTIVE:
                    continue
                
                # Apply filters
                if filters.get('product_type') and account.product_type.value != filters['product_type']:
                    continue
                
                balance = self.account_manager.get_account_balance(account.id)
                
                # Determine interest rate band
                rate_band = "0-1%"
                if account.interest_rate:
                    rate_pct = account.interest_rate * 100
                    if rate_pct >= 5:
                        rate_band = "5%+"
                    elif rate_pct >= 3:
                        rate_band = "3-5%"
                    elif rate_pct >= 1:
                        rate_band = "1-3%"
                
                # Group key
                group_key = (account.product_type.value, rate_band)
                
                if group_key not in grouped_data:
                    grouped_data[group_key] = {
                        'product_type': account.product_type.value,
                        'rate_band': rate_band,
                        'account_count': 0,
                        'total_balance': Decimal('0'),
                        'average_rate': Decimal('0'),
                        'currency': currency.code
                    }
                
                grouped_data[group_key]['account_count'] += 1
                grouped_data[group_key]['total_balance'] += balance.amount
                
                if account.interest_rate:
                    # Weighted average calculation
                    current_total = grouped_data[group_key]['average_rate'] * (grouped_data[group_key]['account_count'] - 1)
                    grouped_data[group_key]['average_rate'] = (current_total + account.interest_rate * 100) / grouped_data[group_key]['account_count']
                
                # Update totals
                totals['total_accounts'] += 1
                totals['total_balance'] += balance.amount
            
            data = list(grouped_data.values())
        
        # Calculate overall averages
        if totals['total_accounts'] > 0:
            totals['average_balance'] = totals['total_balance'] / totals['total_accounts']
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=start_time.replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=end_time,
            data=data,
            totals=dict(totals),
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code,
                'filters_applied': filters
            }
        )
    
    def delinquency_report(self, currency: Currency = Currency.USD) -> ReportResult:
        """
        Generate delinquency aging report with buckets
        """
        start_time = datetime.now(timezone.utc)
        report_id = "delinquency"
        
        data = []
        totals = {
            'total_cases': 0,
            'total_balance': Decimal('0')
        }
        
        # Initialize aging buckets
        buckets = {
            'current': {'cases': 0, 'balance': Decimal('0')},
            '1-30': {'cases': 0, 'balance': Decimal('0')},
            '31-60': {'cases': 0, 'balance': Decimal('0')},
            '61-90': {'cases': 0, 'balance': Decimal('0')},
            '90+': {'cases': 0, 'balance': Decimal('0')}
        }
        
        if self.collections_manager:
            cases = self.collections_manager.get_all_cases()
            
            for case in cases:
                if case.current_balance.currency != currency:
                    continue
                
                # Determine bucket based on days past due
                days_past_due = case.days_past_due
                bucket_name = 'current'
                
                if days_past_due > 90:
                    bucket_name = '90+'
                elif days_past_due > 60:
                    bucket_name = '61-90'
                elif days_past_due > 30:
                    bucket_name = '31-60'
                elif days_past_due > 0:
                    bucket_name = '1-30'
                
                buckets[bucket_name]['cases'] += 1
                buckets[bucket_name]['balance'] += case.current_balance.amount
                
                totals['total_cases'] += 1
                totals['total_balance'] += case.current_balance.amount
        
        # Convert to data format (always create all buckets even if empty)
        for bucket_name, bucket_data in buckets.items():
            percentage = Decimal('0')
            if totals['total_balance'] > 0:
                percentage = (bucket_data['balance'] / totals['total_balance']) * 100
            
            data.append({
                'aging_bucket': bucket_name,
                'case_count': bucket_data['cases'],
                'total_balance': bucket_data['balance'],
                'percentage': percentage,
                'currency': currency.code
            })
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=start_time.replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=end_time,
            data=data,
            totals=dict(totals),
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code
            }
        )
    
    def income_statement(
        self,
        period_start: datetime,
        period_end: datetime,
        currency: Currency = Currency.USD
    ) -> ReportResult:
        """
        Generate income statement for specified period
        """
        start_time = datetime.now(timezone.utc)
        report_id = "income_statement"
        
        data = []
        totals = {
            'interest_income': Decimal('0'),
            'fee_income': Decimal('0'),
            'total_revenue': Decimal('0'),
            'provisions': Decimal('0'),
            'operating_expenses': Decimal('0'),
            'net_income': Decimal('0')
        }
        
        # Mock income statement data - in real implementation would calculate from transactions
        income_items = [
            {'category': 'Interest Income', 'subcategory': 'Loan Interest', 'amount': Decimal('50000')},
            {'category': 'Interest Income', 'subcategory': 'Investment Income', 'amount': Decimal('5000')},
            {'category': 'Fee Income', 'subcategory': 'Transaction Fees', 'amount': Decimal('12000')},
            {'category': 'Fee Income', 'subcategory': 'Service Charges', 'amount': Decimal('8000')},
            {'category': 'Provisions', 'subcategory': 'Loan Loss Provisions', 'amount': Decimal('-15000')},
            {'category': 'Operating Expenses', 'subcategory': 'Staff Costs', 'amount': Decimal('-25000')},
            {'category': 'Operating Expenses', 'subcategory': 'Technology', 'amount': Decimal('-10000')},
        ]
        
        for item in income_items:
            data.append({
                'category': item['category'],
                'subcategory': item['subcategory'],
                'amount': item['amount'],
                'currency': currency.code
            })
            
            # Update totals
            if item['category'] == 'Interest Income':
                totals['interest_income'] += item['amount']
            elif item['category'] == 'Fee Income':
                totals['fee_income'] += item['amount']
            elif item['category'] == 'Provisions':
                totals['provisions'] += item['amount']
            elif item['category'] == 'Operating Expenses':
                totals['operating_expenses'] += item['amount']
        
        totals['total_revenue'] = totals['interest_income'] + totals['fee_income']
        totals['net_income'] = totals['total_revenue'] + totals['provisions'] + totals['operating_expenses']
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=period_start,
            period_end=period_end,
            data=data,
            totals=dict(totals),
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code
            }
        )
    
    def transaction_volume_report(
        self,
        period_start: datetime,
        period_end: datetime,
        currency: Currency = Currency.USD
    ) -> ReportResult:
        """
        Generate transaction volume report by type, channel, currency
        """
        start_time = datetime.now(timezone.utc)
        report_id = "transaction_volume"
        
        data = []
        totals = {
            'total_transactions': 0,
            'total_volume': Decimal('0')
        }
        
        # Mock transaction data - in real implementation would query transaction history
        transaction_types = [
            {'type': 'DEPOSIT', 'channel': 'ATM', 'count': 1250, 'volume': Decimal('125000')},
            {'type': 'WITHDRAWAL', 'channel': 'ATM', 'count': 980, 'volume': Decimal('98000')},
            {'type': 'TRANSFER', 'channel': 'MOBILE', 'count': 2300, 'volume': Decimal('340000')},
            {'type': 'PAYMENT', 'channel': 'WEB', 'count': 1100, 'volume': Decimal('165000')},
            {'type': 'DEPOSIT', 'channel': 'BRANCH', 'count': 450, 'volume': Decimal('78000')},
        ]
        
        for tx_type in transaction_types:
            data.append({
                'transaction_type': tx_type['type'],
                'channel': tx_type['channel'],
                'transaction_count': tx_type['count'],
                'total_volume': tx_type['volume'],
                'average_amount': tx_type['volume'] / tx_type['count'],
                'currency': currency.code
            })
            
            totals['total_transactions'] += tx_type['count']
            totals['total_volume'] += tx_type['volume']
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=period_start,
            period_end=period_end,
            data=data,
            totals=dict(totals),
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code
            }
        )
    
    def product_performance_report(self, currency: Currency = Currency.USD) -> ReportResult:
        """
        Generate product performance report
        """
        start_time = datetime.now(timezone.utc)
        report_id = "product_performance"
        
        data = []
        totals = {
            'total_accounts': 0,
            'total_balance': Decimal('0'),
            'total_revenue': Decimal('0')
        }
        
        if self.account_manager:
            accounts = self.account_manager.get_all_accounts()
            
            # Group by product type
            product_stats = {}
            
            for account in accounts:
                if account.currency != currency or account.state != AccountState.ACTIVE:
                    continue
                
                product_key = account.product_type.value
                
                if product_key not in product_stats:
                    product_stats[product_key] = {
                        'product_type': product_key,
                        'account_count': 0,
                        'total_balance': Decimal('0'),
                        'revenue': Decimal('0'),
                        'delinquency_rate': Decimal('0'),
                        'currency': currency.code
                    }
                
                balance = self.account_manager.get_account_balance(account.id)
                
                product_stats[product_key]['account_count'] += 1
                product_stats[product_key]['total_balance'] += balance.amount
                
                # Mock revenue calculation
                if account.is_loan_product and account.interest_rate:
                    monthly_revenue = balance.amount * (account.interest_rate / 12)
                    product_stats[product_key]['revenue'] += monthly_revenue
                
                totals['total_accounts'] += 1
                totals['total_balance'] += balance.amount
            
            data = list(product_stats.values())
            
            # Calculate totals
            for item in data:
                totals['total_revenue'] += item['revenue']
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=start_time.replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=end_time,
            data=data,
            totals=dict(totals),
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code
            }
        )
    
    def customer_segment_report(self, currency: Currency = Currency.USD) -> ReportResult:
        """
        Generate customer segmentation report
        """
        start_time = datetime.now(timezone.utc)
        report_id = "customer_segment"
        
        data = []
        totals = {
            'total_customers': 0,
            'total_balance': Decimal('0')
        }
        
        # Mock customer segments
        segments = [
            {'segment': 'High Value', 'tier': 'GOLD', 'customers': 150, 'avg_balance': Decimal('50000')},
            {'segment': 'Medium Value', 'tier': 'SILVER', 'customers': 800, 'avg_balance': Decimal('15000')},
            {'segment': 'Basic', 'tier': 'BRONZE', 'customers': 2500, 'avg_balance': Decimal('3000')},
            {'segment': 'New', 'tier': 'STANDARD', 'customers': 300, 'avg_balance': Decimal('1500')},
        ]
        
        for segment in segments:
            total_balance = segment['avg_balance'] * segment['customers']
            
            data.append({
                'customer_segment': segment['segment'],
                'customer_tier': segment['tier'],
                'customer_count': segment['customers'],
                'average_balance': segment['avg_balance'],
                'total_balance': total_balance,
                'currency': currency.code
            })
            
            totals['total_customers'] += segment['customers']
            totals['total_balance'] += total_balance
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=start_time.replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=end_time,
            data=data,
            totals=dict(totals),
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code
            }
        )
    
    def collection_performance_report(self, currency: Currency = Currency.USD) -> ReportResult:
        """
        Generate collections performance report
        """
        start_time = datetime.now(timezone.utc)
        report_id = "collection_performance"
        
        data = []
        totals = {
            'total_cases': 0,
            'total_recovered': Decimal('0'),
            'recovery_rate': Decimal('0')
        }
        
        if self.collections_manager:
            # Mock collections performance data
            performance_data = [
                {'stage': 'Early Collections', 'cases': 120, 'recovered': Decimal('45000'), 'target': Decimal('60000')},
                {'stage': 'Late Collections', 'cases': 85, 'recovered': Decimal('25000'), 'target': Decimal('50000')},
                {'stage': 'Legal Action', 'cases': 25, 'recovered': Decimal('15000'), 'target': Decimal('40000')},
                {'stage': 'Write-off Recovery', 'cases': 10, 'recovered': Decimal('2000'), 'target': Decimal('5000')},
            ]
            
            for item in performance_data:
                recovery_rate = Decimal('0')
                if item['target'] > 0:
                    recovery_rate = (item['recovered'] / item['target']) * 100
                
                data.append({
                    'collection_stage': item['stage'],
                    'active_cases': item['cases'],
                    'amount_recovered': item['recovered'],
                    'recovery_target': item['target'],
                    'recovery_rate': recovery_rate,
                    'currency': currency.code
                })
                
                totals['total_cases'] += item['cases']
                totals['total_recovered'] += item['recovered']
        
        # Calculate overall recovery rate
        total_target = sum(item['target'] for item in performance_data)
        if total_target > 0:
            totals['recovery_rate'] = (totals['total_recovered'] / total_target) * 100
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=report_id,
            generated_at=end_time,
            period_start=start_time.replace(hour=0, minute=0, second=0, microsecond=0),
            period_end=end_time,
            data=data,
            totals=dict(totals),
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'currency': currency.code
            }
        )
    
    def create_report_definition(self, definition: ReportDefinition) -> ReportDefinition:
        """
        Create a custom report definition
        """
        now = datetime.now(timezone.utc)
        
        if not definition.id:
            definition.id = str(uuid.uuid4())
        
        definition.created_at = now
        definition.updated_at = now
        
        # Save to storage
        definition_dict = self._report_definition_to_dict(definition)
        self.storage.save(self.report_definitions_table, definition.id, definition_dict)
        
        # Log audit event
        if self.audit_trail:
            self.audit_trail.log_event(
                event_type=AuditEventType.PRODUCT_CREATED,
                entity_type="report_definition",
                entity_id=definition.id,
                metadata={
                    "name": definition.name,
                    "report_type": definition.report_type.value,
                    "created_by": definition.created_by
                }
            )
        
        return definition
    
    def run_report(
        self,
        report_id: str,
        period_start: datetime = None,
        period_end: datetime = None,
        filters: Dict[str, Any] = None
    ) -> ReportResult:
        """
        Execute a report by ID (built-in or custom)
        """
        # Handle built-in reports
        if report_id == "portfolio_summary":
            currency = Currency.USD
            if filters and 'currency' in filters:
                currency = Currency[filters['currency']]
            return self.portfolio_summary(currency)
        
        elif report_id == "loan_portfolio":
            return self.loan_portfolio_report(filters)
        
        elif report_id == "deposit_portfolio":
            return self.deposit_portfolio_report(filters)
        
        elif report_id == "delinquency":
            currency = Currency.USD
            if filters and 'currency' in filters:
                currency = Currency[filters['currency']]
            return self.delinquency_report(currency)
        
        elif report_id == "income_statement":
            currency = Currency.USD
            if filters and 'currency' in filters:
                currency = Currency[filters['currency']]
            
            if not period_start:
                period_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if not period_end:
                period_end = datetime.now(timezone.utc)
            
            return self.income_statement(period_start, period_end, currency)
        
        elif report_id == "transaction_volume":
            currency = Currency.USD
            if filters and 'currency' in filters:
                currency = Currency[filters['currency']]
            
            if not period_start:
                period_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if not period_end:
                period_end = datetime.now(timezone.utc)
            
            return self.transaction_volume_report(period_start, period_end, currency)
        
        elif report_id == "product_performance":
            currency = Currency.USD
            if filters and 'currency' in filters:
                currency = Currency[filters['currency']]
            return self.product_performance_report(currency)
        
        elif report_id == "customer_segment":
            currency = Currency.USD
            if filters and 'currency' in filters:
                currency = Currency[filters['currency']]
            return self.customer_segment_report(currency)
        
        elif report_id == "collection_performance":
            currency = Currency.USD
            if filters and 'currency' in filters:
                currency = Currency[filters['currency']]
            return self.collection_performance_report(currency)
        
        else:
            # Try to load custom report definition
            definition = self._load_report_definition(report_id)
            if not definition:
                raise ValueError(f"Report {report_id} not found")
            
            return self._execute_custom_report(definition, period_start, period_end, filters)
    
    def list_report_definitions(self, report_type: ReportType = None) -> List[ReportDefinition]:
        """
        List available report definitions
        """
        definitions = []
        
        # Add built-in reports
        built_in_reports = [
            ReportDefinition(
                id="portfolio_summary",
                name="Portfolio Summary",
                description="Overall portfolio health metrics",
                report_type=ReportType.PORTFOLIO_SUMMARY,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            ),
            ReportDefinition(
                id="loan_portfolio",
                name="Loan Portfolio Report",
                description="Loan portfolio analysis by product and status",
                report_type=ReportType.LOAN_PORTFOLIO,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            ),
            ReportDefinition(
                id="deposit_portfolio",
                name="Deposit Portfolio Report",
                description="Deposit portfolio analysis",
                report_type=ReportType.DEPOSIT_PORTFOLIO,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            ),
            ReportDefinition(
                id="delinquency",
                name="Delinquency Aging Report",
                description="Loan delinquency by aging buckets",
                report_type=ReportType.DELINQUENCY,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            ),
            ReportDefinition(
                id="income_statement",
                name="Income Statement",
                description="Profit and loss statement",
                report_type=ReportType.INCOME_STATEMENT,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            ),
            ReportDefinition(
                id="transaction_volume",
                name="Transaction Volume Report",
                description="Transaction volume by type and channel",
                report_type=ReportType.TRANSACTION_VOLUME,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            ),
            ReportDefinition(
                id="product_performance",
                name="Product Performance Report",
                description="Performance metrics by product type",
                report_type=ReportType.PRODUCT_PERFORMANCE,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            ),
            ReportDefinition(
                id="customer_segment",
                name="Customer Segment Report",
                description="Customer analysis by segment",
                report_type=ReportType.CUSTOMER_SEGMENT,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            ),
            ReportDefinition(
                id="collection_performance",
                name="Collection Performance Report",
                description="Collections recovery and performance metrics",
                report_type=ReportType.COLLECTION_PERFORMANCE,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                is_template=True
            )
        ]
        
        definitions.extend(built_in_reports)
        
        # Load custom definitions from storage
        try:
            all_definitions = self.storage.load_all(self.report_definitions_table)
            for def_dict in all_definitions:
                custom_def = self._report_definition_from_dict(def_dict)
                definitions.append(custom_def)
        except:
            pass  # Table might not exist yet
        
        # Apply filter
        if report_type:
            definitions = [d for d in definitions if d.report_type == report_type]
        
        return definitions
    
    def schedule_report(
        self,
        report_id: str,
        frequency: str,
        recipients: List[str]
    ) -> Dict[str, Any]:
        """
        Schedule a report for regular execution (stores config only)
        """
        schedule_id = str(uuid.uuid4())
        schedule_config = {
            'id': schedule_id,
            'report_id': report_id,
            'frequency': frequency,
            'recipients': recipients,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'active': True
        }
        
        # Store schedule configuration
        self.storage.save("report_schedules", schedule_id, schedule_config)
        
        if self.audit_trail:
            self.audit_trail.log_event(
                event_type=AuditEventType.PRODUCT_CREATED,
                entity_type="report_schedule",
                entity_id=schedule_id,
                metadata={
                    "report_id": report_id,
                    "frequency": frequency,
                    "recipient_count": len(recipients)
                }
            )
        
        return schedule_config
    
    def export_report(self, result: ReportResult, format: ReportFormat) -> Union[Dict, str]:
        """
        Export report result in specified format
        """
        if format == ReportFormat.DICT:
            return {
                'report_id': result.report_id,
                'generated_at': result.generated_at.isoformat(),
                'period_start': result.period_start.isoformat(),
                'period_end': result.period_end.isoformat(),
                'data': result.data,
                'totals': result.totals,
                'metadata': result.metadata
            }
        
        elif format == ReportFormat.JSON:
            export_dict = self.export_report(result, ReportFormat.DICT)
            return json.dumps(export_dict, indent=2, default=str)
        
        elif format == ReportFormat.CSV:
            output = io.StringIO()
            
            if result.data:
                # Get headers from first row
                headers = list(result.data[0].keys())
                writer = csv.DictWriter(output, fieldnames=headers)
                writer.writeheader()
                
                for row in result.data:
                    writer.writerow(row)
            
            csv_content = output.getvalue()
            output.close()
            return csv_content
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def _execute_custom_report(
        self,
        definition: ReportDefinition,
        period_start: datetime = None,
        period_end: datetime = None,
        filters: Dict[str, Any] = None
    ) -> ReportResult:
        """
        Execute a custom report definition
        """
        start_time = datetime.now(timezone.utc)
        
        if not period_start:
            period_start = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        if not period_end:
            period_end = start_time
        
        # Mock custom report execution
        data = [{
            'dimension': 'sample',
            'metric_value': Decimal('1000'),
            'currency': 'USD'
        }]
        
        totals = {'total_value': Decimal('1000')}
        
        end_time = datetime.now(timezone.utc)
        generation_time = int((end_time - start_time).total_seconds() * 1000)
        
        return ReportResult(
            report_id=definition.id,
            generated_at=end_time,
            period_start=period_start,
            period_end=period_end,
            data=data,
            totals=totals,
            metadata={
                'row_count': len(data),
                'generation_time_ms': generation_time,
                'definition_name': definition.name,
                'custom_report': True
            }
        )
    
    def _load_report_definition(self, definition_id: str) -> Optional[ReportDefinition]:
        """
        Load a report definition from storage
        """
        try:
            def_dict = self.storage.load(self.report_definitions_table, definition_id)
            if def_dict:
                return self._report_definition_from_dict(def_dict)
        except:
            pass
        return None
    
    def _report_definition_to_dict(self, definition: ReportDefinition) -> Dict[str, Any]:
        """
        Convert ReportDefinition to dictionary for storage
        """
        result = definition.to_dict()
        result['report_type'] = definition.report_type.value
        result['period'] = definition.period.value
        
        # Convert dimensions
        result['dimensions'] = [d.value for d in definition.dimensions]
        
        # Convert metrics
        metrics_data = []
        for metric in definition.metrics:
            metric_dict = {
                'name': metric.name,
                'field': metric.field,
                'aggregation': metric.aggregation.value,
                'format': metric.format.value
            }
            metrics_data.append(metric_dict)
        result['metrics'] = metrics_data
        
        return result
    
    def _report_definition_from_dict(self, data: Dict[str, Any]) -> ReportDefinition:
        """
        Convert dictionary to ReportDefinition
        """
        # Convert timestamps
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        # Convert dimensions
        dimensions = [DimensionType(d) for d in data.get('dimensions', [])]
        
        # Convert metrics
        metrics = []
        for metric_data in data.get('metrics', []):
            metric = MetricDefinition(
                name=metric_data['name'],
                field=metric_data['field'],
                aggregation=AggregationType(metric_data['aggregation']),
                format=MetricFormat(metric_data['format'])
            )
            metrics.append(metric)
        
        return ReportDefinition(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            name=data['name'],
            description=data['description'],
            report_type=ReportType(data['report_type']),
            dimensions=dimensions,
            metrics=metrics,
            filters=data.get('filters', {}),
            period=ReportPeriod(data['period']),
            created_by=data.get('created_by', ''),
            is_template=data.get('is_template', False)
        )