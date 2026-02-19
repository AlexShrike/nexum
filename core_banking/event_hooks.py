"""
Event Hooks Module

Hooks the event publisher into existing banking modules so events fire automatically
when operations complete successfully. Uses wrapper/proxy pattern to maintain
loose coupling.
"""

import logging
from typing import Optional, Any
from functools import wraps

from .kafka_integration import NexumEventPublisher, EventBus


class EventEnabledMixin:
    """Mixin to add event publishing capability to existing classes"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_publisher: Optional[NexumEventPublisher] = None
    
    def set_event_publisher(self, event_publisher: NexumEventPublisher) -> None:
        """Set the event publisher for this instance"""
        self._event_publisher = event_publisher
    
    def _publish_event(self, method_name: str, *args, **kwargs) -> None:
        """Helper to publish events if publisher is available"""
        if self._event_publisher:
            try:
                method = getattr(self._event_publisher, method_name)
                method(*args, **kwargs)
            except Exception as e:
                logging.error(f"Error publishing event {method_name}: {e}")


class EventHookManager:
    """Manages event hooks for the banking system"""
    
    def __init__(self, event_publisher: NexumEventPublisher):
        self.event_publisher = event_publisher
        self._original_methods = {}  # Store original methods for restoration
    
    def enable_transaction_events(self, transaction_processor) -> None:
        """Enable events for transaction processor"""
        if hasattr(transaction_processor, '_event_publisher'):
            transaction_processor.set_event_publisher(self.event_publisher)
            return
        
        # Monkey patch approach for existing classes
        original_process = transaction_processor.process_transaction
        original_create = transaction_processor.create_transaction
        
        def process_transaction_with_events(transaction):
            """Wrapper for process_transaction that fires events"""
            try:
                result = original_process(transaction)
                # Fire transaction posted event on success
                if hasattr(transaction, 'state') and transaction.state.value == 'completed':
                    self.event_publisher.on_transaction_posted(transaction)
                elif hasattr(transaction, 'state') and transaction.state.value == 'failed':
                    error_msg = getattr(transaction, 'error_message', 'Transaction failed')
                    self.event_publisher.on_transaction_failed(transaction, error_msg)
                return result
            except Exception as e:
                # Fire transaction failed event
                self.event_publisher.on_transaction_failed(transaction, str(e))
                raise
        
        def create_transaction_with_events(*args, **kwargs):
            """Wrapper for create_transaction that fires events"""
            transaction = original_create(*args, **kwargs)
            # Fire transaction created event
            self.event_publisher.on_transaction_created(transaction)
            return transaction
        
        # Replace methods
        transaction_processor.process_transaction = process_transaction_with_events
        transaction_processor.create_transaction = create_transaction_with_events
        
        # Store originals for potential restoration
        self._original_methods[transaction_processor] = {
            'process_transaction': original_process,
            'create_transaction': original_create
        }
    
    def enable_account_events(self, account_manager) -> None:
        """Enable events for account manager"""
        if hasattr(account_manager, '_event_publisher'):
            account_manager.set_event_publisher(self.event_publisher)
            return
        
        original_create = account_manager.create_account
        original_update_state = account_manager.update_account_state
        
        def create_account_with_events(*args, **kwargs):
            """Wrapper for create_account that fires events"""
            account = original_create(*args, **kwargs)
            self.event_publisher.on_account_created(account)
            return account
        
        def update_account_state_with_events(*args, **kwargs):
            """Wrapper for update_account_state that fires events"""
            account = original_update_state(*args, **kwargs)
            self.event_publisher.on_account_updated(account)
            return account
        
        account_manager.create_account = create_account_with_events
        account_manager.update_account_state = update_account_state_with_events
        
        self._original_methods[account_manager] = {
            'create_account': original_create,
            'update_account_state': original_update_state
        }
    
    def enable_customer_events(self, customer_manager) -> None:
        """Enable events for customer manager"""
        if hasattr(customer_manager, '_event_publisher'):
            customer_manager.set_event_publisher(self.event_publisher)
            return
        
        original_create = customer_manager.create_customer
        original_update = customer_manager.update_customer_info
        original_update_kyc = customer_manager.update_kyc_status
        
        def create_customer_with_events(*args, **kwargs):
            """Wrapper for create_customer that fires events"""
            customer = original_create(*args, **kwargs)
            self.event_publisher.on_customer_created(customer)
            return customer
        
        def update_customer_with_events(*args, **kwargs):
            """Wrapper for update_customer that fires events"""
            customer = original_update(*args, **kwargs)
            self.event_publisher.on_customer_updated(customer)
            return customer
        
        def update_kyc_with_events(customer_id, status, tier=None, **kwargs):
            """Wrapper for update_kyc_status that fires events"""
            # Get old values
            try:
                old_customer = customer_manager.get_customer(customer_id)
                old_status = old_customer.kyc_status if old_customer else None
                old_tier = old_customer.kyc_tier if old_customer else None
            except:
                old_status = None
                old_tier = None
            
            customer = original_update_kyc(customer_id, status, tier, **kwargs)
            self.event_publisher.on_customer_kyc_changed(customer, old_status, old_tier)
            return customer
        
        customer_manager.create_customer = create_customer_with_events
        customer_manager.update_customer_info = update_customer_with_events
        customer_manager.update_kyc_status = update_kyc_with_events
        
        self._original_methods[customer_manager] = {
            'create_customer': original_create,
            'update_customer_info': original_update,
            'update_kyc_status': original_update_kyc
        }
    
    def enable_loan_events(self, loan_manager) -> None:
        """Enable events for loan manager"""
        if hasattr(loan_manager, '_event_publisher'):
            loan_manager.set_event_publisher(self.event_publisher)
            return
        
        original_originate = loan_manager.originate_loan
        original_disburse = loan_manager.disburse_loan
        original_payment = getattr(loan_manager, 'make_payment', None)
        
        def originate_loan_with_events(*args, **kwargs):
            """Wrapper for originate_loan that fires events"""
            loan = original_originate(*args, **kwargs)
            self.event_publisher.on_loan_originated(loan)
            return loan
        
        def disburse_loan_with_events(*args, **kwargs):
            """Wrapper for disburse_loan that fires events"""
            loan = original_disburse(*args, **kwargs)
            self.event_publisher.on_loan_disbursed(loan)
            return loan
        
        loan_manager.originate_loan = originate_loan_with_events
        loan_manager.disburse_loan = disburse_loan_with_events
        
        stored_methods = {
            'originate_loan': original_originate,
            'disburse_loan': original_disburse
        }
        
        if original_payment:
            def make_payment_with_events(loan_id, payment_amount, **kwargs):
                """Wrapper for make_payment that fires events"""
                result = original_payment(loan_id, payment_amount, **kwargs)
                loan = loan_manager.get_loan(loan_id)
                self.event_publisher.on_loan_payment(loan, payment_amount)
                return result
            
            loan_manager.make_payment = make_payment_with_events
            stored_methods['make_payment'] = original_payment
        
        self._original_methods[loan_manager] = stored_methods
    
    def enable_compliance_events(self, compliance_engine) -> None:
        """Enable events for compliance engine"""
        if hasattr(compliance_engine, '_event_publisher'):
            compliance_engine.set_event_publisher(self.event_publisher)
            return
        
        # Look for methods that generate alerts
        original_check_transaction = getattr(compliance_engine, 'check_transaction', None)
        original_check_customer = getattr(compliance_engine, 'check_customer', None)
        
        def check_transaction_with_events(*args, **kwargs):
            """Wrapper for check_transaction that fires compliance events"""
            result = original_check_transaction(*args, **kwargs)
            # If result indicates an alert or suspicious activity
            if isinstance(result, dict) and result.get('alert'):
                self.event_publisher.on_compliance_alert(result)
            return result
        
        def check_customer_with_events(*args, **kwargs):
            """Wrapper for check_customer that fires compliance events"""
            result = original_check_customer(*args, **kwargs)
            # If result indicates an alert
            if isinstance(result, dict) and result.get('alert'):
                self.event_publisher.on_compliance_alert(result)
            return result
        
        stored_methods = {}
        
        if original_check_transaction:
            compliance_engine.check_transaction = check_transaction_with_events
            stored_methods['check_transaction'] = original_check_transaction
        
        if original_check_customer:
            compliance_engine.check_customer = check_customer_with_events
            stored_methods['check_customer'] = original_check_customer
        
        if stored_methods:
            self._original_methods[compliance_engine] = stored_methods
    
    def enable_collections_events(self, collections_manager) -> None:
        """Enable events for collections manager"""
        if hasattr(collections_manager, '_event_publisher'):
            collections_manager.set_event_publisher(self.event_publisher)
            return
        
        original_create_case = getattr(collections_manager, 'create_collection_case', None)
        
        if original_create_case:
            def create_case_with_events(*args, **kwargs):
                """Wrapper for create_collection_case that fires events"""
                case = original_create_case(*args, **kwargs)
                self.event_publisher.on_collection_case_created(case)
                return case
            
            collections_manager.create_collection_case = create_case_with_events
            self._original_methods[collections_manager] = {
                'create_collection_case': original_create_case
            }
    
    def enable_workflow_events(self, workflow_engine) -> None:
        """Enable events for workflow engine"""
        if hasattr(workflow_engine, '_event_publisher'):
            workflow_engine.set_event_publisher(self.event_publisher)
            return
        
        original_complete = getattr(workflow_engine, 'complete_workflow', None)
        
        if original_complete:
            def complete_workflow_with_events(*args, **kwargs):
                """Wrapper for complete_workflow that fires events"""
                workflow = original_complete(*args, **kwargs)
                self.event_publisher.on_workflow_completed(workflow)
                return workflow
            
            workflow_engine.complete_workflow = complete_workflow_with_events
            self._original_methods[workflow_engine] = {
                'complete_workflow': original_complete
            }
    
    def enable_audit_events(self, audit_trail) -> None:
        """Enable events for audit trail"""
        if hasattr(audit_trail, '_event_publisher'):
            audit_trail.set_event_publisher(self.event_publisher)
            return
        
        original_log = audit_trail.log_event
        
        def log_event_with_events(*args, **kwargs):
            """Wrapper for log_event that fires events"""
            audit_event = original_log(*args, **kwargs)
            self.event_publisher.on_audit_event(audit_event)
            return audit_event
        
        audit_trail.log_event = log_event_with_events
        self._original_methods[audit_trail] = {
            'log_event': original_log
        }
    
    def enable_all_events(self, banking_components: dict) -> None:
        """Enable events for all provided banking components"""
        
        # Enable transaction events
        if 'transaction_processor' in banking_components:
            self.enable_transaction_events(banking_components['transaction_processor'])
        
        # Enable account events  
        if 'account_manager' in banking_components:
            self.enable_account_events(banking_components['account_manager'])
        
        # Enable customer events
        if 'customer_manager' in banking_components:
            self.enable_customer_events(banking_components['customer_manager'])
        
        # Enable loan events
        if 'loan_manager' in banking_components:
            self.enable_loan_events(banking_components['loan_manager'])
        
        # Enable compliance events
        if 'compliance_engine' in banking_components:
            self.enable_compliance_events(banking_components['compliance_engine'])
        
        # Enable collections events
        if 'collections_manager' in banking_components:
            self.enable_collections_events(banking_components['collections_manager'])
        
        # Enable workflow events
        if 'workflow_engine' in banking_components:
            self.enable_workflow_events(banking_components['workflow_engine'])
        
        # Enable audit events
        if 'audit_trail' in banking_components:
            self.enable_audit_events(banking_components['audit_trail'])
        
        logging.info("Event hooks enabled for all banking components")
    
    def disable_all_events(self) -> None:
        """Restore all original methods (disable event hooks)"""
        for obj, methods in self._original_methods.items():
            for method_name, original_method in methods.items():
                setattr(obj, method_name, original_method)
        
        self._original_methods.clear()
        logging.info("All event hooks disabled")


def create_event_enabled_banking_system(event_bus: EventBus, banking_components: dict) -> EventHookManager:
    """
    Convenience function to create an event-enabled banking system
    
    Args:
        event_bus: The event bus to use for publishing events
        banking_components: Dictionary of banking system components
    
    Returns:
        EventHookManager instance for managing the event hooks
    """
    event_publisher = NexumEventPublisher(event_bus)
    hook_manager = EventHookManager(event_publisher)
    hook_manager.enable_all_events(banking_components)
    
    return hook_manager