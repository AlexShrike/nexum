"""
Compliance & Limits Module

Handles transaction limits per KYC tier, large transaction reporting,
account freezes, holds, and suspicious activity detection.
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
import uuid

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType
from .customers import Customer, CustomerManager, KYCTier


class ComplianceRuleType(Enum):
    """Types of compliance rules"""
    DAILY_LIMIT = "daily_limit"
    MONTHLY_LIMIT = "monthly_limit"
    SINGLE_TRANSACTION_LIMIT = "single_transaction_limit"
    LARGE_TRANSACTION_REPORTING = "large_transaction_reporting"
    VELOCITY_CHECK = "velocity_check"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    GEOGRAPHIC_RESTRICTION = "geographic_restriction"


class SuspiciousActivityType(Enum):
    """Types of suspicious activities"""
    UNUSUAL_TRANSACTION_SIZE = "unusual_transaction_size"
    HIGH_VELOCITY = "high_velocity"
    ROUND_DOLLAR_AMOUNTS = "round_dollar_amounts"
    RAPID_MOVEMENT = "rapid_movement"
    GEOGRAPHIC_ANOMALY = "geographic_anomaly"
    STRUCTURED_TRANSACTION = "structured_transaction"  # Just below reporting threshold
    DORMANT_ACCOUNT_ACTIVITY = "dormant_account_activity"


class ComplianceAction(Enum):
    """Actions taken for compliance violations"""
    ALLOW = "allow"              # Allow transaction
    BLOCK = "block"              # Block transaction
    REVIEW = "review"            # Hold for manual review
    REPORT = "report"            # Report to authorities
    FREEZE_ACCOUNT = "freeze_account"  # Freeze account


@dataclass
class ComplianceRule:
    """Compliance rule definition"""
    rule_type: ComplianceRuleType
    threshold: Money
    time_period_hours: Optional[int] = None  # For velocity checks
    kyc_tiers: Set[KYCTier] = field(default_factory=lambda: set(KYCTier))
    is_active: bool = True


@dataclass
class SuspiciousActivityAlert(StorageRecord):
    """Alert for suspicious activity"""
    customer_id: str
    activity_type: SuspiciousActivityType
    description: str
    risk_score: int  # 1-100, higher = more suspicious
    account_id: Optional[str] = None
    transaction_id: Optional[str] = None
    status: str = "open"  # open, investigating, resolved, false_positive
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None
    resolved_at: Optional[datetime] = None
    
    @property
    def is_high_risk(self) -> bool:
        """Check if this is a high-risk alert (score >= 80)"""
        return self.risk_score >= 80


@dataclass
class ComplianceViolation(StorageRecord):
    """Record of compliance rule violation"""
    customer_id: str
    account_id: str
    transaction_id: Optional[str]
    rule_type: ComplianceRuleType
    description: str
    amount: Money
    action_taken: ComplianceAction
    reviewer_id: Optional[str] = None
    review_notes: Optional[str] = None


@dataclass
class LargeTransactionReport(StorageRecord):
    """Report for large transactions requiring regulatory filing"""
    customer_id: str
    transaction_id: str
    amount: Money
    transaction_type: str
    reporting_threshold: Money
    filed_at: Optional[datetime] = None
    filing_reference: Optional[str] = None


class ComplianceEngine:
    """
    Compliance engine for transaction limits, monitoring, and suspicious activity detection
    """
    
    def __init__(
        self,
        storage: StorageInterface,
        customer_manager: CustomerManager,
        audit_trail: AuditTrail
    ):
        self.storage = storage
        self.customer_manager = customer_manager
        self.audit_trail = audit_trail
        self.violations_table = "compliance_violations"
        self.alerts_table = "suspicious_activity_alerts"
        self.reports_table = "large_transaction_reports"
        
        # Default compliance rules
        self._initialize_default_rules()
    
    def _initialize_default_rules(self):
        """Initialize default compliance rules"""
        self.rules = [
            # Large transaction reporting thresholds (varies by jurisdiction)
            ComplianceRule(
                rule_type=ComplianceRuleType.LARGE_TRANSACTION_REPORTING,
                threshold=Money(Decimal('10000'), Currency.USD)  # $10K for USD
            ),
            # Structured transaction detection (just below reporting threshold)
            ComplianceRule(
                rule_type=ComplianceRuleType.SUSPICIOUS_PATTERN,
                threshold=Money(Decimal('9500'), Currency.USD)  # Just below $10K
            )
        ]
    
    def check_transaction_compliance(
        self,
        customer_id: str,
        account_id: str,
        transaction_amount: Money,
        transaction_type: str,
        transaction_id: Optional[str] = None
    ) -> Tuple[ComplianceAction, List[str]]:
        """
        Check transaction against all compliance rules
        
        Args:
            customer_id: Customer performing transaction
            account_id: Account being transacted on
            transaction_amount: Amount of transaction
            transaction_type: Type of transaction (deposit, withdrawal, etc.)
            transaction_id: Optional transaction ID
            
        Returns:
            Tuple of (action, violations) where violations is list of violation descriptions
        """
        violations = []
        max_action = ComplianceAction.ALLOW
        
        customer = self.customer_manager.get_customer(customer_id)
        if not customer:
            violations.append("Customer not found")
            return ComplianceAction.BLOCK, violations
        
        if not customer.is_active:
            violations.append("Customer account is inactive")
            return ComplianceAction.BLOCK, violations
        
        # Check KYC limits
        kyc_violations = self._check_kyc_limits(customer, account_id, transaction_amount)
        if kyc_violations:
            violations.extend(kyc_violations)
            max_action = ComplianceAction.BLOCK
        
        # Check large transaction reporting
        if self._requires_large_transaction_report(transaction_amount):
            self._create_large_transaction_report(
                customer_id, transaction_id or "pending", transaction_amount, transaction_type
            )
            violations.append(f"Large transaction report required for {transaction_amount.to_string()}")
        
        # Check for suspicious patterns
        suspicious_alerts = self._check_suspicious_patterns(
            customer_id, account_id, transaction_amount, transaction_type
        )
        
        if suspicious_alerts:
            for alert in suspicious_alerts:
                violations.append(f"Suspicious activity detected: {alert.description}")
                if alert.is_high_risk:
                    max_action = max(max_action, ComplianceAction.REVIEW, key=lambda x: x.value)
        
        # Check velocity (rapid transactions)
        velocity_violation = self._check_velocity(customer_id, account_id, transaction_amount)
        if velocity_violation:
            violations.append(velocity_violation)
            max_action = max(max_action, ComplianceAction.REVIEW, key=lambda x: x.value)
        
        # Record violation if any found
        if violations:
            self._record_violation(
                customer_id=customer_id,
                account_id=account_id,
                transaction_id=transaction_id,
                rule_type=ComplianceRuleType.DAILY_LIMIT,  # Simplified
                description="; ".join(violations),
                amount=transaction_amount,
                action_taken=max_action
            )
        
        return max_action, violations
    
    def _check_kyc_limits(self, customer: Customer, account_id: str, amount: Money) -> List[str]:
        """Check transaction against KYC tier limits"""
        violations = []
        
        # Get KYC limits for customer
        kyc_limits = self.customer_manager.get_kyc_limits(customer.id, amount.currency)
        
        # Check single transaction limit
        if amount > kyc_limits.single_transaction_limit:
            violations.append(
                f"Transaction amount {amount.to_string()} exceeds single transaction limit "
                f"{kyc_limits.single_transaction_limit.to_string()} for {customer.kyc_tier.value}"
            )
        
        # Check daily limits
        daily_total = self._get_daily_transaction_total(customer.id, amount.currency)
        if daily_total + amount > kyc_limits.daily_transaction_limit:
            violations.append(
                f"Transaction would exceed daily limit {kyc_limits.daily_transaction_limit.to_string()} "
                f"(current: {daily_total.to_string()}, proposed: {amount.to_string()})"
            )
        
        # Check monthly limits
        monthly_total = self._get_monthly_transaction_total(customer.id, amount.currency)
        if monthly_total + amount > kyc_limits.monthly_transaction_limit:
            violations.append(
                f"Transaction would exceed monthly limit {kyc_limits.monthly_transaction_limit.to_string()} "
                f"(current: {monthly_total.to_string()}, proposed: {amount.to_string()})"
            )
        
        return violations
    
    def _requires_large_transaction_report(self, amount: Money) -> bool:
        """Check if transaction requires large transaction reporting"""
        for rule in self.rules:
            if (rule.rule_type == ComplianceRuleType.LARGE_TRANSACTION_REPORTING and
                rule.is_active and
                rule.threshold.currency == amount.currency and
                amount >= rule.threshold):
                return True
        return False
    
    def _check_suspicious_patterns(
        self,
        customer_id: str,
        account_id: str,
        amount: Money,
        transaction_type: str
    ) -> List[SuspiciousActivityAlert]:
        """Check for suspicious activity patterns"""
        alerts = []
        
        # Check for round dollar amounts (potential structuring)
        # Flag significant round amounts for all customers
        customer = self.customer_manager.get_customer(customer_id)
        if self._is_round_amount(amount) and customer and amount.amount >= Decimal('5000'):
            # Risk score varies by tier - but kept moderate to avoid blocking transactions
            if customer.kyc_tier == KYCTier.TIER_0:
                risk_score = 60  # Higher risk for unverified customers
            elif customer.kyc_tier == KYCTier.TIER_1:
                risk_score = 40  # Medium risk for basic KYC
            else:  # TIER_2, TIER_3
                risk_score = 30  # Lower risk for fully verified customers, but still flagged
                
            alert = self._create_suspicious_activity_alert(
                customer_id=customer_id,
                account_id=account_id,
                activity_type=SuspiciousActivityType.ROUND_DOLLAR_AMOUNTS,
                description=f"Round dollar amount: {amount.to_string()}",
                risk_score=risk_score
            )
            alerts.append(alert)
        
        # Check for structured transactions (just below reporting threshold)
        if self._is_structured_transaction(amount):
            alert = self._create_suspicious_activity_alert(
                customer_id=customer_id,
                account_id=account_id,
                activity_type=SuspiciousActivityType.STRUCTURED_TRANSACTION,
                description=f"Transaction amount {amount.to_string()} just below reporting threshold",
                risk_score=70
            )
            alerts.append(alert)
        
        # Check for unusual transaction size for customer
        if self._is_unusual_size_for_customer(customer_id, amount):
            alert = self._create_suspicious_activity_alert(
                customer_id=customer_id,
                account_id=account_id,
                activity_type=SuspiciousActivityType.UNUSUAL_TRANSACTION_SIZE,
                description=f"Transaction amount {amount.to_string()} unusual for customer pattern",
                risk_score=50
            )
            alerts.append(alert)
        
        return alerts
    
    def _check_velocity(self, customer_id: str, account_id: str, amount: Money) -> Optional[str]:
        """Check for high-velocity transactions"""
        # Look for multiple transactions in short time period
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        
        # In a real implementation, would query transaction history
        # For now, simplified velocity check
        recent_violations = self.storage.find(
            self.violations_table,
            {"customer_id": customer_id}
        )
        
        # Count violations in last hour
        recent_count = 0
        for violation_data in recent_violations:
            violation = self._violation_from_dict(violation_data)
            if violation.created_at > one_hour_ago:
                recent_count += 1
        
        if recent_count >= 5:  # More than 5 transactions/violations in last hour
            self._create_suspicious_activity_alert(
                customer_id=customer_id,
                account_id=account_id,
                activity_type=SuspiciousActivityType.HIGH_VELOCITY,
                description=f"High velocity: {recent_count} transactions in last hour",
                risk_score=60
            )
            return f"High transaction velocity detected: {recent_count} transactions in last hour"
        
        return None
    
    def _is_round_amount(self, amount: Money) -> bool:
        """Check if amount is suspiciously round (e.g., $1000.00, $5000.00)"""
        # Check if amount is divisible by 1000 or 500
        amount_int = int(amount.amount)
        return amount.amount == amount_int and (amount_int % 1000 == 0 or amount_int % 500 == 0)
    
    def _is_structured_transaction(self, amount: Money) -> bool:
        """Check if transaction appears to be structured to avoid reporting"""
        reporting_threshold = Money(Decimal('10000'), Currency.USD)  # $10K USD threshold
        
        if amount.currency != reporting_threshold.currency:
            return False
        
        # Check if amount is between 95% and 99.9% of threshold
        threshold_95 = reporting_threshold * Decimal('0.95')
        threshold_999 = reporting_threshold * Decimal('0.999')
        
        return threshold_95 <= amount <= threshold_999
    
    def _is_unusual_size_for_customer(self, customer_id: str, amount: Money) -> bool:
        """Check if transaction size is unusual for customer's typical pattern"""
        # Simplified implementation - in production would analyze historical patterns
        customer = self.customer_manager.get_customer(customer_id)
        if not customer:
            return False
        
        # For basic customers (Tier 0/1), amounts over $5K might be unusual
        if customer.kyc_tier in [KYCTier.TIER_0, KYCTier.TIER_1]:
            unusual_threshold = Money(Decimal('5000'), amount.currency)
            return amount > unusual_threshold
        
        return False
    
    def _get_daily_transaction_total(self, customer_id: str, currency: Currency) -> Money:
        """Get total transaction amount for customer today"""
        # Simplified implementation - in production would query actual transactions
        # For now, return zero as we don't have transaction history yet
        return Money(Decimal('0'), currency)
    
    def _get_monthly_transaction_total(self, customer_id: str, currency: Currency) -> Money:
        """Get total transaction amount for customer this month"""
        # Simplified implementation - in production would query actual transactions
        return Money(Decimal('0'), currency)
    
    def _create_large_transaction_report(
        self,
        customer_id: str,
        transaction_id: str,
        amount: Money,
        transaction_type: str
    ) -> LargeTransactionReport:
        """Create large transaction report"""
        now = datetime.now(timezone.utc)
        report_id = str(uuid.uuid4())
        
        # Get reporting threshold
        threshold = Money(Decimal('10000'), Currency.USD)  # Simplified
        
        report = LargeTransactionReport(
            id=report_id,
            created_at=now,
            updated_at=now,
            customer_id=customer_id,
            transaction_id=transaction_id,
            amount=amount,
            transaction_type=transaction_type,
            reporting_threshold=threshold
        )
        
        # Save report
        report_dict = self._report_to_dict(report)
        self.storage.save(self.reports_table, report.id, report_dict)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.LARGE_TRANSACTION_REPORTED,
            entity_type="transaction",
            entity_id=transaction_id,
            metadata={
                "customer_id": customer_id,
                "amount": amount.to_string(),
                "threshold": threshold.to_string(),
                "report_id": report_id
            }
        )
        
        return report
    
    def _create_suspicious_activity_alert(
        self,
        customer_id: str,
        activity_type: SuspiciousActivityType,
        description: str,
        risk_score: int,
        account_id: Optional[str] = None,
        transaction_id: Optional[str] = None
    ) -> SuspiciousActivityAlert:
        """Create suspicious activity alert"""
        now = datetime.now(timezone.utc)
        alert_id = str(uuid.uuid4())
        
        alert = SuspiciousActivityAlert(
            id=alert_id,
            created_at=now,
            updated_at=now,
            customer_id=customer_id,
            account_id=account_id,
            transaction_id=transaction_id,
            activity_type=activity_type,
            description=description,
            risk_score=risk_score
        )
        
        # Save alert
        alert_dict = self._alert_to_dict(alert)
        self.storage.save(self.alerts_table, alert.id, alert_dict)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.SUSPICIOUS_ACTIVITY_FLAGGED,
            entity_type="customer",
            entity_id=customer_id,
            metadata={
                "alert_id": alert_id,
                "activity_type": activity_type.value,
                "risk_score": risk_score,
                "description": description
            }
        )
        
        return alert
    
    def _record_violation(
        self,
        customer_id: str,
        account_id: str,
        rule_type: ComplianceRuleType,
        description: str,
        amount: Money,
        action_taken: ComplianceAction,
        transaction_id: Optional[str] = None
    ) -> ComplianceViolation:
        """Record compliance violation"""
        now = datetime.now(timezone.utc)
        violation_id = str(uuid.uuid4())
        
        violation = ComplianceViolation(
            id=violation_id,
            created_at=now,
            updated_at=now,
            customer_id=customer_id,
            account_id=account_id,
            transaction_id=transaction_id,
            rule_type=rule_type,
            description=description,
            amount=amount,
            action_taken=action_taken
        )
        
        # Save violation
        violation_dict = self._violation_to_dict(violation)
        self.storage.save(self.violations_table, violation.id, violation_dict)
        
        return violation
    
    def get_customer_violations(self, customer_id: str) -> List[ComplianceViolation]:
        """Get all violations for a customer"""
        violations_data = self.storage.find(self.violations_table, {"customer_id": customer_id})
        return [self._violation_from_dict(data) for data in violations_data]
    
    def get_suspicious_alerts(
        self,
        status: Optional[str] = None,
        min_risk_score: Optional[int] = None
    ) -> List[SuspiciousActivityAlert]:
        """Get suspicious activity alerts with optional filters"""
        all_alerts_data = self.storage.load_all(self.alerts_table)
        alerts = [self._alert_from_dict(data) for data in all_alerts_data]
        
        if status:
            alerts = [a for a in alerts if a.status == status]
        
        if min_risk_score:
            alerts = [a for a in alerts if a.risk_score >= min_risk_score]
        
        # Sort by risk score (highest first) and creation time
        alerts.sort(key=lambda x: (-x.risk_score, -x.created_at.timestamp()))
        
        return alerts
    
    def resolve_alert(
        self,
        alert_id: str,
        resolution: str,
        notes: str,
        reviewer_id: str
    ) -> SuspiciousActivityAlert:
        """Resolve a suspicious activity alert"""
        alert_dict = self.storage.load(self.alerts_table, alert_id)
        if not alert_dict:
            raise ValueError(f"Alert {alert_id} not found")
        
        alert = self._alert_from_dict(alert_dict)
        
        now = datetime.now(timezone.utc)
        alert.status = resolution
        alert.resolution_notes = notes
        alert.assigned_to = reviewer_id
        alert.resolved_at = now
        alert.updated_at = now
        
        # Save updated alert
        alert_dict = self._alert_to_dict(alert)
        self.storage.save(self.alerts_table, alert.id, alert_dict)
        
        return alert
    
    def _violation_to_dict(self, violation: ComplianceViolation) -> Dict:
        """Convert violation to dictionary"""
        result = violation.to_dict()
        result['rule_type'] = violation.rule_type.value
        result['action_taken'] = violation.action_taken.value
        result['amount'] = str(violation.amount.amount)
        result['currency'] = violation.amount.currency.code
        return result
    
    def _violation_from_dict(self, data: Dict) -> ComplianceViolation:
        """Convert dictionary to violation"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        return ComplianceViolation(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            customer_id=data['customer_id'],
            account_id=data['account_id'],
            transaction_id=data.get('transaction_id'),
            rule_type=ComplianceRuleType(data['rule_type']),
            description=data['description'],
            amount=Money(Decimal(data['amount']), Currency[data['currency']]),
            action_taken=ComplianceAction(data['action_taken']),
            reviewer_id=data.get('reviewer_id'),
            review_notes=data.get('review_notes')
        )
    
    def _alert_to_dict(self, alert: SuspiciousActivityAlert) -> Dict:
        """Convert alert to dictionary"""
        result = alert.to_dict()
        result['activity_type'] = alert.activity_type.value
        
        if alert.resolved_at:
            result['resolved_at'] = alert.resolved_at.isoformat()
        
        return result
    
    def _alert_from_dict(self, data: Dict) -> SuspiciousActivityAlert:
        """Convert dictionary to alert"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        resolved_at = None
        if data.get('resolved_at'):
            resolved_at = datetime.fromisoformat(data['resolved_at'])
        
        return SuspiciousActivityAlert(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            customer_id=data['customer_id'],
            account_id=data.get('account_id'),
            transaction_id=data.get('transaction_id'),
            activity_type=SuspiciousActivityType(data['activity_type']),
            description=data['description'],
            risk_score=data['risk_score'],
            status=data['status'],
            assigned_to=data.get('assigned_to'),
            resolution_notes=data.get('resolution_notes'),
            resolved_at=resolved_at
        )
    
    def _report_to_dict(self, report: LargeTransactionReport) -> Dict:
        """Convert report to dictionary"""
        result = report.to_dict()
        result['amount'] = str(report.amount.amount)
        result['amount_currency'] = report.amount.currency.code
        result['reporting_threshold'] = str(report.reporting_threshold.amount)
        result['threshold_currency'] = report.reporting_threshold.currency.code
        
        if report.filed_at:
            result['filed_at'] = report.filed_at.isoformat()
        
        return result