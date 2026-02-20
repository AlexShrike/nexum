"""
Authentication and authorization dependencies
"""

from ..storage import InMemoryStorage, SQLiteStorage
from ..audit import AuditTrail
from ..ledger import GeneralLedger
from ..accounts import AccountManager
from ..customers import CustomerManager
from ..compliance import ComplianceEngine
from ..transactions import TransactionProcessor
from ..interest import InterestEngine
from ..credit import CreditLineManager
from ..loans import LoanManager
from ..products import ProductEngine
from ..collections import CollectionsManager
from ..reporting import ReportingEngine
from ..workflows import WorkflowEngine
from ..rbac import RBACManager
from ..custom_fields import CustomFieldManager
from ..fraud_client import BastionClient
from ..config import get_config


class BankingSystem:
    """Core banking system with all components initialized"""
    
    def __init__(self, use_sqlite: bool = True):
        # Initialize storage
        if use_sqlite:
            self.storage = SQLiteStorage("core_banking.db")
        else:
            self.storage = InMemoryStorage()
        
        # Initialize core components
        self.audit_trail = AuditTrail(self.storage)
        self.ledger = GeneralLedger(self.storage, self.audit_trail)
        self.account_manager = AccountManager(self.storage, self.ledger, self.audit_trail)
        self.customer_manager = CustomerManager(self.storage, self.audit_trail)
        self.compliance_engine = ComplianceEngine(self.storage, self.customer_manager, self.audit_trail)
        
        # Initialize fraud client if configured
        fraud_client = self._create_fraud_client()
        
        self.transaction_processor = TransactionProcessor(
            self.storage, self.ledger, self.account_manager, 
            self.customer_manager, self.compliance_engine, self.audit_trail,
            fraud_client=fraud_client
        )
        self.interest_engine = InterestEngine(
            self.storage, self.ledger, self.account_manager,
            self.transaction_processor, self.audit_trail
        )
        self.credit_manager = CreditLineManager(
            self.storage, self.account_manager, self.transaction_processor,
            self.interest_engine, self.audit_trail
        )
        self.loan_manager = LoanManager(
            self.storage, self.account_manager, self.transaction_processor,
            self.audit_trail
        )
        
        # Initialize new modules
        self.product_engine = ProductEngine(self.storage, self.audit_trail)
        self.collections_manager = CollectionsManager(
            self.storage, self.account_manager, self.loan_manager, self.credit_manager
        )
        self.reporting_engine = ReportingEngine(
            self.storage, self.ledger, self.account_manager, self.loan_manager,
            self.credit_manager, self.collections_manager, self.customer_manager,
            self.product_engine, self.audit_trail
        )
        self.workflow_engine = WorkflowEngine(self.storage, self.audit_trail)
        self.rbac_manager = RBACManager(self.storage, self.audit_trail)
        self.custom_field_manager = CustomFieldManager(self.storage, self.audit_trail)
    
    def _create_fraud_client(self):
        """Create fraud client based on configuration"""
        config = get_config()
        
        # Only create fraud client if URL is configured
        if not config.bastion_url:
            return None
        
        return BastionClient(
            base_url=config.bastion_url,
            timeout=config.bastion_timeout,
            api_key=config.bastion_api_key if config.bastion_api_key else None,
            enabled=True,
            fallback_on_error=config.bastion_fallback
        )


# Global banking system instance
banking_system = BankingSystem(use_sqlite=True)


# Dependency to get banking system
def get_banking_system() -> BankingSystem:
    return banking_system