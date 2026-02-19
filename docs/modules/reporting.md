# Reporting Module

The reporting module provides a comprehensive dynamic reporting engine with configurable reports, regulatory templates, and real-time portfolio analytics. It supports custom report definitions, multiple export formats, and automated report generation for compliance and business intelligence.

## Overview

The reporting system enables:

- **Dynamic Reports**: Configure custom reports without code changes
- **Portfolio Analytics**: Real-time analysis of loan and deposit portfolios
- **Regulatory Reports**: Pre-built templates for regulatory compliance
- **Custom Dashboards**: Flexible metrics and dimensions for business intelligence
- **Export Formats**: Multiple output formats including CSV, JSON, and structured data
- **Scheduled Reports**: Automated report generation and distribution

## Key Concepts

### Report Types
The system supports various built-in report categories:
- **Portfolio Summary**: High-level portfolio overview and KPIs
- **Loan Portfolio**: Detailed loan performance analysis
- **Deposit Portfolio**: Deposit account analysis and trends
- **Delinquency Reports**: Past-due account analysis and aging
- **Financial Statements**: Income statement, balance sheet, cash flow
- **Collection Performance**: Recovery rates and collection metrics
- **Transaction Analytics**: Volume and trend analysis
- **Custom Reports**: User-defined reports with flexible dimensions

### Report Dimensions
Data can be grouped and analyzed across multiple dimensions:
- **Product**: Group by product types (savings, loans, credit lines)
- **Currency**: Multi-currency reporting and analysis
- **Customer Tier**: Segment by KYC tier or risk profile
- **Geographic**: Analysis by branch, region, or location
- **Time Period**: Daily, weekly, monthly, quarterly, yearly views
- **Delinquency Status**: Current, 30-60-90+ day buckets

## Core Classes

### ReportDefinition

Defines a configurable report template:

```python
from core_banking.reporting import ReportDefinition, ReportType, MetricDefinition, AggregationType

# Define custom loan portfolio report
loan_portfolio_report = ReportDefinition(
    name="Loan Portfolio Analysis",
    description="Detailed analysis of active loan portfolio",
    report_type=ReportType.LOAN_PORTFOLIO,
    
    # Data source configuration
    entity_type="loan",
    base_filters={
        "status": ["active", "disbursed"],
        "balance_greater_than": 0
    },
    
    # Metrics to calculate
    metrics=[
        MetricDefinition(
            name="total_outstanding",
            display_name="Total Outstanding",
            field="current_balance",
            aggregation=AggregationType.SUM,
            format=MetricFormat.MONEY
        ),
        MetricDefinition(
            name="average_balance",
            display_name="Average Balance",
            field="current_balance",
            aggregation=AggregationType.AVERAGE,
            format=MetricFormat.MONEY
        ),
        MetricDefinition(
            name="loan_count",
            display_name="Number of Loans",
            field="id",
            aggregation=AggregationType.COUNT,
            format=MetricFormat.COUNT
        ),
        MetricDefinition(
            name="default_rate",
            display_name="Default Rate",
            field="status",
            aggregation=AggregationType.PERCENTAGE,
            format=MetricFormat.PERCENTAGE,
            conditions={"status": "defaulted"}
        )
    ],
    
    # Grouping dimensions
    dimensions=[
        DimensionDefinition(
            name="product_type",
            display_name="Product Type",
            field="product_type",
            dimension_type=DimensionType.PRODUCT
        ),
        DimensionDefinition(
            name="origination_month",
            display_name="Origination Month",
            field="originated_at",
            dimension_type=DimensionType.DATE,
            date_format="YYYY-MM"
        )
    ],
    
    # Default sorting and limits
    sort_by="total_outstanding",
    sort_order="DESC",
    limit=100,
    
    created_by="admin",
    is_active=True
)
```

### MetricDefinition

Defines individual metrics within reports:

```python
from core_banking.reporting import MetricDefinition, AggregationType, MetricFormat

@dataclass
class MetricDefinition:
    name: str
    display_name: str
    field: str
    aggregation: AggregationType
    format: MetricFormat = MetricFormat.DECIMAL
    conditions: Dict[str, Any] = field(default_factory=dict)
    
    # Advanced metric options
    calculation_formula: Optional[str] = None  # For calculated metrics
    threshold_warning: Optional[Decimal] = None
    threshold_critical: Optional[Decimal] = None

# Example metrics
metrics = [
    # Simple sum metric
    MetricDefinition(
        name="total_deposits",
        display_name="Total Deposits",
        field="balance",
        aggregation=AggregationType.SUM,
        format=MetricFormat.MONEY
    ),
    
    # Conditional count
    MetricDefinition(
        name="high_balance_accounts",
        display_name="Accounts >$10k",
        field="id",
        aggregation=AggregationType.COUNT,
        conditions={"balance_greater_than": 10000.00}
    ),
    
    # Calculated percentage
    MetricDefinition(
        name="utilization_rate",
        display_name="Credit Utilization",
        field="balance_used",
        aggregation=AggregationType.PERCENTAGE,
        calculation_formula="sum(balance_used) / sum(credit_limit) * 100",
        format=MetricFormat.PERCENTAGE,
        threshold_warning=Decimal("75.0"),
        threshold_critical=Decimal("90.0")
    )
]
```

### ReportResult

Contains generated report data and metadata:

```python
from core_banking.reporting import ReportResult, ReportFormat

@dataclass
class ReportResult:
    report_definition_id: str
    generated_at: datetime
    parameters: Dict[str, Any]
    
    # Report data
    data: List[Dict[str, Any]]  # Main report data
    summary: Dict[str, Any]     # Summary statistics
    metadata: Dict[str, Any]    # Additional metadata
    
    # Performance info
    execution_time_ms: int
    row_count: int
    
    def to_csv(self) -> str:
        """Export report data as CSV"""
        if not self.data:
            return ""
        
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=self.data[0].keys())
        writer.writeheader()
        writer.writerows(self.data)
        
        return output.getvalue()
    
    def to_json(self) -> str:
        """Export report as JSON"""
        return json.dumps({
            "report_id": self.report_definition_id,
            "generated_at": self.generated_at.isoformat(),
            "parameters": self.parameters,
            "summary": self.summary,
            "data": self.data,
            "metadata": self.metadata
        }, indent=2, default=str)
```

## Report Engine

### ReportEngine

Main interface for report generation:

```python
from core_banking.reporting import ReportEngine

class ReportEngine:
    def __init__(
        self,
        storage: StorageInterface,
        ledger: GeneralLedger,
        account_manager: AccountManager,
        loan_manager: LoanManager,
        credit_manager: CreditLineManager
    ):
        self.storage = storage
        self.ledger = ledger
        self.account_manager = account_manager
        self.loan_manager = loan_manager
        self.credit_manager = credit_manager
    
    def create_report_definition(self, definition: ReportDefinition) -> str:
        """Create new report definition"""
        
        definition.id = str(uuid.uuid4())
        definition.created_at = datetime.now(timezone.utc)
        
        # Validate definition
        self._validate_report_definition(definition)
        
        self.storage.store(definition)
        
        return definition.id
    
    def generate_report(
        self,
        definition_id: str,
        parameters: Dict[str, Any] = None,
        format: ReportFormat = ReportFormat.DICT
    ) -> ReportResult:
        """Generate report from definition"""
        
        start_time = datetime.now()
        definition = self.get_report_definition(definition_id)
        
        if not definition or not definition.is_active:
            raise ValueError("Invalid or inactive report definition")
        
        # Merge parameters with defaults
        params = parameters or {}
        
        # Get base data
        raw_data = self._fetch_report_data(definition, params)
        
        # Apply filters
        filtered_data = self._apply_filters(raw_data, definition, params)
        
        # Calculate metrics
        report_data = self._calculate_metrics(filtered_data, definition)
        
        # Apply grouping and aggregation
        if definition.dimensions:
            report_data = self._apply_grouping(report_data, definition)
        
        # Sort and limit results
        report_data = self._sort_and_limit(report_data, definition)
        
        # Calculate summary statistics
        summary = self._calculate_summary(report_data, definition)
        
        # Generate metadata
        metadata = self._generate_metadata(definition, params)
        
        end_time = datetime.now()
        execution_time = int((end_time - start_time).total_seconds() * 1000)
        
        result = ReportResult(
            report_definition_id=definition_id,
            generated_at=end_time,
            parameters=params,
            data=report_data,
            summary=summary,
            metadata=metadata,
            execution_time_ms=execution_time,
            row_count=len(report_data)
        )
        
        return result
```

## Built-in Reports

### Portfolio Summary Report

```python
def generate_portfolio_summary(
    self,
    as_of_date: date = None,
    currency: Currency = Currency.USD
) -> Dict[str, Any]:
    """Generate high-level portfolio summary"""
    
    if not as_of_date:
        as_of_date = date.today()
    
    # Get all active accounts
    accounts = self.account_manager.get_active_accounts(as_of_date)
    loans = self.loan_manager.get_active_loans(as_of_date)
    credit_lines = self.credit_manager.get_active_accounts(as_of_date)
    
    # Calculate totals
    total_deposits = sum(
        acc.balance.amount for acc in accounts 
        if acc.product_type in [ProductType.SAVINGS, ProductType.CHECKING]
        and acc.balance.currency == currency
    )
    
    total_loans = sum(
        loan.current_balance.amount for loan in loans
        if loan.current_balance.currency == currency
    )
    
    total_credit_lines = sum(
        acc.balance.amount for acc in credit_lines
        if acc.balance.currency == currency
    )
    
    # Calculate key metrics
    summary = {
        "as_of_date": as_of_date.isoformat(),
        "currency": currency.code,
        
        # Asset portfolio
        "loans": {
            "count": len(loans),
            "total_outstanding": total_loans,
            "average_balance": total_loans / len(loans) if loans else 0
        },
        
        # Liability portfolio
        "deposits": {
            "count": len([a for a in accounts if a.product_type in [ProductType.SAVINGS, ProductType.CHECKING]]),
            "total_balance": total_deposits,
            "average_balance": total_deposits / len(accounts) if accounts else 0
        },
        
        # Credit lines
        "credit_lines": {
            "count": len(credit_lines),
            "total_outstanding": total_credit_lines,
            "total_available": sum(
                (acc.credit_limit - acc.balance).amount 
                for acc in credit_lines
            )
        },
        
        # Key ratios
        "loan_to_deposit_ratio": (total_loans / total_deposits * 100) if total_deposits > 0 else 0,
        "net_interest_income": self._calculate_net_interest_income(as_of_date),
        
        # Portfolio health
        "delinquency_rate": self._calculate_portfolio_delinquency_rate(as_of_date),
        "charge_off_rate": self._calculate_charge_off_rate(as_of_date),
    }
    
    return summary
```

### Delinquency Report

```python
def generate_delinquency_report(
    self,
    as_of_date: date = None,
    product_types: List[ProductType] = None
) -> Dict[str, Any]:
    """Generate detailed delinquency analysis"""
    
    if not as_of_date:
        as_of_date = date.today()
    
    # Get all loans and credit lines
    loans = self.loan_manager.get_all_loans()
    credit_lines = self.credit_manager.get_all_accounts()
    
    # Filter by product types if specified
    if product_types:
        loans = [l for l in loans if l.product_type in product_types]
    
    # Categorize by delinquency status
    buckets = {
        "current": [],
        "1-30": [],
        "31-60": [],
        "61-90": [],
        "90+": [],
        "charge_off": []
    }
    
    for loan in loans:
        days_past_due = self.loan_manager.calculate_days_past_due(loan, as_of_date)
        
        if days_past_due == 0:
            buckets["current"].append(loan)
        elif days_past_due <= 30:
            buckets["1-30"].append(loan)
        elif days_past_due <= 60:
            buckets["31-60"].append(loan)
        elif days_past_due <= 90:
            buckets["61-90"].append(loan)
        elif loan.state == LoanState.WRITTEN_OFF:
            buckets["charge_off"].append(loan)
        else:
            buckets["90+"].append(loan)
    
    # Calculate metrics for each bucket
    report = {
        "as_of_date": as_of_date.isoformat(),
        "total_accounts": len(loans),
        "total_outstanding": sum(loan.current_balance.amount for loan in loans),
        
        "delinquency_buckets": {}
    }
    
    for bucket_name, bucket_loans in buckets.items():
        bucket_balance = sum(loan.current_balance.amount for loan in bucket_loans)
        total_balance = report["total_outstanding"]
        
        report["delinquency_buckets"][bucket_name] = {
            "account_count": len(bucket_loans),
            "total_balance": bucket_balance,
            "percentage_of_accounts": (len(bucket_loans) / len(loans) * 100) if loans else 0,
            "percentage_of_balance": (bucket_balance / total_balance * 100) if total_balance > 0 else 0,
            "average_balance": bucket_balance / len(bucket_loans) if bucket_loans else 0
        }
    
    # Calculate roll rates (movement between buckets)
    report["roll_rates"] = self._calculate_roll_rates(as_of_date)
    
    # Provision recommendations
    report["provision_recommendations"] = self._calculate_provision_requirements(buckets)
    
    return report
```

### Transaction Volume Report

```python
def generate_transaction_volume_report(
    self,
    start_date: date,
    end_date: date,
    group_by: str = "daily"
) -> Dict[str, Any]:
    """Generate transaction volume and trends report"""
    
    # Get all transactions in date range
    transactions = self.transaction_processor.get_transactions_by_date_range(
        start_date, end_date
    )
    
    # Group by time period
    grouped_data = {}
    
    for transaction in transactions:
        # Determine grouping key
        if group_by == "daily":
            key = transaction.created_at.date().isoformat()
        elif group_by == "weekly":
            key = f"{transaction.created_at.year}-W{transaction.created_at.isocalendar()[1]}"
        elif group_by == "monthly":
            key = f"{transaction.created_at.year}-{transaction.created_at.month:02d}"
        else:
            key = "total"
        
        if key not in grouped_data:
            grouped_data[key] = {
                "date": key,
                "transaction_count": 0,
                "total_volume": Decimal("0"),
                "by_type": {},
                "by_channel": {}
            }
        
        # Aggregate data
        grouped_data[key]["transaction_count"] += 1
        grouped_data[key]["total_volume"] += transaction.amount.amount
        
        # By transaction type
        tx_type = transaction.transaction_type.value
        if tx_type not in grouped_data[key]["by_type"]:
            grouped_data[key]["by_type"][tx_type] = {"count": 0, "volume": Decimal("0")}
        
        grouped_data[key]["by_type"][tx_type]["count"] += 1
        grouped_data[key]["by_type"][tx_type]["volume"] += transaction.amount.amount
        
        # By channel
        channel = transaction.channel.value
        if channel not in grouped_data[key]["by_channel"]:
            grouped_data[key]["by_channel"][channel] = {"count": 0, "volume": Decimal("0")}
        
        grouped_data[key]["by_channel"][channel]["count"] += 1
        grouped_data[key]["by_channel"][channel]["volume"] += transaction.amount.amount
    
    # Calculate trends and statistics
    periods = sorted(grouped_data.keys())
    report_data = [grouped_data[period] for period in periods]
    
    # Calculate period-over-period changes
    for i in range(1, len(report_data)):
        prev_volume = report_data[i-1]["total_volume"]
        curr_volume = report_data[i]["total_volume"]
        
        if prev_volume > 0:
            growth_rate = ((curr_volume - prev_volume) / prev_volume * 100)
            report_data[i]["growth_rate"] = float(growth_rate)
    
    return {
        "report_period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "group_by": group_by
        },
        "summary": {
            "total_transactions": sum(d["transaction_count"] for d in report_data),
            "total_volume": float(sum(d["total_volume"] for d in report_data)),
            "average_daily_volume": float(
                sum(d["total_volume"] for d in report_data) / len(report_data)
            ) if report_data else 0,
            "peak_day": max(report_data, key=lambda x: x["total_volume"]) if report_data else None
        },
        "time_series_data": report_data
    }
```

## Custom Report Builder

### Dynamic Report Configuration

```python
def create_custom_report(
    self,
    name: str,
    entity_type: str,
    metrics: List[Dict[str, Any]],
    dimensions: List[Dict[str, Any]] = None,
    filters: Dict[str, Any] = None
) -> str:
    """Create custom report from configuration"""
    
    # Convert metric configurations to MetricDefinition objects
    metric_definitions = []
    for metric_config in metrics:
        metric_definitions.append(MetricDefinition(
            name=metric_config["name"],
            display_name=metric_config.get("display_name", metric_config["name"]),
            field=metric_config["field"],
            aggregation=AggregationType(metric_config["aggregation"]),
            format=MetricFormat(metric_config.get("format", "decimal")),
            conditions=metric_config.get("conditions", {})
        ))
    
    # Convert dimension configurations
    dimension_definitions = []
    if dimensions:
        for dim_config in dimensions:
            dimension_definitions.append(DimensionDefinition(
                name=dim_config["name"],
                display_name=dim_config.get("display_name", dim_config["name"]),
                field=dim_config["field"],
                dimension_type=DimensionType(dim_config["type"])
            ))
    
    # Create report definition
    definition = ReportDefinition(
        name=name,
        description=f"Custom report for {entity_type}",
        report_type=ReportType.CUSTOM,
        entity_type=entity_type,
        metrics=metric_definitions,
        dimensions=dimension_definitions,
        base_filters=filters or {},
        created_by="user"
    )
    
    return self.create_report_definition(definition)

# Example: Create custom loan performance report
custom_report_id = report_engine.create_custom_report(
    name="Loan Performance by Origination Year",
    entity_type="loan",
    metrics=[
        {
            "name": "total_originated",
            "display_name": "Total Originated",
            "field": "original_balance",
            "aggregation": "sum",
            "format": "money"
        },
        {
            "name": "current_outstanding",
            "display_name": "Current Outstanding",
            "field": "current_balance", 
            "aggregation": "sum",
            "format": "money"
        },
        {
            "name": "default_count",
            "display_name": "Defaulted Loans",
            "field": "id",
            "aggregation": "count",
            "conditions": {"status": "defaulted"}
        }
    ],
    dimensions=[
        {
            "name": "origination_year",
            "display_name": "Origination Year",
            "field": "originated_at",
            "type": "date"
        },
        {
            "name": "product_type",
            "display_name": "Product Type",
            "field": "product_type",
            "type": "product"
        }
    ],
    filters={
        "originated_after": "2020-01-01",
        "original_balance_greater_than": 1000.00
    }
)
```

## Report Scheduling and Distribution

### Automated Report Generation

```python
from core_banking.reporting import ReportSchedule, ScheduleFrequency

@dataclass
class ReportSchedule(StorageRecord):
    report_definition_id: str
    name: str
    description: str
    
    # Schedule configuration
    frequency: ScheduleFrequency  # daily, weekly, monthly, quarterly
    day_of_week: Optional[int] = None  # 0=Monday for weekly
    day_of_month: Optional[int] = None  # 1-28 for monthly
    hour: int = 9  # Hour of day (0-23)
    
    # Output configuration
    output_format: ReportFormat = ReportFormat.CSV
    email_recipients: List[str] = field(default_factory=list)
    file_path: Optional[str] = None  # For file system output
    
    # Status
    is_active: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None

class ReportScheduler:
    """Manage scheduled report generation"""
    
    def schedule_report(
        self,
        report_definition_id: str,
        frequency: ScheduleFrequency,
        recipients: List[str],
        name: str = None
    ) -> str:
        """Schedule regular report generation"""
        
        schedule = ReportSchedule(
            report_definition_id=report_definition_id,
            name=name or f"Scheduled Report {report_definition_id}",
            description="Automatically generated report",
            frequency=frequency,
            email_recipients=recipients,
            next_run=self._calculate_next_run_time(frequency)
        )
        
        self.storage.store(schedule)
        
        return schedule.id
    
    def run_scheduled_reports(self) -> List[str]:
        """Execute all due scheduled reports"""
        
        now = datetime.now(timezone.utc)
        due_schedules = self.get_due_schedules(now)
        
        executed_reports = []
        
        for schedule in due_schedules:
            try:
                # Generate report
                result = self.report_engine.generate_report(
                    schedule.report_definition_id,
                    format=schedule.output_format
                )
                
                # Distribute report
                if schedule.email_recipients:
                    self._email_report(result, schedule.email_recipients)
                
                if schedule.file_path:
                    self._save_report_to_file(result, schedule.file_path)
                
                # Update schedule
                schedule.last_run = now
                schedule.next_run = self._calculate_next_run_time(
                    schedule.frequency, 
                    from_date=now
                )
                
                self.storage.update(schedule.id, schedule)
                executed_reports.append(schedule.id)
                
            except Exception as e:
                # Log error and continue with other reports
                self.logger.error(f"Failed to execute scheduled report {schedule.id}: {e}")
        
        return executed_reports

# Example: Schedule monthly portfolio report
scheduler.schedule_report(
    report_definition_id="portfolio_summary",
    frequency=ScheduleFrequency.MONTHLY,
    recipients=["cfo@nexumbank.com", "risk@nexumbank.com"],
    name="Monthly Portfolio Summary"
)
```

## Export and Integration

### Multiple Export Formats

```python
class ReportExporter:
    """Handle report export in various formats"""
    
    def export_to_csv(self, result: ReportResult) -> str:
        """Export report data as CSV"""
        return result.to_csv()
    
    def export_to_excel(self, result: ReportResult) -> bytes:
        """Export report data as Excel file"""
        import pandas as pd
        
        # Create Excel writer
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Main data sheet
            df_data = pd.DataFrame(result.data)
            df_data.to_excel(writer, sheet_name='Data', index=False)
            
            # Summary sheet
            df_summary = pd.DataFrame([result.summary])
            df_summary.to_excel(writer, sheet_name='Summary', index=False)
            
            # Metadata sheet
            df_metadata = pd.DataFrame([result.metadata])
            df_metadata.to_excel(writer, sheet_name='Metadata', index=False)
        
        output.seek(0)
        return output.getvalue()
    
    def export_to_pdf(self, result: ReportResult) -> bytes:
        """Export report as formatted PDF"""
        # Implementation would use libraries like reportlab or weasyprint
        # to create formatted PDF reports with charts and tables
        pass
    
    def export_for_regulatory_filing(
        self,
        result: ReportResult,
        filing_format: str
    ) -> str:
        """Export in specific regulatory format (XBRL, etc.)"""
        
        if filing_format == "call_report":
            return self._format_for_call_report(result)
        elif filing_format == "ctr":
            return self._format_for_ctr(result)
        else:
            raise ValueError(f"Unsupported regulatory format: {filing_format}")
```

## Testing Report Generation

```python
def test_portfolio_summary_report():
    """Test portfolio summary report generation"""
    
    # Create test data
    create_test_accounts_and_loans()
    
    # Generate report
    summary = report_engine.generate_portfolio_summary(
        as_of_date=date.today(),
        currency=Currency.USD
    )
    
    assert "loans" in summary
    assert "deposits" in summary
    assert "loan_to_deposit_ratio" in summary
    
    assert summary["loans"]["count"] > 0
    assert summary["loans"]["total_outstanding"] > 0

def test_custom_report_creation():
    """Test dynamic custom report creation"""
    
    # Create custom report definition
    report_id = report_engine.create_custom_report(
        name="Test Custom Report",
        entity_type="account",
        metrics=[
            {
                "name": "total_balance",
                "field": "balance",
                "aggregation": "sum",
                "format": "money"
            },
            {
                "name": "account_count",
                "field": "id",
                "aggregation": "count"
            }
        ],
        dimensions=[
            {
                "name": "product_type",
                "field": "product_type",
                "type": "product"
            }
        ]
    )
    
    # Generate the report
    result = report_engine.generate_report(report_id)
    
    assert result.row_count > 0
    assert len(result.data) > 0
    assert "total_balance" in result.data[0]
    assert "account_count" in result.data[0]

def test_delinquency_report():
    """Test delinquency analysis report"""
    
    # Create test loans with various delinquency states
    create_delinquent_test_loans()
    
    # Generate delinquency report
    delinq_report = report_engine.generate_delinquency_report(
        as_of_date=date.today()
    )
    
    assert "delinquency_buckets" in delinq_report
    assert "current" in delinq_report["delinquency_buckets"]
    assert "1-30" in delinq_report["delinquency_buckets"]
    
    total_accounts = sum(
        bucket["account_count"] 
        for bucket in delinq_report["delinquency_buckets"].values()
    )
    
    assert total_accounts == delinq_report["total_accounts"]

def test_report_export_formats():
    """Test various export formats"""
    
    # Generate test report
    result = generate_test_report()
    
    # Test CSV export
    csv_data = result.to_csv()
    assert len(csv_data) > 0
    assert "," in csv_data  # Has CSV delimiters
    
    # Test JSON export
    json_data = result.to_json()
    parsed = json.loads(json_data)
    assert "data" in parsed
    assert "summary" in parsed
```

The reporting module provides a powerful and flexible reporting engine that supports both predefined and custom reports, multiple export formats, automated scheduling, and comprehensive portfolio analytics for business intelligence and regulatory compliance.