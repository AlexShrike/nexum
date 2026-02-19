# Compliance Module

The compliance module provides comprehensive KYC (Know Your Customer) and AML (Anti-Money Laundering) capabilities to ensure regulatory compliance across all customer interactions and transactions. It implements sophisticated risk assessment, monitoring, and reporting tools required for modern banking operations.

## Overview

The compliance system handles:

- **KYC Management**: Customer identification and verification processes
- **AML Monitoring**: Real-time transaction monitoring for suspicious activity
- **Risk Assessment**: Customer and transaction risk scoring
- **Regulatory Reporting**: Automated generation of required compliance reports
- **Alert Management**: Investigation and resolution of compliance alerts

## Key Concepts

### KYC Tiers
Customers are classified into risk-based tiers that determine verification requirements and transaction limits:

- **Tier 0**: Unverified customers with minimal functionality
- **Tier 1**: Basic verification with limited transaction capabilities
- **Tier 2**: Enhanced verification with standard transaction limits
- **Tier 3**: Full verification with highest transaction limits

### AML Monitoring
Real-time monitoring of transactions against configurable rules to detect:
- Unusual transaction patterns
- Structuring (multiple transactions below reporting thresholds)
- High-risk geographic locations
- Suspicious velocity or amounts
- Watch list matches

### Risk Scoring
Customers and transactions are scored based on various risk factors to prioritize compliance resources and determine appropriate controls.

## Core Classes

### ComplianceEngine

Main interface for compliance operations:

```python
from core_banking.compliance import ComplianceEngine, KYCTier, RiskLevel
from core_banking.customers import Customer
from core_banking.transactions import Transaction

class ComplianceEngine:
    def __init__(self, storage: StorageInterface):
        self.storage = storage
        self.kyc_validator = KYCValidator()
        self.aml_monitor = AMLMonitor()
        self.risk_scorer = RiskScorer()
    
    def validate_kyc_requirements(
        self,
        customer: Customer,
        requested_tier: KYCTier
    ) -> KYCValidationResult:
        """Validate KYC requirements for tier upgrade"""
        
        required_documents = self.get_required_documents(requested_tier)
        provided_documents = customer.kyc_documents or []
        
        missing_documents = []
        for doc_type in required_documents:
            if not any(doc.document_type == doc_type for doc in provided_documents):
                missing_documents.append(doc_type)
        
        # Additional validations
        validation_issues = []
        
        if requested_tier >= KYCTier.TIER_2:
            # Enhanced due diligence requirements
            if not customer.address:
                validation_issues.append("Address verification required")
            
            if not customer.date_of_birth:
                validation_issues.append("Date of birth required")
            
            # Check against watch lists
            watch_list_matches = self.check_watch_lists(customer)
            if watch_list_matches:
                validation_issues.extend([f"Watch list match: {match}" for match in watch_list_matches])
        
        return KYCValidationResult(
            approved=len(missing_documents) == 0 and len(validation_issues) == 0,
            missing_documents=missing_documents,
            validation_issues=validation_issues,
            risk_score=self.risk_scorer.score_customer(customer)
        )
```

### KYCDocument

Represents identity verification documents:

```python
from core_banking.compliance import KYCDocument, DocumentType, DocumentStatus

@dataclass
class KYCDocument(StorageRecord):
    customer_id: str
    document_type: DocumentType
    document_number: str
    issued_date: Optional[date] = None
    expiry_date: Optional[date] = None
    issuing_authority: Optional[str] = None
    
    # Verification status
    status: DocumentStatus = DocumentStatus.PENDING
    verified_date: Optional[date] = None
    verified_by: Optional[str] = None
    
    # Document metadata
    file_path: Optional[str] = None
    notes: str = ""
    
    @property
    def is_expired(self) -> bool:
        """Check if document is expired"""
        if not self.expiry_date:
            return False
        return date.today() > self.expiry_date
    
    @property
    def days_until_expiry(self) -> Optional[int]:
        """Get days until document expires"""
        if not self.expiry_date:
            return None
        return (self.expiry_date - date.today()).days

# Example KYC documents
drivers_license = KYCDocument(
    customer_id="cust_123",
    document_type=DocumentType.DRIVERS_LICENSE,
    document_number="DL123456789",
    issued_date=date(2020, 3, 15),
    expiry_date=date(2025, 3, 15),
    issuing_authority="CA DMV",
    status=DocumentStatus.VERIFIED,
    verified_date=date(2026, 1, 10)
)
```

### AMLAlert

Represents suspicious activity alerts:

```python
from core_banking.compliance import AMLAlert, AlertType, AlertStatus

@dataclass
class AMLAlert(StorageRecord):
    customer_id: str
    transaction_id: Optional[str] = None
    
    # Alert details
    alert_type: AlertType
    severity: RiskLevel
    description: str
    
    # Alert data
    triggered_amount: Optional[Money] = None
    triggered_rule: str
    alert_parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Investigation status
    status: AlertStatus = AlertStatus.OPEN
    assigned_analyst: Optional[str] = None
    investigation_notes: str = ""
    
    # Resolution
    resolved_date: Optional[date] = None
    resolution: Optional[str] = None
    sar_filed: bool = False  # Suspicious Activity Report filed
    
    def __post_init__(self):
        self.created_at = datetime.now(timezone.utc)

# Example AML alert
structuring_alert = AMLAlert(
    customer_id="cust_456",
    alert_type=AlertType.STRUCTURING,
    severity=RiskLevel.HIGH,
    description="Multiple cash deposits just below $10,000 threshold",
    triggered_rule="STRUCT_001",
    alert_parameters={
        "total_amount": "28500.00",
        "transaction_count": 4,
        "time_period": "7 days",
        "deposit_amounts": ["9800.00", "9500.00", "4700.00", "4500.00"]
    }
)
```

## KYC Management

### Tier-Based Requirements

```python
class KYCTierRequirements:
    """KYC requirements for each tier level"""
    
    TIER_REQUIREMENTS = {
        KYCTier.TIER_0: {
            "documents": [],
            "max_transaction_amount": Money(Decimal("300.00"), Currency.USD),
            "max_daily_limit": Money(Decimal("1000.00"), Currency.USD),
            "max_monthly_limit": Money(Decimal("2500.00"), Currency.USD)
        },
        KYCTier.TIER_1: {
            "documents": [DocumentType.GOVERNMENT_ID],
            "max_transaction_amount": Money(Decimal("2500.00"), Currency.USD),
            "max_daily_limit": Money(Decimal("5000.00"), Currency.USD),
            "max_monthly_limit": Money(Decimal("25000.00"), Currency.USD),
            "additional_requirements": ["phone_verification"]
        },
        KYCTier.TIER_2: {
            "documents": [
                DocumentType.GOVERNMENT_ID,
                DocumentType.PROOF_OF_ADDRESS
            ],
            "max_transaction_amount": Money(Decimal("25000.00"), Currency.USD),
            "max_daily_limit": Money(Decimal("50000.00"), Currency.USD),
            "max_monthly_limit": Money(Decimal("250000.00"), Currency.USD),
            "additional_requirements": ["address_verification", "background_check"]
        },
        KYCTier.TIER_3: {
            "documents": [
                DocumentType.GOVERNMENT_ID,
                DocumentType.PROOF_OF_ADDRESS,
                DocumentType.PROOF_OF_INCOME
            ],
            "max_transaction_amount": None,  # No limit
            "max_daily_limit": None,
            "max_monthly_limit": None,
            "additional_requirements": [
                "enhanced_due_diligence",
                "source_of_funds_verification",
                "ongoing_monitoring"
            ]
        }
    }

def upgrade_kyc_tier(
    customer_id: str,
    requested_tier: KYCTier,
    documents: List[KYCDocument]
) -> KYCUpgradeResult:
    """Upgrade customer KYC tier"""
    
    customer = self.customer_manager.get_customer(customer_id)
    
    # Validate requirements
    validation = self.validate_kyc_requirements(customer, requested_tier)
    
    if not validation.approved:
        return KYCUpgradeResult(
            success=False,
            issues=validation.validation_issues,
            missing_documents=validation.missing_documents
        )
    
    # Enhanced due diligence for high-risk customers
    if validation.risk_score >= RiskLevel.HIGH:
        edd_result = self.perform_enhanced_due_diligence(customer)
        if not edd_result.approved:
            return KYCUpgradeResult(
                success=False,
                issues=["Enhanced due diligence required"]
            )
    
    # Update customer KYC status
    customer.kyc_tier = requested_tier
    customer.kyc_status = KYCStatus.VERIFIED
    customer.kyc_verified_date = date.today()
    
    # Store documents
    for document in documents:
        document.customer_id = customer_id
        self.storage.store(document)
    
    self.customer_manager.update_customer(customer_id, customer)
    
    # Log KYC upgrade
    self.audit.log_event(
        AuditEventType.KYC_TIER_UPGRADED,
        entity_id=customer_id,
        details={
            "old_tier": customer.kyc_tier.value,
            "new_tier": requested_tier.value,
            "risk_score": validation.risk_score.value
        }
    )
    
    return KYCUpgradeResult(success=True, new_tier=requested_tier)
```

### Document Verification

```python
def verify_document(document_id: str, analyst_id: str) -> DocumentVerificationResult:
    """Verify KYC document"""
    
    document = self.get_document(document_id)
    
    # Perform document checks
    verification_checks = []
    
    # Check document validity
    if document.is_expired:
        verification_checks.append("Document is expired")
    
    # Verify document format (simplified)
    format_check = self.verify_document_format(document)
    if not format_check.valid:
        verification_checks.append(f"Invalid format: {format_check.reason}")
    
    # Cross-reference with external databases
    if document.document_type == DocumentType.DRIVERS_LICENSE:
        dmv_check = self.verify_with_dmv(document.document_number, document.issuing_authority)
        if not dmv_check.valid:
            verification_checks.append("Could not verify with DMV")
    
    elif document.document_type == DocumentType.PASSPORT:
        passport_check = self.verify_passport(document.document_number)
        if not passport_check.valid:
            verification_checks.append("Could not verify passport")
    
    # Update document status
    if len(verification_checks) == 0:
        document.status = DocumentStatus.VERIFIED
        document.verified_date = date.today()
        document.verified_by = analyst_id
    else:
        document.status = DocumentStatus.REJECTED
        document.notes = "; ".join(verification_checks)
    
    self.storage.update(document_id, document)
    
    return DocumentVerificationResult(
        verified=document.status == DocumentStatus.VERIFIED,
        issues=verification_checks
    )
```

## AML Monitoring

### Transaction Monitoring Rules

```python
class AMLMonitoringRules:
    """AML monitoring rule definitions"""
    
    def __init__(self):
        self.rules = [
            # Cash transaction reporting
            AMLRule(
                name="CTR_CASH_OVER_10K",
                description="Cash transactions over $10,000 (CTR filing required)",
                threshold=Money(Decimal("10000.00"), Currency.USD),
                trigger_condition="single_transaction",
                severity=RiskLevel.HIGH
            ),
            
            # Structuring detection
            AMLRule(
                name="STRUCT_MULTIPLE_UNDER_10K",
                description="Multiple transactions under $10K in short timeframe",
                threshold=Money(Decimal("10000.00"), Currency.USD),
                trigger_condition="aggregated_daily",
                lookback_days=7,
                severity=RiskLevel.HIGH
            ),
            
            # Unusual velocity
            AMLRule(
                name="VELOCITY_UNUSUAL_ACTIVITY",
                description="Unusual transaction velocity for customer",
                trigger_condition="velocity_change",
                velocity_multiplier=3.0,  # 3x normal activity
                severity=RiskLevel.MEDIUM
            ),
            
            # Geographic risk
            AMLRule(
                name="HIGH_RISK_GEOGRAPHY",
                description="Transactions involving high-risk countries",
                trigger_condition="geographic_risk",
                high_risk_countries=["Country1", "Country2"],
                severity=RiskLevel.HIGH
            )
        ]

def monitor_transaction(transaction: Transaction) -> List[AMLAlert]:
    """Monitor transaction against AML rules"""
    
    alerts = []
    customer = self.customer_manager.get_customer(transaction.customer_id)
    
    for rule in self.rules:
        if self.rule_applies_to_transaction(rule, transaction, customer):
            alert = self.evaluate_rule(rule, transaction, customer)
            if alert:
                alerts.append(alert)
    
    return alerts

def evaluate_rule(
    rule: AMLRule, 
    transaction: Transaction, 
    customer: Customer
) -> Optional[AMLAlert]:
    """Evaluate specific AML rule against transaction"""
    
    if rule.name == "CTR_CASH_OVER_10K":
        if (transaction.transaction_type == TransactionType.CASH_DEPOSIT and
            transaction.amount >= rule.threshold):
            
            return AMLAlert(
                customer_id=customer.id,
                transaction_id=transaction.id,
                alert_type=AlertType.CTR_REQUIRED,
                severity=rule.severity,
                description=f"Cash deposit of {transaction.amount} requires CTR filing",
                triggered_rule=rule.name,
                triggered_amount=transaction.amount
            )
    
    elif rule.name == "STRUCT_MULTIPLE_UNDER_10K":
        # Check for multiple transactions under $10K in lookback period
        recent_transactions = self.get_recent_cash_transactions(
            customer.id, 
            days=rule.lookback_days
        )
        
        total_amount = sum(t.amount for t in recent_transactions)
        
        if (len(recent_transactions) >= 3 and 
            total_amount >= rule.threshold and
            all(t.amount < rule.threshold for t in recent_transactions)):
            
            return AMLAlert(
                customer_id=customer.id,
                transaction_id=transaction.id,
                alert_type=AlertType.STRUCTURING,
                severity=rule.severity,
                description=f"Potential structuring: {len(recent_transactions)} transactions totaling {total_amount}",
                triggered_rule=rule.name,
                alert_parameters={
                    "transaction_count": len(recent_transactions),
                    "total_amount": str(total_amount.amount),
                    "lookback_days": rule.lookback_days
                }
            )
    
    elif rule.name == "VELOCITY_UNUSUAL_ACTIVITY":
        # Compare current activity to historical baseline
        historical_velocity = self.calculate_historical_velocity(customer.id)
        current_velocity = self.calculate_current_velocity(customer.id, days=30)
        
        if current_velocity > historical_velocity * rule.velocity_multiplier:
            return AMLAlert(
                customer_id=customer.id,
                transaction_id=transaction.id,
                alert_type=AlertType.UNUSUAL_ACTIVITY,
                severity=rule.severity,
                description=f"Transaction velocity {current_velocity:.2f}x above normal",
                triggered_rule=rule.name,
                alert_parameters={
                    "historical_velocity": historical_velocity,
                    "current_velocity": current_velocity,
                    "multiplier": rule.velocity_multiplier
                }
            )
    
    return None
```

### Watch List Screening

```python
class WatchListScreening:
    """Screen customers and transactions against watch lists"""
    
    def __init__(self):
        self.watch_lists = {
            "OFAC_SDN": self.load_ofac_sdn_list(),  # OFAC Specially Designated Nationals
            "PEP": self.load_pep_list(),           # Politically Exposed Persons
            "INTERNAL": self.load_internal_list()   # Internal watch list
        }
    
    def screen_customer(self, customer: Customer) -> List[WatchListMatch]:
        """Screen customer against all watch lists"""
        
        matches = []
        
        # Create search terms from customer data
        search_terms = self.create_search_terms(customer)
        
        for list_name, watch_list in self.watch_lists.items():
            list_matches = self.search_watch_list(search_terms, watch_list)
            
            for match in list_matches:
                matches.append(WatchListMatch(
                    list_name=list_name,
                    matched_name=match.name,
                    customer_name=f"{customer.first_name} {customer.last_name}",
                    match_score=match.score,
                    match_reason=match.reason
                ))
        
        return matches
    
    def create_search_terms(self, customer: Customer) -> List[str]:
        """Create search terms from customer data"""
        
        terms = []
        
        # Full name
        full_name = f"{customer.first_name} {customer.last_name}"
        terms.append(full_name)
        
        # Name variations
        terms.append(f"{customer.last_name}, {customer.first_name}")
        terms.append(f"{customer.first_name[0]} {customer.last_name}")
        
        # Add aliases if available
        if hasattr(customer, 'aliases') and customer.aliases:
            terms.extend(customer.aliases)
        
        return terms
    
    def fuzzy_match_name(self, name1: str, name2: str) -> float:
        """Calculate fuzzy match score between names"""
        from difflib import SequenceMatcher
        
        # Normalize names
        name1_norm = name1.lower().strip()
        name2_norm = name2.lower().strip()
        
        # Calculate similarity
        similarity = SequenceMatcher(None, name1_norm, name2_norm).ratio()
        
        return similarity
```

## Risk Assessment

### Customer Risk Scoring

```python
class RiskScorer:
    """Calculate risk scores for customers and transactions"""
    
    def score_customer(self, customer: Customer) -> RiskScore:
        """Calculate comprehensive customer risk score"""
        
        risk_factors = []
        total_score = 0
        
        # Geographic risk
        if customer.address:
            geo_risk = self.assess_geographic_risk(customer.address.country)
            risk_factors.append(f"Geographic risk: {geo_risk.level}")
            total_score += geo_risk.score
        
        # Industry risk (if business customer)
        if hasattr(customer, 'business_info') and customer.business_info:
            industry_risk = self.assess_industry_risk(customer.business_info.industry)
            risk_factors.append(f"Industry risk: {industry_risk.level}")
            total_score += industry_risk.score
        
        # Account activity risk
        activity_risk = self.assess_activity_risk(customer.id)
        risk_factors.append(f"Activity risk: {activity_risk.level}")
        total_score += activity_risk.score
        
        # KYC completeness
        kyc_risk = self.assess_kyc_completeness(customer)
        risk_factors.append(f"KYC risk: {kyc_risk.level}")
        total_score += kyc_risk.score
        
        # Watch list matches
        watch_list_matches = self.watch_list_screening.screen_customer(customer)
        if watch_list_matches:
            watch_list_risk = len(watch_list_matches) * 25  # 25 points per match
            risk_factors.append(f"Watch list matches: {len(watch_list_matches)}")
            total_score += watch_list_risk
        
        # Determine risk level
        if total_score >= 75:
            risk_level = RiskLevel.HIGH
        elif total_score >= 50:
            risk_level = RiskLevel.MEDIUM
        elif total_score >= 25:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.MINIMAL
        
        return RiskScore(
            score=total_score,
            level=risk_level,
            factors=risk_factors
        )
    
    def score_transaction(self, transaction: Transaction) -> RiskScore:
        """Calculate transaction-specific risk score"""
        
        risk_factors = []
        total_score = 0
        
        # Amount-based risk
        if transaction.amount >= Money(Decimal("10000.00"), transaction.amount.currency):
            risk_factors.append("High value transaction")
            total_score += 30
        elif transaction.amount >= Money(Decimal("5000.00"), transaction.amount.currency):
            risk_factors.append("Medium value transaction")
            total_score += 15
        
        # Time-based risk (unusual hours)
        transaction_hour = transaction.created_at.hour
        if transaction_hour < 6 or transaction_hour > 22:
            risk_factors.append("Off-hours transaction")
            total_score += 10
        
        # Channel risk
        if transaction.channel == TransactionChannel.ATM:
            # ATM transactions in high-risk locations
            if hasattr(transaction, 'atm_location'):
                location_risk = self.assess_location_risk(transaction.atm_location)
                if location_risk.level >= RiskLevel.MEDIUM:
                    risk_factors.append("High-risk ATM location")
                    total_score += 20
        
        # Customer velocity risk
        recent_transactions = self.get_recent_transactions(transaction.customer_id, days=1)
        if len(recent_transactions) > 10:
            risk_factors.append("High transaction velocity")
            total_score += 25
        
        # Determine risk level
        if total_score >= 60:
            risk_level = RiskLevel.HIGH
        elif total_score >= 35:
            risk_level = RiskLevel.MEDIUM
        elif total_score >= 15:
            risk_level = RiskLevel.LOW
        else:
            risk_level = RiskLevel.MINIMAL
        
        return RiskScore(
            score=total_score,
            level=risk_level,
            factors=risk_factors
        )
```

## Alert Investigation

### Alert Management Workflow

```python
class AlertInvestigationWorkflow:
    """Manage AML alert investigation workflow"""
    
    def assign_alert(self, alert_id: str, analyst_id: str) -> None:
        """Assign alert to compliance analyst"""
        
        alert = self.get_alert(alert_id)
        alert.assigned_analyst = analyst_id
        alert.status = AlertStatus.ASSIGNED
        
        self.storage.update(alert_id, alert)
        
        # Create investigation record
        investigation = AlertInvestigation(
            alert_id=alert_id,
            analyst_id=analyst_id,
            started_date=date.today(),
            status=InvestigationStatus.IN_PROGRESS
        )
        
        self.storage.store(investigation)
    
    def investigate_alert(
        self,
        alert_id: str,
        investigation_notes: str,
        supporting_evidence: List[str] = None
    ) -> InvestigationResult:
        """Conduct alert investigation"""
        
        alert = self.get_alert(alert_id)
        customer = self.customer_manager.get_customer(alert.customer_id)
        
        investigation_steps = []
        
        # Review customer profile
        profile_review = self.review_customer_profile(customer)
        investigation_steps.append(f"Profile review: {profile_review.summary}")
        
        # Review transaction history
        if alert.transaction_id:
            transaction = self.transaction_processor.get_transaction(alert.transaction_id)
            history_review = self.review_transaction_history(customer.id, transaction)
            investigation_steps.append(f"Transaction history: {history_review.summary}")
        
        # Check for related alerts
        related_alerts = self.get_related_alerts(alert)
        if related_alerts:
            investigation_steps.append(f"Related alerts found: {len(related_alerts)}")
        
        # External database checks
        external_checks = self.perform_external_checks(customer)
        investigation_steps.extend(external_checks)
        
        # Update investigation
        investigation = self.get_investigation_by_alert(alert_id)
        investigation.investigation_notes = investigation_notes
        investigation.investigation_steps = investigation_steps
        investigation.supporting_evidence = supporting_evidence or []
        
        return InvestigationResult(
            alert_id=alert_id,
            investigation_summary=investigation_notes,
            steps_completed=investigation_steps,
            recommendation=self.generate_recommendation(alert, investigation_steps)
        )
    
    def close_alert(
        self,
        alert_id: str,
        resolution: str,
        file_sar: bool = False
    ) -> None:
        """Close alert with resolution"""
        
        alert = self.get_alert(alert_id)
        
        alert.status = AlertStatus.CLOSED
        alert.resolved_date = date.today()
        alert.resolution = resolution
        alert.sar_filed = file_sar
        
        if file_sar:
            # File Suspicious Activity Report
            sar = self.generate_sar(alert)
            self.file_sar(sar)
        
        self.storage.update(alert_id, alert)
        
        # Update investigation record
        investigation = self.get_investigation_by_alert(alert_id)
        investigation.status = InvestigationStatus.COMPLETED
        investigation.completed_date = date.today()
        investigation.final_resolution = resolution
        
        self.storage.update(investigation.id, investigation)
```

## Regulatory Reporting

### Currency Transaction Report (CTR)

```python
def generate_ctr(transaction: Transaction) -> CTRReport:
    """Generate Currency Transaction Report for transactions over $10,000"""
    
    if transaction.amount < Money(Decimal("10000.00"), Currency.USD):
        raise ValueError("CTR only required for transactions $10,000 and above")
    
    customer = self.customer_manager.get_customer(transaction.customer_id)
    
    ctr = CTRReport(
        report_date=date.today(),
        transaction_date=transaction.created_at.date(),
        
        # Financial institution information
        institution_name="Nexum Bank",
        institution_address=self.get_institution_address(),
        institution_routing_number="123456789",
        
        # Customer information
        customer_name=f"{customer.first_name} {customer.last_name}",
        customer_address=customer.address,
        customer_ssn=customer.ssn,
        customer_id_type="Driver's License",
        customer_id_number=self.get_customer_id_document(customer.id),
        
        # Transaction details
        transaction_type=transaction.transaction_type.value,
        transaction_amount=transaction.amount,
        account_number=transaction.account_id,
        
        # Additional information
        multiple_transactions=self.check_multiple_transactions(customer.id, transaction.created_at.date()),
        suspicious_activity=False  # Would be determined by investigation
    )
    
    return ctr

def file_ctr(ctr: CTRReport) -> None:
    """File CTR with FinCEN"""
    
    # Generate CTR in required XML format
    xml_data = self.format_ctr_xml(ctr)
    
    # Submit to FinCEN (mock implementation)
    response = self.fincen_api.submit_ctr(xml_data)
    
    if response.success:
        ctr.filing_status = "FILED"
        ctr.bsa_id = response.bsa_id
        ctr.filed_date = date.today()
    else:
        ctr.filing_status = "FAILED"
        ctr.error_message = response.error_message
    
    self.storage.store(ctr)
```

### Suspicious Activity Report (SAR)

```python
def generate_sar(alert: AMLAlert) -> SARReport:
    """Generate Suspicious Activity Report"""
    
    customer = self.customer_manager.get_customer(alert.customer_id)
    investigation = self.get_investigation_by_alert(alert.id)
    
    sar = SARReport(
        report_date=date.today(),
        
        # Subject information
        subject_name=f"{customer.first_name} {customer.last_name}",
        subject_address=customer.address,
        subject_ssn=customer.ssn,
        subject_phone=customer.phone,
        
        # Suspicious activity details
        activity_type=self.map_alert_to_sar_type(alert.alert_type),
        activity_date_range=self.calculate_activity_period(alert),
        total_dollar_amount=alert.triggered_amount or self.calculate_total_suspicious_amount(alert),
        
        # Narrative
        suspicious_activity_description=self.generate_sar_narrative(alert, investigation),
        
        # Law enforcement information
        law_enforcement_notified=False,
        law_enforcement_agency=None,
        
        # Filing institution
        institution_name="Nexum Bank",
        institution_contact=self.get_compliance_contact(),
        
        # Internal tracking
        internal_control_number=f"SAR_{alert.id}_{date.today().strftime('%Y%m%d')}"
    )
    
    return sar

def generate_sar_narrative(alert: AMLAlert, investigation: AlertInvestigation) -> str:
    """Generate detailed narrative for SAR filing"""
    
    narrative_parts = []
    
    # Alert summary
    narrative_parts.append(f"This SAR is being filed due to {alert.description}.")
    
    # Investigation findings
    if investigation.investigation_notes:
        narrative_parts.append(f"Investigation findings: {investigation.investigation_notes}")
    
    # Transaction details
    if alert.transaction_id:
        transaction = self.transaction_processor.get_transaction(alert.transaction_id)
        narrative_parts.append(
            f"The suspicious transaction occurred on {transaction.created_at.date()} "
            f"in the amount of {transaction.amount} via {transaction.channel.value}."
        )
    
    # Pattern analysis
    if alert.alert_type == AlertType.STRUCTURING:
        narrative_parts.append(
            "The transactions appear to be structured to avoid currency reporting requirements."
        )
    
    # Customer behavior
    customer_history = self.analyze_customer_history(alert.customer_id)
    if customer_history.unusual_patterns:
        narrative_parts.append(f"Customer behavior analysis: {customer_history.summary}")
    
    return " ".join(narrative_parts)
```

## Testing Compliance Operations

```python
def test_kyc_tier_upgrade():
    """Test KYC tier upgrade process"""
    
    customer = create_test_customer()
    
    # Provide required documents for Tier 2
    documents = [
        KYCDocument(
            document_type=DocumentType.DRIVERS_LICENSE,
            document_number="DL123456",
            status=DocumentStatus.VERIFIED
        ),
        KYCDocument(
            document_type=DocumentType.PROOF_OF_ADDRESS,
            document_number="UTILITY_BILL_123",
            status=DocumentStatus.VERIFIED
        )
    ]
    
    # Attempt upgrade
    result = compliance_engine.upgrade_kyc_tier(
        customer.id,
        KYCTier.TIER_2,
        documents
    )
    
    assert result.success
    assert result.new_tier == KYCTier.TIER_2
    
    # Verify customer updated
    updated_customer = customer_manager.get_customer(customer.id)
    assert updated_customer.kyc_tier == KYCTier.TIER_2

def test_aml_structuring_detection():
    """Test structuring detection algorithm"""
    
    customer = create_test_customer()
    
    # Create multiple cash deposits under $10K
    transactions = []
    for amount in ["9800.00", "9500.00", "4900.00"]:
        transaction = create_test_transaction(
            customer_id=customer.id,
            transaction_type=TransactionType.CASH_DEPOSIT,
            amount=Money(Decimal(amount), Currency.USD)
        )
        transactions.append(transaction)
    
    # Monitor transactions
    alerts = []
    for transaction in transactions:
        transaction_alerts = compliance_engine.monitor_transaction(transaction)
        alerts.extend(transaction_alerts)
    
    # Should trigger structuring alert
    structuring_alerts = [a for a in alerts if a.alert_type == AlertType.STRUCTURING]
    assert len(structuring_alerts) >= 1
    
    alert = structuring_alerts[0]
    assert alert.severity == RiskLevel.HIGH
    assert "24200.00" in alert.alert_parameters["total_amount"]  # Sum of deposits

def test_watch_list_screening():
    """Test customer screening against watch lists"""
    
    # Create customer with name similar to watch list entry
    customer = Customer(
        first_name="John",
        last_name="Doe",  # Assuming "John Doe" is on test watch list
        email="john.doe@example.com"
    )
    
    # Screen customer
    matches = compliance_engine.watch_list_screening.screen_customer(customer)
    
    # Should find potential match
    assert len(matches) > 0
    
    match = matches[0]
    assert match.match_score > 0.8  # High similarity
    assert "John Doe" in match.matched_name
```

The compliance module provides comprehensive KYC and AML capabilities that ensure regulatory compliance while maintaining efficient customer onboarding and transaction processing workflows.