"""
Test suite for the Reporting Engine module
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock

from core_banking.reporting import (
    ReportingEngine, ReportType, ReportFormat, AggregationType,
    ReportPeriod, DimensionType, MetricFormat, MetricDefinition,
    ReportDefinition, ReportResult
)
from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.accounts import Account, ProductType, AccountState
from core_banking.ledger import AccountType
from core_banking.loans import Loan, LoanState
from core_banking.collections import CollectionCase, DelinquencyStatus


# Global fixtures
@pytest.fixture
def storage():
    return InMemoryStorage()

@pytest.fixture
def audit_trail():
    return AuditTrail(InMemoryStorage())

@pytest.fixture
def mock_account_manager():
    manager = Mock()
    
    # Mock accounts
    accounts = [
        Account(
            id="acc1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            account_number="12345",
            customer_id="cust1",
            product_type=ProductType.SAVINGS,
            account_type=AccountType.ASSET,
            currency=Currency.USD,
            name="Savings Account",
            state=AccountState.ACTIVE,
            interest_rate=Decimal('0.025')
        ),
        Account(
            id="acc2",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            account_number="67890",
            customer_id="cust2",
            product_type=ProductType.LOAN,
            account_type=AccountType.LIABILITY,
            currency=Currency.USD,
            name="Personal Loan",
            state=AccountState.ACTIVE,
            interest_rate=Decimal('0.15')
        )
    ]
    
    manager.get_all_accounts.return_value = accounts
    manager.get_account_balance.side_effect = lambda acc_id: {
        "acc1": Money(Decimal('5000'), Currency.USD),
        "acc2": Money(Decimal('10000'), Currency.USD)
    }.get(acc_id, Money(Decimal('0'), Currency.USD))
    
    return manager

@pytest.fixture
def mock_loan_manager():
    manager = Mock()
    
    loans = [
        Mock(
            id="loan1",
            product_type=ProductType.LOAN,
            state=LoanState.ACTIVE,
            principal_amount=Money(Decimal('10000'), Currency.USD)
        ),
        Mock(
            id="loan2", 
            product_type=ProductType.LOAN,
            state=LoanState.ACTIVE,
            principal_amount=Money(Decimal('15000'), Currency.USD)
        )
    ]
    
    manager.get_all_loans.return_value = loans
    manager.get_current_balance.side_effect = lambda loan_id: {
        "loan1": Money(Decimal('8000'), Currency.USD),
        "loan2": Money(Decimal('12000'), Currency.USD)
    }.get(loan_id, Money(Decimal('0'), Currency.USD))
    
    return manager

@pytest.fixture
def mock_collections_manager():
    manager = Mock()
    
    cases = [
        Mock(
            id="case1",
            loan_id="loan1",
            status=DelinquencyStatus.CURRENT,
            current_balance=Money(Decimal('8000'), Currency.USD),
            days_past_due=0
        ),
        Mock(
            id="case2",
            loan_id="loan2", 
            status=DelinquencyStatus.SERIOUS,
            current_balance=Money(Decimal('12000'), Currency.USD),
            days_past_due=75
        )
    ]
    
    manager.get_all_cases.return_value = cases
    manager.get_case_by_loan.side_effect = lambda loan_id: {
        "loan1": cases[0],
        "loan2": cases[1]
    }.get(loan_id)
    
    return manager

@pytest.fixture
def reporting_engine(storage, audit_trail, mock_account_manager, 
                    mock_loan_manager, mock_collections_manager):
    return ReportingEngine(
        storage=storage,
        account_manager=mock_account_manager,
        loan_manager=mock_loan_manager,
        collections_manager=mock_collections_manager,
        audit_trail=audit_trail
    )


class TestReportingEngine:
    """Test cases for ReportingEngine"""
    pass


class TestEnums:
    """Test enum definitions"""
    
    def test_report_type_enum(self):
        assert ReportType.PORTFOLIO_SUMMARY.value == "portfolio_summary"
        assert ReportType.LOAN_PORTFOLIO.value == "loan_portfolio"
        assert ReportType.DELINQUENCY.value == "delinquency"
        assert ReportType.CUSTOM.value == "custom"
    
    def test_report_format_enum(self):
        assert ReportFormat.DICT.value == "dict"
        assert ReportFormat.CSV.value == "csv"
        assert ReportFormat.JSON.value == "json"
    
    def test_aggregation_type_enum(self):
        assert AggregationType.SUM.value == "sum"
        assert AggregationType.COUNT.value == "count"
        assert AggregationType.AVERAGE.value == "average"
        assert AggregationType.PERCENTAGE.value == "percentage"
    
    def test_dimension_type_enum(self):
        assert DimensionType.PRODUCT.value == "product"
        assert DimensionType.CURRENCY.value == "currency"
        assert DimensionType.DELINQUENCY_STATUS.value == "delinquency_status"
    
    def test_metric_format_enum(self):
        assert MetricFormat.MONEY.value == "money"
        assert MetricFormat.PERCENTAGE.value == "percentage"
        assert MetricFormat.COUNT.value == "count"


class TestMetricDefinition:
    """Test MetricDefinition class"""
    
    def test_create_metric_definition(self):
        metric = MetricDefinition(
            name="Total Balance",
            field="balance",
            aggregation=AggregationType.SUM,
            format=MetricFormat.MONEY
        )
        
        assert metric.name == "Total Balance"
        assert metric.field == "balance"
        assert metric.aggregation == AggregationType.SUM
        assert metric.format == MetricFormat.MONEY
    
    def test_format_money_value(self):
        metric = MetricDefinition(
            name="Balance",
            field="balance",
            aggregation=AggregationType.SUM,
            format=MetricFormat.MONEY
        )
        
        money_value = Money(Decimal('1234.56'), Currency.USD)
        formatted = metric.format_value(money_value, Currency.USD)
        assert "1,234.56" in formatted
    
    def test_format_percentage_value(self):
        metric = MetricDefinition(
            name="Rate",
            field="rate",
            aggregation=AggregationType.AVERAGE,
            format=MetricFormat.PERCENTAGE
        )
        
        formatted = metric.format_value(0.0525)
        assert formatted == "5.25%"
    
    def test_format_count_value(self):
        metric = MetricDefinition(
            name="Count",
            field="count",
            aggregation=AggregationType.COUNT,
            format=MetricFormat.COUNT
        )
        
        formatted = metric.format_value(123.7)
        assert formatted == "123"


class TestReportDefinition:
    """Test ReportDefinition class"""
    
    def test_create_report_definition(self):
        now = datetime.now(timezone.utc)
        
        definition = ReportDefinition(
            id="test_report",
            created_at=now,
            updated_at=now,
            name="Test Report",
            description="A test report",
            report_type=ReportType.CUSTOM,
            dimensions=[DimensionType.PRODUCT, DimensionType.CURRENCY],
            metrics=[
                MetricDefinition("Count", "count", AggregationType.COUNT),
                MetricDefinition("Balance", "balance", AggregationType.SUM, MetricFormat.MONEY)
            ],
            filters={"currency": "USD"},
            period=ReportPeriod.MONTHLY,
            created_by="test_user",
            is_template=True
        )
        
        assert definition.name == "Test Report"
        assert definition.report_type == ReportType.CUSTOM
        assert len(definition.dimensions) == 2
        assert len(definition.metrics) == 2
        assert definition.filters["currency"] == "USD"
        assert definition.is_template is True
    
    def test_report_definition_defaults(self):
        now = datetime.now(timezone.utc)
        
        definition = ReportDefinition(
            id="test_report",
            created_at=now,
            updated_at=now,
            name="Test Report",
            description="A test report", 
            report_type=ReportType.CUSTOM
        )
        
        assert definition.dimensions == []
        assert definition.metrics == []
        assert definition.filters == {}
        assert definition.period == ReportPeriod.MONTHLY
        assert definition.created_by == ""
        assert definition.is_template is False


class TestReportResult:
    """Test ReportResult class"""
    
    def test_create_report_result(self):
        now = datetime.now(timezone.utc)
        
        result = ReportResult(
            report_id="test_report",
            generated_at=now,
            period_start=now - timedelta(days=30),
            period_end=now,
            data=[{"key": "value"}],
            totals={"total": 100},
            metadata={"rows": 1}
        )
        
        assert result.report_id == "test_report"
        assert len(result.data) == 1
        assert result.totals["total"] == 100
        assert result.metadata["rows"] == 1
    
    def test_report_result_defaults(self):
        now = datetime.now(timezone.utc)
        
        result = ReportResult(
            report_id="test_report",
            generated_at=now,
            period_start=now - timedelta(days=30),
            period_end=now
        )
        
        assert result.data == []
        assert result.totals == {}
        assert "row_count" in result.metadata
        assert result.metadata["row_count"] == 0


class TestPortfolioSummaryReport:
    """Test portfolio summary report generation"""
    
    def test_portfolio_summary_generation(self, reporting_engine):
        result = reporting_engine.portfolio_summary(Currency.USD)
        
        assert result.report_id == "portfolio_summary"
        assert len(result.data) == 1
        assert "total_assets" in result.data[0]
        assert "total_liabilities" in result.data[0]
        assert "equity" in result.data[0]
        assert "npl_ratio" in result.data[0]
        assert result.data[0]["currency"] == "USD"
        
        # Verify totals match data
        assert result.totals["currency"] == "USD"
        assert "generation_time_ms" in result.metadata
    
    def test_portfolio_summary_empty_data(self, storage, audit_trail):
        # Test with no managers
        engine = ReportingEngine(storage=storage, audit_trail=audit_trail)
        result = engine.portfolio_summary(Currency.USD)
        
        assert result.report_id == "portfolio_summary"
        assert len(result.data) == 1
        assert result.data[0]["total_assets"] == 0
        assert result.data[0]["total_liabilities"] == 0


class TestLoanPortfolioReport:
    """Test loan portfolio report generation"""
    
    def test_loan_portfolio_report_generation(self, reporting_engine):
        result = reporting_engine.loan_portfolio_report()
        
        assert result.report_id == "loan_portfolio"
        assert len(result.data) >= 0
        assert "total_loans" in result.totals
        assert "total_balance" in result.totals
        assert "par_ratio" in result.totals
        assert result.metadata["currency"] == "USD"
    
    def test_loan_portfolio_with_filters(self, reporting_engine):
        filters = {
            "currency": "USD",
            "state": "ACTIVE"
        }
        
        result = reporting_engine.loan_portfolio_report(filters)
        
        assert result.report_id == "loan_portfolio"
        assert result.metadata["filters_applied"] == filters
    
    def test_loan_portfolio_par_calculation(self, reporting_engine):
        result = reporting_engine.loan_portfolio_report()
        
        # Should have some performing and non-performing balances
        assert "performing_balance" in result.totals
        assert "non_performing_balance" in result.totals


class TestDepositPortfolioReport:
    """Test deposit portfolio report generation"""
    
    def test_deposit_portfolio_report_generation(self, reporting_engine):
        result = reporting_engine.deposit_portfolio_report()
        
        assert result.report_id == "deposit_portfolio"
        assert "total_accounts" in result.totals
        assert "total_balance" in result.totals
        assert "average_balance" in result.totals
    
    def test_deposit_portfolio_with_filters(self, reporting_engine):
        filters = {
            "currency": "USD",
            "product_type": "SAVINGS"
        }
        
        result = reporting_engine.deposit_portfolio_report(filters)
        
        assert result.metadata["filters_applied"] == filters


class TestDelinquencyReport:
    """Test delinquency aging report generation"""
    
    def test_delinquency_report_generation(self, reporting_engine):
        result = reporting_engine.delinquency_report(Currency.USD)
        
        assert result.report_id == "delinquency"
        assert len(result.data) == 5  # 5 aging buckets
        
        # Verify aging buckets
        bucket_names = [row["aging_bucket"] for row in result.data]
        expected_buckets = ["current", "1-30", "31-60", "61-90", "90+"]
        
        for bucket in expected_buckets:
            assert bucket in bucket_names
        
        # Verify structure
        for row in result.data:
            assert "case_count" in row
            assert "total_balance" in row
            assert "percentage" in row
            assert "currency" in row
    
    def test_delinquency_report_empty_collections(self, storage, audit_trail):
        # Test with no collections manager
        engine = ReportingEngine(storage=storage, audit_trail=audit_trail)
        result = engine.delinquency_report(Currency.USD)
        
        assert result.report_id == "delinquency"
        assert len(result.data) == 5  # Still has bucket structure
        assert result.totals["total_cases"] == 0


class TestIncomeStatementReport:
    """Test income statement report generation"""
    
    def test_income_statement_generation(self, reporting_engine):
        period_start = datetime.now(timezone.utc) - timedelta(days=30)
        period_end = datetime.now(timezone.utc)
        
        result = reporting_engine.income_statement(period_start, period_end, Currency.USD)
        
        assert result.report_id == "income_statement"
        assert result.period_start == period_start
        assert result.period_end == period_end
        
        # Verify income statement structure
        categories = [row["category"] for row in result.data]
        assert "Interest Income" in categories
        assert "Fee Income" in categories
        assert "Provisions" in categories
        assert "Operating Expenses" in categories
        
        # Verify totals
        assert "interest_income" in result.totals
        assert "fee_income" in result.totals
        assert "total_revenue" in result.totals
        assert "net_income" in result.totals
    
    def test_income_statement_calculations(self, reporting_engine):
        period_start = datetime.now(timezone.utc) - timedelta(days=30)
        period_end = datetime.now(timezone.utc)
        
        result = reporting_engine.income_statement(period_start, period_end, Currency.USD)
        
        # Verify calculations
        expected_revenue = result.totals["interest_income"] + result.totals["fee_income"]
        assert result.totals["total_revenue"] == expected_revenue
        
        expected_net = (result.totals["total_revenue"] + 
                       result.totals["provisions"] + 
                       result.totals["operating_expenses"])
        assert result.totals["net_income"] == expected_net


class TestTransactionVolumeReport:
    """Test transaction volume report generation"""
    
    def test_transaction_volume_report_generation(self, reporting_engine):
        period_start = datetime.now(timezone.utc) - timedelta(days=7)
        period_end = datetime.now(timezone.utc)
        
        result = reporting_engine.transaction_volume_report(period_start, period_end, Currency.USD)
        
        assert result.report_id == "transaction_volume"
        assert result.period_start == period_start
        assert result.period_end == period_end
        
        # Verify transaction data structure
        for row in result.data:
            assert "transaction_type" in row
            assert "channel" in row
            assert "transaction_count" in row
            assert "total_volume" in row
            assert "average_amount" in row
        
        assert "total_transactions" in result.totals
        assert "total_volume" in result.totals
    
    def test_transaction_volume_calculations(self, reporting_engine):
        period_start = datetime.now(timezone.utc) - timedelta(days=7)
        period_end = datetime.now(timezone.utc)
        
        result = reporting_engine.transaction_volume_report(period_start, period_end, Currency.USD)
        
        # Verify average calculations
        for row in result.data:
            expected_avg = row["total_volume"] / row["transaction_count"]
            assert row["average_amount"] == expected_avg


class TestProductPerformanceReport:
    """Test product performance report generation"""
    
    def test_product_performance_report_generation(self, reporting_engine):
        result = reporting_engine.product_performance_report(Currency.USD)
        
        assert result.report_id == "product_performance"
        
        # Verify structure
        for row in result.data:
            assert "product_type" in row
            assert "account_count" in row
            assert "total_balance" in row
            assert "revenue" in row
            assert "delinquency_rate" in row
        
        assert "total_accounts" in result.totals
        assert "total_balance" in result.totals
        assert "total_revenue" in result.totals


class TestCustomerSegmentReport:
    """Test customer segment report generation"""
    
    def test_customer_segment_report_generation(self, reporting_engine):
        result = reporting_engine.customer_segment_report(Currency.USD)
        
        assert result.report_id == "customer_segment"
        
        # Verify customer segment structure
        for row in result.data:
            assert "customer_segment" in row
            assert "customer_tier" in row
            assert "customer_count" in row
            assert "average_balance" in row
            assert "total_balance" in row
        
        assert "total_customers" in result.totals
        assert "total_balance" in result.totals


class TestCollectionPerformanceReport:
    """Test collection performance report generation"""
    
    def test_collection_performance_report_generation(self, reporting_engine):
        result = reporting_engine.collection_performance_report(Currency.USD)
        
        assert result.report_id == "collection_performance"
        
        # Verify collections structure
        for row in result.data:
            assert "collection_stage" in row
            assert "active_cases" in row
            assert "amount_recovered" in row
            assert "recovery_target" in row
            assert "recovery_rate" in row
        
        assert "total_cases" in result.totals
        assert "total_recovered" in result.totals
        assert "recovery_rate" in result.totals


class TestCustomReports:
    """Test custom report definition CRUD operations"""
    
    def test_create_report_definition(self, reporting_engine):
        definition = ReportDefinition(
            id="",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            name="Custom Loan Report",
            description="Custom loan analysis",
            report_type=ReportType.CUSTOM,
            dimensions=[DimensionType.PRODUCT, DimensionType.CURRENCY],
            metrics=[
                MetricDefinition("Count", "count", AggregationType.COUNT),
                MetricDefinition("Balance", "balance", AggregationType.SUM, MetricFormat.MONEY)
            ],
            created_by="test_user"
        )
        
        saved_definition = reporting_engine.create_report_definition(definition)
        
        assert saved_definition.id is not None
        assert saved_definition.id != ""
        assert saved_definition.name == "Custom Loan Report"
        assert len(saved_definition.dimensions) == 2
        assert len(saved_definition.metrics) == 2
    
    def test_list_report_definitions(self, reporting_engine):
        definitions = reporting_engine.list_report_definitions()
        
        # Should include built-in reports
        report_ids = [d.id for d in definitions]
        assert "portfolio_summary" in report_ids
        assert "loan_portfolio" in report_ids
        assert "delinquency" in report_ids
        assert "income_statement" in report_ids
    
    def test_list_report_definitions_with_filter(self, reporting_engine):
        definitions = reporting_engine.list_report_definitions(ReportType.PORTFOLIO_SUMMARY)
        
        assert len(definitions) == 1
        assert definitions[0].report_type == ReportType.PORTFOLIO_SUMMARY
    
    def test_run_built_in_report(self, reporting_engine):
        result = reporting_engine.run_report("portfolio_summary")
        
        assert result.report_id == "portfolio_summary"
        assert len(result.data) > 0
    
    def test_run_built_in_report_with_filters(self, reporting_engine):
        filters = {"currency": "USD"}
        result = reporting_engine.run_report("loan_portfolio", filters=filters)
        
        assert result.report_id == "loan_portfolio"
        assert result.metadata.get("filters_applied") == filters
    
    def test_run_nonexistent_report(self, reporting_engine):
        with pytest.raises(ValueError, match="Report nonexistent not found"):
            reporting_engine.run_report("nonexistent")


class TestReportScheduling:
    """Test report scheduling functionality"""
    
    def test_schedule_report(self, reporting_engine):
        schedule = reporting_engine.schedule_report(
            report_id="portfolio_summary",
            frequency="daily",
            recipients=["admin@bank.com", "risk@bank.com"]
        )
        
        assert schedule["report_id"] == "portfolio_summary"
        assert schedule["frequency"] == "daily"
        assert len(schedule["recipients"]) == 2
        assert schedule["active"] is True
        assert "id" in schedule
        assert "created_at" in schedule


class TestReportExport:
    """Test report export functionality"""
    
    def test_export_dict_format(self, reporting_engine):
        result = reporting_engine.portfolio_summary(Currency.USD)
        exported = reporting_engine.export_report(result, ReportFormat.DICT)
        
        assert isinstance(exported, dict)
        assert "report_id" in exported
        assert "generated_at" in exported
        assert "data" in exported
        assert "totals" in exported
        assert "metadata" in exported
    
    def test_export_json_format(self, reporting_engine):
        result = reporting_engine.portfolio_summary(Currency.USD)
        exported = reporting_engine.export_report(result, ReportFormat.JSON)
        
        assert isinstance(exported, str)
        
        # Should be valid JSON
        import json
        parsed = json.loads(exported)
        assert "report_id" in parsed
        assert "data" in parsed
    
    def test_export_csv_format(self, reporting_engine):
        result = reporting_engine.portfolio_summary(Currency.USD)
        exported = reporting_engine.export_report(result, ReportFormat.CSV)
        
        assert isinstance(exported, str)
        
        # Should have CSV headers
        lines = exported.strip().split('\n')
        assert len(lines) >= 2  # Header + at least one data row
        
        # Verify CSV structure
        headers = lines[0].split(',')
        assert len(headers) > 0
    
    def test_export_invalid_format(self, reporting_engine):
        result = reporting_engine.portfolio_summary(Currency.USD)
        
        with pytest.raises(ValueError, match="Unsupported export format"):
            reporting_engine.export_report(result, "invalid_format")


class TestEmptyDataHandling:
    """Test handling of empty data scenarios"""
    
    def test_empty_accounts_handling(self, storage, audit_trail):
        # Create engine with mock managers that return empty data
        mock_account_manager = Mock()
        mock_account_manager.get_all_accounts.return_value = []
        
        engine = ReportingEngine(
            storage=storage,
            audit_trail=audit_trail,
            account_manager=mock_account_manager
        )
        
        result = engine.portfolio_summary(Currency.USD)
        
        assert result.data[0]["total_assets"] == 0
        assert result.data[0]["total_liabilities"] == 0
    
    def test_empty_loans_handling(self, storage, audit_trail):
        mock_loan_manager = Mock()
        mock_loan_manager.get_all_loans.return_value = []
        
        engine = ReportingEngine(
            storage=storage,
            audit_trail=audit_trail,
            loan_manager=mock_loan_manager
        )
        
        result = engine.loan_portfolio_report()
        
        assert result.totals["total_loans"] == 0
        assert result.totals["total_balance"] == 0


class TestMultiCurrencyReporting:
    """Test multi-currency reporting scenarios"""
    
    def test_portfolio_summary_different_currencies(self, storage, audit_trail):
        # Create accounts in different currencies
        mock_account_manager = Mock()
        
        accounts = [
            Account(
                id="usd_acc",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                account_number="12345",
                customer_id="cust1",
                product_type=ProductType.SAVINGS,
                account_type=AccountType.ASSET,
                currency=Currency.USD,
                name="USD Savings",
                state=AccountState.ACTIVE
            ),
            Account(
                id="eur_acc",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                account_number="67890",
                customer_id="cust1",
                product_type=ProductType.SAVINGS,
                account_type=AccountType.ASSET,
                currency=Currency.EUR,
                name="EUR Savings",
                state=AccountState.ACTIVE
            )
        ]
        
        mock_account_manager.get_all_accounts.return_value = accounts
        mock_account_manager.get_account_balance.side_effect = lambda acc_id: {
            "usd_acc": Money(Decimal('1000'), Currency.USD),
            "eur_acc": Money(Decimal('2000'), Currency.EUR)
        }.get(acc_id, Money(Decimal('0'), Currency.USD))
        
        engine = ReportingEngine(
            storage=storage,
            audit_trail=audit_trail,
            account_manager=mock_account_manager
        )
        
        # Test USD report
        usd_result = engine.portfolio_summary(Currency.USD)
        assert usd_result.data[0]["currency"] == "USD"
        assert usd_result.data[0]["total_assets"] == 1000
        
        # Test EUR report
        eur_result = engine.portfolio_summary(Currency.EUR)
        assert eur_result.data[0]["currency"] == "EUR"
        assert eur_result.data[0]["total_assets"] == 2000
    
    def test_currency_filtering_in_reports(self, reporting_engine):
        # Test with explicit currency filter
        filters = {"currency": "USD"}
        result = reporting_engine.loan_portfolio_report(filters)
        
        assert result.metadata["currency"] == "USD"


class TestReportMetadata:
    """Test report metadata and timing"""
    
    def test_report_metadata_structure(self, reporting_engine):
        result = reporting_engine.portfolio_summary(Currency.USD)
        
        metadata = result.metadata
        assert "row_count" in metadata
        assert "generation_time_ms" in metadata
        assert "currency" in metadata
        
        assert isinstance(metadata["row_count"], int)
        assert isinstance(metadata["generation_time_ms"], int)
        assert metadata["generation_time_ms"] >= 0
    
    def test_report_timing(self, reporting_engine):
        result = reporting_engine.portfolio_summary(Currency.USD)
        
        # Generation time should be reasonable (less than 1 second for tests)
        assert result.metadata["generation_time_ms"] < 1000
        
        # Generated timestamp should be recent
        time_diff = datetime.now(timezone.utc) - result.generated_at
        assert time_diff.total_seconds() < 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])