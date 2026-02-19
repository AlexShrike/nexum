"""
Workflow Engine Module

Configurable approval chains and customer journeys for various banking processes.
Inspired by Oradian's "Custom Workflows" - supports complex approval hierarchies,
parallel approvals, auto-approval conditions, and SLA management.
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType


class WorkflowType(Enum):
    """Types of workflows supported"""
    LOAN_APPROVAL = "loan_approval"
    ACCOUNT_OPENING = "account_opening"
    KYC_REVIEW = "kyc_review"
    CREDIT_LIMIT_CHANGE = "credit_limit_change"
    TRANSACTION_OVERRIDE = "transaction_override"
    WRITE_OFF_APPROVAL = "write_off_approval"
    PRODUCT_LAUNCH = "product_launch"
    CUSTOMER_ONBOARDING = "customer_onboarding"
    DISPUTE_RESOLUTION = "dispute_resolution"
    CUSTOM = "custom"


class StepType(Enum):
    """Types of workflow steps"""
    APPROVAL = "approval"
    REVIEW = "review"
    DATA_ENTRY = "data_entry"
    VERIFICATION = "verification"
    NOTIFICATION = "notification"
    AUTOMATIC_CHECK = "automatic_check"
    ESCALATION = "escalation"
    PARALLEL_APPROVAL = "parallel_approval"


class StepStatus(Enum):
    """Status of individual workflow steps"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ESCALATED = "escalated"


class WorkflowStatus(Enum):
    """Status of entire workflow instances"""
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass
class StepApproval(StorageRecord):
    """Individual approval within a parallel approval step"""
    approver: str
    decision: str  # APPROVED or REJECTED
    comments: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WorkflowStepDefinition:
    """Definition of a single workflow step (template)"""
    step_number: int
    name: str
    step_type: StepType
    required_role: str
    required_approvals: int = 1
    auto_approve_conditions: Optional[Dict[str, Any]] = field(default_factory=dict)
    sla_hours: Optional[int] = None
    escalation_role: Optional[str] = None
    can_skip: bool = False


@dataclass
class WorkflowDefinition(StorageRecord):
    """Workflow definition (template)"""
    name: str
    description: str
    workflow_type: WorkflowType
    steps: List[WorkflowStepDefinition]
    version: str = "1.0"
    is_active: bool = True
    created_by: str = ""
    sla_hours: Optional[int] = None


@dataclass
class WorkflowStepInstance(StorageRecord):
    """Running instance of a workflow step"""
    step_number: int
    name: str
    step_type: StepType
    status: StepStatus
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    completed_at: Optional[datetime] = None
    decision: Optional[str] = None
    comments: Optional[str] = None
    approvals: List[StepApproval] = field(default_factory=list)


@dataclass
class WorkflowInstance(StorageRecord):
    """Running workflow instance"""
    definition_id: str
    workflow_type: WorkflowType
    status: WorkflowStatus
    entity_type: str
    entity_id: str
    initiated_by: str
    initiated_at: datetime
    current_step: int = 1
    steps: List[WorkflowStepInstance] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


class WorkflowEngine:
    """Main workflow engine for managing workflow definitions and instances"""
    
    def __init__(self, storage: StorageInterface, audit_manager: Optional[AuditTrail] = None):
        self.storage = storage
        self.audit = audit_manager or AuditTrail(storage)
    
    # Definition Management
    
    def create_definition(self, definition: WorkflowDefinition) -> str:
        """Create a new workflow definition"""
        if not definition.id:
            definition.id = str(uuid.uuid4())
        
        definition.created_at = datetime.now(timezone.utc)
        definition.updated_at = definition.created_at
        
        # Validate definition
        self._validate_definition(definition)
        
        # Save definition
        data = definition.to_dict()
        data['workflow_type'] = definition.workflow_type.value  # Store as string value
        data['steps'] = [
            {
                'step_number': step.step_number,
                'name': step.name,
                'step_type': step.step_type.value,
                'required_role': step.required_role,
                'required_approvals': step.required_approvals,
                'auto_approve_conditions': step.auto_approve_conditions,
                'sla_hours': step.sla_hours,
                'escalation_role': step.escalation_role,
                'can_skip': step.can_skip
            }
            for step in definition.steps
        ]
        
        self.storage.save('workflow_definitions', definition.id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_DEFINITION_CREATED,
            'workflow_definition',
            definition.id,
            {'name': definition.name, 'type': definition.workflow_type.value},
            definition.created_by
        )
        
        return definition.id
    
    def get_definition(self, definition_id: str) -> Optional[WorkflowDefinition]:
        """Get a workflow definition by ID"""
        data = self.storage.load('workflow_definitions', definition_id)
        if not data:
            return None
        
        # Convert steps back from dict
        steps = []
        for step_data in data.get('steps', []):
            steps.append(WorkflowStepDefinition(
                step_number=step_data['step_number'],
                name=step_data['name'],
                step_type=StepType(step_data['step_type']),
                required_role=step_data['required_role'],
                required_approvals=step_data.get('required_approvals', 1),
                auto_approve_conditions=step_data.get('auto_approve_conditions', {}),
                sla_hours=step_data.get('sla_hours'),
                escalation_role=step_data.get('escalation_role'),
                can_skip=step_data.get('can_skip', False)
            ))
        
        data['steps'] = steps
        data['workflow_type'] = WorkflowType(data['workflow_type'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        return WorkflowDefinition(**data)
    
    def list_definitions(self, workflow_type: Optional[WorkflowType] = None) -> List[WorkflowDefinition]:
        """List all workflow definitions, optionally filtered by type"""
        definitions = []
        all_data = self.storage.load_all('workflow_definitions')
        
        for data in all_data:
            definition = self.get_definition(data['id'])
            if definition and (not workflow_type or definition.workflow_type == workflow_type):
                definitions.append(definition)
        
        return sorted(definitions, key=lambda d: d.name)
    
    def activate_definition(self, definition_id: str) -> bool:
        """Activate a workflow definition"""
        definition = self.get_definition(definition_id)
        if not definition:
            return False
        
        definition.is_active = True
        definition.updated_at = datetime.now(timezone.utc)
        
        data = definition.to_dict()
        data['workflow_type'] = definition.workflow_type.value  # Store as string value
        data['steps'] = [
            {
                'step_number': step.step_number,
                'name': step.name,
                'step_type': step.step_type.value,
                'required_role': step.required_role,
                'required_approvals': step.required_approvals,
                'auto_approve_conditions': step.auto_approve_conditions,
                'sla_hours': step.sla_hours,
                'escalation_role': step.escalation_role,
                'can_skip': step.can_skip
            }
            for step in definition.steps
        ]
        
        self.storage.save('workflow_definitions', definition_id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_DEFINITION_UPDATED,
            'workflow_definition',
            definition_id,
            {'action': 'activated'},
            'system'
        )
        
        return True
    
    def deactivate_definition(self, definition_id: str) -> bool:
        """Deactivate a workflow definition"""
        definition = self.get_definition(definition_id)
        if not definition:
            return False
        
        definition.is_active = False
        definition.updated_at = datetime.now(timezone.utc)
        
        data = definition.to_dict()
        data['workflow_type'] = definition.workflow_type.value  # Store as string value
        data['steps'] = [
            {
                'step_number': step.step_number,
                'name': step.name,
                'step_type': step.step_type.value,
                'required_role': step.required_role,
                'required_approvals': step.required_approvals,
                'auto_approve_conditions': step.auto_approve_conditions,
                'sla_hours': step.sla_hours,
                'escalation_role': step.escalation_role,
                'can_skip': step.can_skip
            }
            for step in definition.steps
        ]
        
        self.storage.save('workflow_definitions', definition_id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_DEFINITION_UPDATED,
            'workflow_definition',
            definition_id,
            {'action': 'deactivated'},
            'system'
        )
        
        return True
    
    # Instance Management
    
    def start_workflow(self, definition_id: str, entity_type: str, entity_id: str, 
                      initiated_by: str, context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Start a new workflow instance"""
        definition = self.get_definition(definition_id)
        if not definition or not definition.is_active:
            return None
        
        instance_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        # Create step instances from definition
        step_instances = []
        for step_def in definition.steps:
            step_instance = WorkflowStepInstance(
                id=str(uuid.uuid4()),
                created_at=now,
                updated_at=now,
                step_number=step_def.step_number,
                name=step_def.name,
                step_type=step_def.step_type,
                status=StepStatus.PENDING if step_def.step_number == 1 else StepStatus.PENDING
            )
            step_instances.append(step_instance)
        
        # Set first step as pending
        if step_instances:
            step_instances[0].status = StepStatus.PENDING
        
        instance = WorkflowInstance(
            id=instance_id,
            created_at=now,
            updated_at=now,
            definition_id=definition_id,
            workflow_type=definition.workflow_type,
            status=WorkflowStatus.ACTIVE,
            entity_type=entity_type,
            entity_id=entity_id,
            initiated_by=initiated_by,
            initiated_at=now,
            current_step=1,
            steps=step_instances,
            context=context or {}
        )
        
        # Save instance
        data = instance.to_dict()
        data['workflow_type'] = instance.workflow_type.value
        data['status'] = instance.status.value
        data['steps'] = [self._step_instance_to_dict(step) for step in instance.steps]
        
        self.storage.save('workflow_instances', instance_id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_INSTANCE_CREATED,
            'workflow_instance',
            instance_id,
            {
                'definition_id': definition_id,
                'entity_type': entity_type,
                'entity_id': entity_id
            },
            initiated_by
        )
        
        return instance_id
    
    def get_workflow(self, instance_id: str) -> Optional[WorkflowInstance]:
        """Get a workflow instance by ID"""
        data = self.storage.load('workflow_instances', instance_id)
        if not data:
            return None
        
        # Convert data back to instance
        steps = []
        for step_data in data.get('steps', []):
            steps.append(self._dict_to_step_instance(step_data))
        
        data['steps'] = steps
        data['workflow_type'] = WorkflowType(data['workflow_type'])
        data['status'] = WorkflowStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        data['initiated_at'] = datetime.fromisoformat(data['initiated_at'])
        
        if data.get('completed_at'):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        if data.get('cancelled_at'):
            data['cancelled_at'] = datetime.fromisoformat(data['cancelled_at'])
        
        return WorkflowInstance(**data)
    
    def get_workflows(self, status: Optional[WorkflowStatus] = None, 
                     workflow_type: Optional[WorkflowType] = None,
                     entity_id: Optional[str] = None) -> List[WorkflowInstance]:
        """Get workflows with optional filters"""
        workflows = []
        all_data = self.storage.load_all('workflow_instances')
        
        for data in all_data:
            workflow = self.get_workflow(data['id'])
            if workflow:
                if status and workflow.status != status:
                    continue
                if workflow_type and workflow.workflow_type != workflow_type:
                    continue
                if entity_id and workflow.entity_id != entity_id:
                    continue
                workflows.append(workflow)
        
        return sorted(workflows, key=lambda w: w.initiated_at, reverse=True)
    
    def get_pending_tasks(self, role: Optional[str] = None, user: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all pending tasks, optionally filtered by role or user"""
        tasks = []
        active_workflows = self.get_workflows(status=WorkflowStatus.ACTIVE)
        
        for workflow in active_workflows:
            definition = self.get_definition(workflow.definition_id)
            if not definition:
                continue
            
            current_step_instance = None
            current_step_def = None
            
            for step in workflow.steps:
                if step.step_number == workflow.current_step:
                    current_step_instance = step
                    break
            
            if current_step_instance and current_step_instance.status in [StepStatus.PENDING, StepStatus.IN_PROGRESS]:
                for step_def in definition.steps:
                    if step_def.step_number == workflow.current_step:
                        current_step_def = step_def
                        break
                
                if current_step_def:
                    # Filter by role if specified
                    if role and current_step_def.required_role != role:
                        continue
                    
                    # Filter by user if specified
                    if user and current_step_instance.assigned_to and current_step_instance.assigned_to != user:
                        continue
                    
                    tasks.append({
                        'workflow_id': workflow.id,
                        'definition_name': definition.name,
                        'step_number': current_step_instance.step_number,
                        'step_name': current_step_instance.name,
                        'step_type': current_step_instance.step_type.value,
                        'required_role': current_step_def.required_role,
                        'entity_type': workflow.entity_type,
                        'entity_id': workflow.entity_id,
                        'assigned_to': current_step_instance.assigned_to,
                        'initiated_by': workflow.initiated_by,
                        'initiated_at': workflow.initiated_at,
                        'context': workflow.context
                    })
        
        return tasks
    
    # Step Actions
    
    def assign_step(self, instance_id: str, step_number: int, user: str) -> bool:
        """Assign a workflow step to a specific user"""
        workflow = self.get_workflow(instance_id)
        if not workflow or workflow.status != WorkflowStatus.ACTIVE:
            return False
        
        step_instance = None
        for step in workflow.steps:
            if step.step_number == step_number:
                step_instance = step
                break
        
        if not step_instance or step_instance.status != StepStatus.PENDING:
            return False
        
        step_instance.assigned_to = user
        step_instance.assigned_at = datetime.now(timezone.utc)
        step_instance.status = StepStatus.IN_PROGRESS
        step_instance.updated_at = datetime.now(timezone.utc)
        
        workflow.updated_at = datetime.now(timezone.utc)
        
        # Save workflow
        data = workflow.to_dict()
        data['workflow_type'] = workflow.workflow_type.value
        data['status'] = workflow.status.value
        data['steps'] = [self._step_instance_to_dict(step) for step in workflow.steps]
        
        self.storage.save('workflow_instances', instance_id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_INSTANCE_UPDATED,
            'workflow_instance',
            instance_id,
            {
                'action': 'step_assigned',
                'step_number': step_number,
                'assigned_to': user
            },
            user
        )
        
        return True
    
    def approve_step(self, instance_id: str, step_number: int, approver: str, 
                    comments: Optional[str] = None) -> bool:
        """Approve a workflow step and advance workflow"""
        workflow = self.get_workflow(instance_id)
        if not workflow or workflow.status != WorkflowStatus.ACTIVE:
            return False
        
        definition = self.get_definition(workflow.definition_id)
        if not definition:
            return False
        
        step_instance = None
        step_definition = None
        
        for step in workflow.steps:
            if step.step_number == step_number:
                step_instance = step
                break
        
        for step_def in definition.steps:
            if step_def.step_number == step_number:
                step_definition = step_def
                break
        
        if not step_instance or not step_definition:
            return False
        
        if step_instance.status not in [StepStatus.PENDING, StepStatus.IN_PROGRESS]:
            return False
        
        now = datetime.now(timezone.utc)
        
        # Handle parallel approvals
        if step_definition.step_type == StepType.PARALLEL_APPROVAL:
            # Set status to IN_PROGRESS if this is the first approval
            if step_instance.status == StepStatus.PENDING:
                step_instance.status = StepStatus.IN_PROGRESS
            
            # Add approval
            approval = StepApproval(
                id=str(uuid.uuid4()),
                created_at=now,
                updated_at=now,
                approver=approver,
                decision="APPROVED",
                comments=comments,
                timestamp=now
            )
            step_instance.approvals.append(approval)
            
            # Check if we have enough approvals
            approved_count = sum(1 for a in step_instance.approvals if a.decision == "APPROVED")
            if approved_count >= step_definition.required_approvals:
                step_instance.status = StepStatus.APPROVED
                step_instance.completed_by = approver
                step_instance.completed_at = now
                step_instance.decision = "APPROVED"
                step_instance.comments = comments
        else:
            # Single approval
            step_instance.status = StepStatus.APPROVED
            step_instance.completed_by = approver
            step_instance.completed_at = now
            step_instance.decision = "APPROVED"
            step_instance.comments = comments
        
        step_instance.updated_at = now
        
        # Advance workflow if step is approved
        if step_instance.status == StepStatus.APPROVED:
            self._advance_workflow(workflow, definition)
        
        workflow.updated_at = now
        
        # Save workflow
        data = workflow.to_dict()
        data['workflow_type'] = workflow.workflow_type.value
        data['status'] = workflow.status.value
        data['steps'] = [self._step_instance_to_dict(step) for step in workflow.steps]
        
        self.storage.save('workflow_instances', instance_id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_INSTANCE_UPDATED,
            'workflow_instance',
            instance_id,
            {
                'action': 'step_approved',
                'step_number': step_number,
                'comments': comments
            },
            approver
        )
        
        return True
    
    def reject_step(self, instance_id: str, step_number: int, rejector: str, 
                   comments: Optional[str] = None) -> bool:
        """Reject a workflow step (typically rejects entire workflow)"""
        workflow = self.get_workflow(instance_id)
        if not workflow or workflow.status != WorkflowStatus.ACTIVE:
            return False
        
        step_instance = None
        for step in workflow.steps:
            if step.step_number == step_number:
                step_instance = step
                break
        
        if not step_instance:
            return False
        
        if step_instance.status not in [StepStatus.PENDING, StepStatus.IN_PROGRESS]:
            return False
        
        now = datetime.now(timezone.utc)
        
        step_instance.status = StepStatus.REJECTED
        step_instance.completed_by = rejector
        step_instance.completed_at = now
        step_instance.decision = "REJECTED"
        step_instance.comments = comments
        step_instance.updated_at = now
        
        # Reject entire workflow
        workflow.status = WorkflowStatus.REJECTED
        workflow.completed_at = now
        workflow.updated_at = now
        
        # Save workflow
        data = workflow.to_dict()
        data['workflow_type'] = workflow.workflow_type.value
        data['status'] = workflow.status.value
        data['steps'] = [self._step_instance_to_dict(step) for step in workflow.steps]
        
        self.storage.save('workflow_instances', instance_id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_INSTANCE_UPDATED,
            'workflow_instance',
            instance_id,
            {
                'action': 'step_rejected',
                'step_number': step_number,
                'comments': comments
            },
            rejector
        )
        
        return True
    
    def skip_step(self, instance_id: str, step_number: int, skipped_by: str, reason: str) -> bool:
        """Skip a workflow step if allowed"""
        workflow = self.get_workflow(instance_id)
        if not workflow or workflow.status != WorkflowStatus.ACTIVE:
            return False
        
        definition = self.get_definition(workflow.definition_id)
        if not definition:
            return False
        
        step_instance = None
        step_definition = None
        
        for step in workflow.steps:
            if step.step_number == step_number:
                step_instance = step
                break
        
        for step_def in definition.steps:
            if step_def.step_number == step_number:
                step_definition = step_def
                break
        
        if not step_instance or not step_definition or not step_definition.can_skip:
            return False
        
        if step_instance.status not in [StepStatus.PENDING, StepStatus.IN_PROGRESS]:
            return False
        
        now = datetime.now(timezone.utc)
        
        step_instance.status = StepStatus.SKIPPED
        step_instance.completed_by = skipped_by
        step_instance.completed_at = now
        step_instance.comments = reason
        step_instance.updated_at = now
        
        # Advance workflow
        self._advance_workflow(workflow, definition)
        
        workflow.updated_at = now
        
        # Save workflow
        data = workflow.to_dict()
        data['workflow_type'] = workflow.workflow_type.value
        data['status'] = workflow.status.value
        data['steps'] = [self._step_instance_to_dict(step) for step in workflow.steps]
        
        self.storage.save('workflow_instances', instance_id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_INSTANCE_UPDATED,
            'workflow_instance',
            instance_id,
            {
                'action': 'step_skipped',
                'step_number': step_number,
                'reason': reason
            },
            skipped_by
        )
        
        return True
    
    # Auto-processing
    
    def check_auto_approvals(self, instance_id: str) -> bool:
        """Check if current step can be auto-approved"""
        workflow = self.get_workflow(instance_id)
        if not workflow or workflow.status != WorkflowStatus.ACTIVE:
            return False
        
        definition = self.get_definition(workflow.definition_id)
        if not definition:
            return False
        
        current_step_def = None
        for step_def in definition.steps:
            if step_def.step_number == workflow.current_step:
                current_step_def = step_def
                break
        
        if not current_step_def or not current_step_def.auto_approve_conditions:
            return False
        
        # Check auto-approve conditions against context
        for condition_key, condition_value in current_step_def.auto_approve_conditions.items():
            if condition_key not in workflow.context:
                return False
            
            context_value = workflow.context[condition_key]
            
            # Handle different condition types
            if condition_key == "amount_below":
                if isinstance(context_value, (int, float, Decimal)):
                    if Decimal(str(context_value)) >= Decimal(str(condition_value)):
                        return False
                else:
                    return False
            else:
                # Direct comparison for other conditions
                if context_value != condition_value:
                    return False
        
        # All conditions met, auto-approve
        return self.approve_step(instance_id, workflow.current_step, "system", "Auto-approved")
    
    def check_sla_breaches(self) -> List[Dict[str, Any]]:
        """Find timed-out steps and escalate them"""
        breaches = []
        active_workflows = self.get_workflows(status=WorkflowStatus.ACTIVE)
        now = datetime.now(timezone.utc)
        
        for workflow in active_workflows:
            definition = self.get_definition(workflow.definition_id)
            if not definition:
                continue
            
            current_step_instance = None
            current_step_def = None
            
            for step in workflow.steps:
                if step.step_number == workflow.current_step:
                    current_step_instance = step
                    break
            
            for step_def in definition.steps:
                if step_def.step_number == workflow.current_step:
                    current_step_def = step_def
                    break
            
            if not current_step_instance or not current_step_def:
                continue
            
            # Check step SLA
            if current_step_def.sla_hours and current_step_instance.status in [StepStatus.PENDING, StepStatus.IN_PROGRESS]:
                step_start_time = current_step_instance.assigned_at or current_step_instance.created_at or workflow.initiated_at
                sla_deadline = step_start_time + timedelta(hours=current_step_def.sla_hours)
                
                if now > sla_deadline:
                    # Mark step as timed out
                    current_step_instance.status = StepStatus.TIMED_OUT
                    current_step_instance.updated_at = now
                    
                    # Escalate if escalation role defined
                    if current_step_def.escalation_role:
                        current_step_instance.status = StepStatus.ESCALATED
                        current_step_instance.assigned_to = current_step_def.escalation_role
                        current_step_instance.assigned_at = now
                    
                    breach_info = {
                        'workflow_id': workflow.id,
                        'step_number': workflow.current_step,
                        'step_name': current_step_instance.name,
                        'sla_hours': current_step_def.sla_hours,
                        'breach_time': now,
                        'escalated_to': current_step_def.escalation_role
                    }
                    breaches.append(breach_info)
                    
                    # Save updated workflow
                    data = workflow.to_dict()
                    data['workflow_type'] = workflow.workflow_type.value
                    data['status'] = workflow.status.value
                    data['steps'] = [self._step_instance_to_dict(step) for step in workflow.steps]
                    
                    self.storage.save('workflow_instances', workflow.id, data)
                    
                    self.audit.log_event(
                        AuditEventType.WORKFLOW_INSTANCE_UPDATED,
                        'workflow_instance',
                        workflow.id,
                        {
                            'action': 'sla_breach',
                            'step_number': workflow.current_step,
                            'escalated_to': current_step_def.escalation_role
                        },
                        'system'
                    )
        
        return breaches
    
    # Workflow Control
    
    def cancel_workflow(self, instance_id: str, cancelled_by: str, reason: str) -> bool:
        """Cancel a workflow"""
        workflow = self.get_workflow(instance_id)
        if not workflow or workflow.status not in [WorkflowStatus.ACTIVE, WorkflowStatus.DRAFT]:
            return False
        
        now = datetime.now(timezone.utc)
        
        workflow.status = WorkflowStatus.CANCELLED
        workflow.cancelled_at = now
        workflow.updated_at = now
        
        # Save workflow
        data = workflow.to_dict()
        data['workflow_type'] = workflow.workflow_type.value
        data['status'] = workflow.status.value
        data['steps'] = [self._step_instance_to_dict(step) for step in workflow.steps]
        
        self.storage.save('workflow_instances', instance_id, data)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_INSTANCE_UPDATED,
            'workflow_instance',
            instance_id,
            {
                'action': 'cancelled',
                'reason': reason
            },
            cancelled_by
        )
        
        return True
    
    def get_workflow_history(self, entity_type: str, entity_id: str) -> List[WorkflowInstance]:
        """Get all workflows for a specific entity"""
        return self.get_workflows(entity_id=entity_id)
    
    # Private helper methods
    
    def _validate_definition(self, definition: WorkflowDefinition):
        """Validate a workflow definition"""
        if not definition.steps:
            raise ValueError("Workflow must have at least one step")
        
        step_numbers = [step.step_number for step in definition.steps]
        if len(set(step_numbers)) != len(step_numbers):
            raise ValueError("Step numbers must be unique")
        
        if min(step_numbers) != 1:
            raise ValueError("First step must be numbered 1")
        
        sorted_numbers = sorted(step_numbers)
        for i, num in enumerate(sorted_numbers):
            if num != i + 1:
                raise ValueError("Step numbers must be consecutive")
    
    def _advance_workflow(self, workflow: WorkflowInstance, definition: WorkflowDefinition):
        """Advance workflow to next step or complete it"""
        # Check if there are more steps
        next_step_number = workflow.current_step + 1
        next_step_exists = any(step.step_number == next_step_number for step in workflow.steps)
        
        if next_step_exists:
            # Move to next step
            workflow.current_step = next_step_number
            
            # Set next step as pending
            for step in workflow.steps:
                if step.step_number == next_step_number:
                    step.status = StepStatus.PENDING
                    break
        else:
            # No more steps, complete workflow
            workflow.status = WorkflowStatus.COMPLETED
            workflow.completed_at = datetime.now(timezone.utc)
    
    def _step_instance_to_dict(self, step: WorkflowStepInstance) -> Dict[str, Any]:
        """Convert step instance to dictionary for storage"""
        data = step.to_dict()
        data['step_type'] = step.step_type.value
        data['status'] = step.status.value
        
        # Convert approvals
        approvals = []
        for approval in step.approvals:
            approval_data = approval.to_dict()
            approvals.append(approval_data)
        data['approvals'] = approvals
        
        return data
    
    def _dict_to_step_instance(self, data: Dict[str, Any]) -> WorkflowStepInstance:
        """Convert dictionary to step instance"""
        # Convert approvals
        approvals = []
        for approval_data in data.get('approvals', []):
            approval_data['created_at'] = datetime.fromisoformat(approval_data['created_at'])
            approval_data['updated_at'] = datetime.fromisoformat(approval_data['updated_at'])
            approval_data['timestamp'] = datetime.fromisoformat(approval_data['timestamp'])
            approvals.append(StepApproval(**approval_data))
        
        data['approvals'] = approvals
        data['step_type'] = StepType(data['step_type'])
        data['status'] = StepStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        if data.get('assigned_at'):
            data['assigned_at'] = datetime.fromisoformat(data['assigned_at'])
        if data.get('completed_at'):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        
        return WorkflowStepInstance(**data)