# Workflows Module

The workflows module provides a comprehensive configurable workflow engine that manages approval chains, customer journeys, and complex business processes. It supports multi-step approvals, parallel processing, auto-approval conditions, SLA management, and escalation handling for various banking operations.

## Overview

The workflow system enables banks to:

- **Define Approval Chains**: Configure multi-step approval processes for loans, account openings, and transactions
- **Manage SLAs**: Track processing times and automatically escalate overdue items
- **Automate Decisions**: Set conditions for automatic approvals based on business rules
- **Handle Parallel Approvals**: Support multiple simultaneous approvers for complex decisions
- **Track Progress**: Monitor workflow status and generate audit trails

## Key Concepts

### Workflow Types
The system supports various pre-defined workflow types:
- **Loan Approval**: Multi-step loan origination and approval
- **Account Opening**: Customer onboarding and account setup
- **KYC Review**: Customer identification verification process
- **Credit Limit Changes**: Approval chain for credit limit modifications
- **Transaction Overrides**: Exception handling for blocked transactions
- **Write-off Approvals**: Bad debt write-off authorization
- **Product Launch**: New banking product approval process

### Step Types
Individual workflow steps can be:
- **APPROVAL**: Decision-making step requiring approval/rejection
- **REVIEW**: Information review without decision requirement
- **DATA_ENTRY**: Data collection or modification step
- **VERIFICATION**: Document or information verification
- **NOTIFICATION**: Automated notification to stakeholders
- **AUTOMATIC_CHECK**: System-driven validation or check
- **ESCALATION**: Automatic escalation to higher authority
- **PARALLEL_APPROVAL**: Multiple simultaneous approvals required

## Core Classes

### WorkflowDefinition

Defines a reusable workflow template:

```python
from core_banking.workflows import WorkflowDefinition, WorkflowType, WorkflowStepDefinition, StepType
from decimal import Decimal

# Define loan approval workflow
loan_workflow = WorkflowDefinition(
    name="Personal Loan Approval",
    description="Multi-step approval process for personal loans",
    workflow_type=WorkflowType.LOAN_APPROVAL,
    steps=[
        WorkflowStepDefinition(
            step_number=1,
            name="Initial Review",
            step_type=StepType.REVIEW,
            required_role="OFFICER",
            sla_hours=24,
            auto_approve_conditions={
                "loan_amount_less_than": 5000.00,
                "customer_tier": "prime"
            },
            can_skip=False
        ),
        WorkflowStepDefinition(
            step_number=2,
            name="Credit Analysis",
            step_type=StepType.APPROVAL,
            required_role="UNDERWRITER",
            required_approvals=1,
            sla_hours=48,
            escalation_role="SENIOR_UNDERWRITER"
        ),
        WorkflowStepDefinition(
            step_number=3,
            name="Manager Approval",
            step_type=StepType.APPROVAL,
            required_role="MANAGER",
            required_approvals=1,
            sla_hours=24,
            auto_approve_conditions={
                "loan_amount_less_than": 25000.00,
                "credit_score_above": 700
            }
        ),
        WorkflowStepDefinition(
            step_number=4,
            name="Final Documentation",
            step_type=StepType.DATA_ENTRY,
            required_role="OFFICER",
            sla_hours=24
        )
    ],
    version="2.1",
    is_active=True,
    created_by="system_admin"
)
```

### WorkflowInstance

Represents a running workflow for a specific entity:

```python
from core_banking.workflows import WorkflowInstance, WorkflowStatus

@dataclass
class WorkflowInstance(StorageRecord):
    definition_id: str
    workflow_type: WorkflowType
    status: WorkflowStatus
    entity_type: str        # "loan", "account", "customer"
    entity_id: str         # ID of the entity being processed
    initiated_by: str      # User who started the workflow
    initiated_at: datetime
    current_step: int = 1
    steps: List[WorkflowStepInstance] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)  # Additional data
    completed_at: Optional[datetime] = None

# Example workflow instance
loan_workflow_instance = WorkflowInstance(
    definition_id="loan_approval_v2.1",
    workflow_type=WorkflowType.LOAN_APPROVAL,
    status=WorkflowStatus.ACTIVE,
    entity_type="loan",
    entity_id="loan_123456",
    initiated_by="loan_officer_john",
    initiated_at=datetime.now(timezone.utc),
    context={
        "loan_amount": 15000.00,
        "customer_id": "cust_789",
        "loan_purpose": "debt_consolidation",
        "requested_term": 36
    }
)
```

### WorkflowStepInstance

Individual step within a running workflow:

```python
from core_banking.workflows import WorkflowStepInstance, StepStatus, StepApproval

@dataclass
class WorkflowStepInstance(StorageRecord):
    step_number: int
    name: str
    step_type: StepType
    status: StepStatus
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    completed_at: Optional[datetime] = None
    decision: Optional[str] = None  # "APPROVED", "REJECTED", etc.
    comments: Optional[str] = None
    approvals: List[StepApproval] = field(default_factory=list)  # For parallel approvals

# Example step instance
step_instance = WorkflowStepInstance(
    step_number=2,
    name="Credit Analysis",
    step_type=StepType.APPROVAL,
    status=StepStatus.IN_PROGRESS,
    assigned_to="underwriter_sarah",
    assigned_at=datetime.now(timezone.utc),
    comments="Reviewing credit history and debt-to-income ratio"
)
```

## Workflow Management

### WorkflowEngine

Main interface for workflow operations:

```python
from core_banking.workflows import WorkflowEngine

class WorkflowEngine:
    def __init__(self, storage: StorageInterface, audit_manager: AuditTrail):
        self.storage = storage
        self.audit = audit_manager
    
    def create_definition(self, definition: WorkflowDefinition) -> str:
        """Create new workflow definition"""
        
        # Validate definition
        self._validate_definition(definition)
        
        # Store definition
        definition.id = str(uuid.uuid4())
        definition.created_at = datetime.now(timezone.utc)
        
        self.storage.store(definition)
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_DEFINITION_CREATED,
            entity_id=definition.id,
            details={
                "name": definition.name,
                "type": definition.workflow_type.value,
                "steps": len(definition.steps)
            }
        )
        
        return definition.id
    
    def start_workflow(
        self,
        definition_id: str,
        entity_type: str,
        entity_id: str,
        initiated_by: str,
        context: Dict[str, Any] = None
    ) -> WorkflowInstance:
        """Start new workflow instance"""
        
        definition = self.get_definition(definition_id)
        if not definition or not definition.is_active:
            raise ValueError("Invalid or inactive workflow definition")
        
        # Create workflow instance
        instance = WorkflowInstance(
            definition_id=definition_id,
            workflow_type=definition.workflow_type,
            status=WorkflowStatus.ACTIVE,
            entity_type=entity_type,
            entity_id=entity_id,
            initiated_by=initiated_by,
            initiated_at=datetime.now(timezone.utc),
            context=context or {}
        )
        
        # Initialize step instances
        for step_def in definition.steps:
            step_instance = WorkflowStepInstance(
                step_number=step_def.step_number,
                name=step_def.name,
                step_type=step_def.step_type,
                status=StepStatus.PENDING if step_def.step_number == 1 else StepStatus.PENDING
            )
            instance.steps.append(step_instance)
        
        # Start first step
        self._advance_to_next_step(instance)
        
        self.storage.store(instance)
        
        return instance
```

## Step Processing

### Approval Handling

```python
def approve_step(
    self,
    instance_id: str,
    step_number: int,
    approver_id: str,
    decision: str,
    comments: str = ""
) -> WorkflowInstance:
    """Process step approval"""
    
    instance = self.get_instance(instance_id)
    if not instance or instance.status != WorkflowStatus.ACTIVE:
        raise ValueError("Invalid or inactive workflow instance")
    
    # Find the step
    step = self._get_step_by_number(instance, step_number)
    if not step:
        raise ValueError(f"Step {step_number} not found")
    
    if step.status != StepStatus.IN_PROGRESS:
        raise ValueError(f"Step {step_number} is not in progress")
    
    # Record the approval
    approval = StepApproval(
        approver=approver_id,
        decision=decision,
        comments=comments,
        timestamp=datetime.now(timezone.utc)
    )
    
    step.approvals.append(approval)
    
    # Check if step is complete
    definition = self.get_definition(instance.definition_id)
    step_def = self._get_step_definition(definition, step_number)
    
    if self._is_step_complete(step, step_def):
        # Determine overall step decision
        approvals = [a.decision for a in step.approvals]
        
        if decision == "REJECTED" or "REJECTED" in approvals:
            step.status = StepStatus.REJECTED
            step.decision = "REJECTED"
            
            # Reject entire workflow
            instance.status = WorkflowStatus.REJECTED
            instance.completed_at = datetime.now(timezone.utc)
            
        else:
            step.status = StepStatus.APPROVED
            step.decision = "APPROVED"
            step.completed_by = approver_id
            step.completed_at = datetime.now(timezone.utc)
            
            # Advance to next step
            self._advance_to_next_step(instance)
    
    self.storage.update(instance_id, instance)
    
    # Log approval
    self.audit.log_event(
        AuditEventType.WORKFLOW_STEP_APPROVED,
        entity_id=instance_id,
        user_id=approver_id,
        details={
            "step_number": step_number,
            "step_name": step.name,
            "decision": decision,
            "entity_type": instance.entity_type,
            "entity_id": instance.entity_id
        }
    )
    
    return instance

def _is_step_complete(self, step: WorkflowStepInstance, step_def: WorkflowStepDefinition) -> bool:
    """Check if step has required number of approvals"""
    
    if step_def.step_type != StepType.APPROVAL and step_def.step_type != StepType.PARALLEL_APPROVAL:
        return len(step.approvals) > 0
    
    approved_count = sum(1 for a in step.approvals if a.decision == "APPROVED")
    rejected_count = sum(1 for a in step.approvals if a.decision == "REJECTED")
    
    # If any rejection, step is complete
    if rejected_count > 0:
        return True
    
    # Check if we have enough approvals
    return approved_count >= step_def.required_approvals
```

### Auto-Approval Logic

```python
def _check_auto_approval(
    self,
    instance: WorkflowInstance,
    step_def: WorkflowStepDefinition
) -> bool:
    """Check if step can be auto-approved based on conditions"""
    
    if not step_def.auto_approve_conditions:
        return False
    
    conditions = step_def.auto_approve_conditions
    context = instance.context
    
    # Check each condition
    for condition, value in conditions.items():
        if condition == "loan_amount_less_than":
            loan_amount = context.get("loan_amount", 0)
            if loan_amount >= value:
                return False
                
        elif condition == "customer_tier":
            customer_tier = context.get("customer_tier", "")
            if customer_tier != value:
                return False
                
        elif condition == "credit_score_above":
            credit_score = context.get("credit_score", 0)
            if credit_score <= value:
                return False
        
        # Add more condition types as needed
    
    return True

def _advance_to_next_step(self, instance: WorkflowInstance) -> None:
    """Advance workflow to next step or complete"""
    
    definition = self.get_definition(instance.definition_id)
    
    # Check if all steps are complete
    completed_steps = [s for s in instance.steps if s.status in [StepStatus.APPROVED, StepStatus.SKIPPED]]
    
    if len(completed_steps) == len(instance.steps):
        # Workflow complete
        instance.status = WorkflowStatus.COMPLETED
        instance.completed_at = datetime.now(timezone.utc)
        return
    
    # Find next pending step
    next_step = None
    for step in instance.steps:
        if step.status == StepStatus.PENDING:
            next_step = step
            break
    
    if not next_step:
        return  # No more steps
    
    # Get step definition
    step_def = self._get_step_definition(definition, next_step.step_number)
    
    # Check for auto-approval
    if self._check_auto_approval(instance, step_def):
        # Auto-approve step
        next_step.status = StepStatus.APPROVED
        next_step.decision = "AUTO_APPROVED"
        next_step.completed_at = datetime.now(timezone.utc)
        next_step.completed_by = "system"
        
        self.audit.log_event(
            AuditEventType.WORKFLOW_STEP_AUTO_APPROVED,
            entity_id=instance.id,
            details={
                "step_number": next_step.step_number,
                "conditions": step_def.auto_approve_conditions
            }
        )
        
        # Continue to next step
        self._advance_to_next_step(instance)
    else:
        # Activate step for manual processing
        next_step.status = StepStatus.IN_PROGRESS
        next_step.assigned_at = datetime.now(timezone.utc)
        
        # Assign to user/role
        assignee = self._find_assignee(step_def.required_role)
        if assignee:
            next_step.assigned_to = assignee
        
        instance.current_step = next_step.step_number
```

## SLA Management

### SLA Monitoring

```python
def check_sla_violations(self) -> List[Dict[str, Any]]:
    """Check for SLA violations across active workflows"""
    
    violations = []
    active_instances = self.get_active_instances()
    
    for instance in active_instances:
        definition = self.get_definition(instance.definition_id)
        
        for step in instance.steps:
            if step.status != StepStatus.IN_PROGRESS:
                continue
            
            step_def = self._get_step_definition(definition, step.step_number)
            if not step_def.sla_hours:
                continue
            
            # Check if SLA is violated
            elapsed_hours = self._calculate_elapsed_hours(step.assigned_at)
            
            if elapsed_hours > step_def.sla_hours:
                violations.append({
                    "instance_id": instance.id,
                    "step_number": step.step_number,
                    "step_name": step.name,
                    "assigned_to": step.assigned_to,
                    "sla_hours": step_def.sla_hours,
                    "elapsed_hours": elapsed_hours,
                    "entity_type": instance.entity_type,
                    "entity_id": instance.entity_id,
                    "escalation_role": step_def.escalation_role
                })
    
    return violations

def escalate_overdue_steps(self) -> List[str]:
    """Escalate overdue workflow steps"""
    
    violations = self.check_sla_violations()
    escalated_instances = []
    
    for violation in violations:
        instance_id = violation["instance_id"]
        step_number = violation["step_number"]
        escalation_role = violation["escalation_role"]
        
        if not escalation_role:
            continue
        
        # Reassign to escalation role
        instance = self.get_instance(instance_id)
        step = self._get_step_by_number(instance, step_number)
        
        old_assignee = step.assigned_to
        new_assignee = self._find_assignee(escalation_role)
        
        step.assigned_to = new_assignee
        step.status = StepStatus.ESCALATED
        
        self.storage.update(instance_id, instance)
        
        # Log escalation
        self.audit.log_event(
            AuditEventType.WORKFLOW_STEP_ESCALATED,
            entity_id=instance_id,
            details={
                "step_number": step_number,
                "old_assignee": old_assignee,
                "new_assignee": new_assignee,
                "sla_hours": violation["sla_hours"],
                "elapsed_hours": violation["elapsed_hours"]
            }
        )
        
        escalated_instances.append(instance_id)
        
        # Send notification
        self._send_escalation_notification(instance, step, violation)
    
    return escalated_instances

def _calculate_elapsed_hours(self, start_time: datetime) -> float:
    """Calculate business hours elapsed since start time"""
    
    # Simplified calculation - in production, would exclude weekends and holidays
    now = datetime.now(timezone.utc)
    elapsed = now - start_time
    return elapsed.total_seconds() / 3600
```

## Parallel Approvals

### Multiple Approver Support

```python
def create_parallel_approval_workflow() -> WorkflowDefinition:
    """Example workflow with parallel approvals"""
    
    return WorkflowDefinition(
        name="High Value Loan Approval",
        description="Parallel approval process for loans over $100k",
        workflow_type=WorkflowType.LOAN_APPROVAL,
        steps=[
            WorkflowStepDefinition(
                step_number=1,
                name="Risk Assessment",
                step_type=StepType.REVIEW,
                required_role="RISK_ANALYST",
                sla_hours=24
            ),
            WorkflowStepDefinition(
                step_number=2,
                name="Parallel Credit Review",
                step_type=StepType.PARALLEL_APPROVAL,
                required_role="SENIOR_UNDERWRITER",
                required_approvals=2,  # Need 2 out of 3 approvals
                sla_hours=48,
                escalation_role="CHIEF_UNDERWRITER"
            ),
            WorkflowStepDefinition(
                step_number=3,
                name="Executive Approval",
                step_type=StepType.APPROVAL,
                required_role="VP_LENDING",
                sla_hours=24
            )
        ]
    )

def assign_parallel_approvers(
    self,
    instance_id: str,
    step_number: int,
    approver_ids: List[str]
) -> None:
    """Assign multiple approvers to a parallel approval step"""
    
    instance = self.get_instance(instance_id)
    step = self._get_step_by_number(instance, step_number)
    
    if step.step_type != StepType.PARALLEL_APPROVAL:
        raise ValueError("Step is not a parallel approval step")
    
    # Create notification for each approver
    for approver_id in approver_ids:
        self._send_approval_request(instance, step, approver_id)
    
    step.assigned_to = ",".join(approver_ids)  # Store comma-separated list
    self.storage.update(instance_id, instance)
```

## Workflow Templates

### Common Workflow Patterns

```python
class WorkflowTemplates:
    """Pre-defined workflow templates for common banking processes"""
    
    @staticmethod
    def loan_origination_workflow() -> WorkflowDefinition:
        """Standard loan origination workflow"""
        
        return WorkflowDefinition(
            name="Standard Loan Origination",
            workflow_type=WorkflowType.LOAN_APPROVAL,
            steps=[
                WorkflowStepDefinition(
                    step_number=1,
                    name="Application Completeness Check",
                    step_type=StepType.VERIFICATION,
                    required_role="LOAN_PROCESSOR",
                    sla_hours=4
                ),
                WorkflowStepDefinition(
                    step_number=2,
                    name="Credit Check",
                    step_type=StepType.AUTOMATIC_CHECK,
                    required_role="SYSTEM",
                    sla_hours=1
                ),
                WorkflowStepDefinition(
                    step_number=3,
                    name="Underwriting Review",
                    step_type=StepType.APPROVAL,
                    required_role="UNDERWRITER",
                    auto_approve_conditions={
                        "credit_score_above": 750,
                        "dti_ratio_below": 0.36,
                        "loan_amount_less_than": 50000
                    },
                    sla_hours=24,
                    escalation_role="SENIOR_UNDERWRITER"
                ),
                WorkflowStepDefinition(
                    step_number=4,
                    name="Final Approval",
                    step_type=StepType.APPROVAL,
                    required_role="MANAGER",
                    sla_hours=24
                )
            ]
        )
    
    @staticmethod
    def account_opening_workflow() -> WorkflowDefinition:
        """Customer account opening workflow"""
        
        return WorkflowDefinition(
            name="Account Opening Process",
            workflow_type=WorkflowType.ACCOUNT_OPENING,
            steps=[
                WorkflowStepDefinition(
                    step_number=1,
                    name="KYC Documentation Review",
                    step_type=StepType.VERIFICATION,
                    required_role="KYC_ANALYST",
                    sla_hours=24
                ),
                WorkflowStepDefinition(
                    step_number=2,
                    name="Compliance Screening",
                    step_type=StepType.AUTOMATIC_CHECK,
                    required_role="SYSTEM",
                    sla_hours=2
                ),
                WorkflowStepDefinition(
                    step_number=3,
                    name="Account Setup Approval",
                    step_type=StepType.APPROVAL,
                    required_role="BRANCH_MANAGER",
                    auto_approve_conditions={
                        "kyc_tier": "tier_2",
                        "risk_score_below": 50
                    },
                    sla_hours=24
                )
            ]
        )
```

## Reporting and Analytics

### Workflow Performance Metrics

```python
def generate_workflow_performance_report(
    self,
    workflow_type: WorkflowType = None,
    date_range: Tuple[datetime, datetime] = None
) -> Dict[str, Any]:
    """Generate workflow performance report"""
    
    instances = self.get_instances_for_reporting(workflow_type, date_range)
    
    report = {
        "total_workflows": len(instances),
        "completed_workflows": len([i for i in instances if i.status == WorkflowStatus.COMPLETED]),
        "rejected_workflows": len([i for i in instances if i.status == WorkflowStatus.REJECTED]),
        "active_workflows": len([i for i in instances if i.status == WorkflowStatus.ACTIVE]),
        "average_processing_time_hours": self._calculate_average_processing_time(instances),
        "sla_compliance_rate": self._calculate_sla_compliance_rate(instances),
        "step_performance": self._analyze_step_performance(instances),
        "bottleneck_analysis": self._identify_bottlenecks(instances)
    }
    
    return report

def _calculate_average_processing_time(self, instances: List[WorkflowInstance]) -> float:
    """Calculate average workflow processing time"""
    
    completed_instances = [i for i in instances if i.completed_at]
    
    if not completed_instances:
        return 0.0
    
    total_hours = 0
    for instance in completed_instances:
        duration = instance.completed_at - instance.initiated_at
        total_hours += duration.total_seconds() / 3600
    
    return total_hours / len(completed_instances)

def _identify_bottlenecks(self, instances: List[WorkflowInstance]) -> List[Dict[str, Any]]:
    """Identify workflow bottlenecks"""
    
    step_times = {}  # step_name -> list of processing times
    
    for instance in instances:
        for step in instance.steps:
            if step.completed_at and step.assigned_at:
                duration = step.completed_at - step.assigned_at
                hours = duration.total_seconds() / 3600
                
                if step.name not in step_times:
                    step_times[step.name] = []
                
                step_times[step.name].append(hours)
    
    # Calculate average time per step
    bottlenecks = []
    for step_name, times in step_times.items():
        avg_time = sum(times) / len(times)
        bottlenecks.append({
            "step_name": step_name,
            "average_hours": avg_time,
            "sample_size": len(times),
            "max_time": max(times),
            "min_time": min(times)
        })
    
    # Sort by average time (descending)
    return sorted(bottlenecks, key=lambda x: x["average_hours"], reverse=True)
```

## Testing Workflow Operations

```python
def test_loan_approval_workflow():
    """Test complete loan approval workflow"""
    
    # Create workflow definition
    definition = WorkflowTemplates.loan_origination_workflow()
    definition_id = workflow_engine.create_definition(definition)
    
    # Start workflow for loan
    instance = workflow_engine.start_workflow(
        definition_id=definition_id,
        entity_type="loan",
        entity_id="loan_12345",
        initiated_by="loan_officer_john",
        context={
            "loan_amount": 35000,
            "credit_score": 780,
            "dti_ratio": 0.32
        }
    )
    
    assert instance.status == WorkflowStatus.ACTIVE
    assert instance.current_step == 1
    
    # Process first step (verification)
    workflow_engine.approve_step(
        instance_id=instance.id,
        step_number=1,
        approver_id="processor_mary",
        decision="APPROVED",
        comments="All documents complete"
    )
    
    # Should advance to step 2 (automatic credit check)
    updated_instance = workflow_engine.get_instance(instance.id)
    assert updated_instance.current_step == 2
    
    # Step 3 should auto-approve based on conditions
    assert updated_instance.current_step == 4  # Skipped to final approval

def test_parallel_approval_workflow():
    """Test workflow with parallel approvals"""
    
    definition = create_parallel_approval_workflow()
    definition_id = workflow_engine.create_definition(definition)
    
    instance = workflow_engine.start_workflow(
        definition_id=definition_id,
        entity_type="loan",
        entity_id="loan_67890",
        initiated_by="loan_officer_jane",
        context={"loan_amount": 150000}
    )
    
    # Skip to parallel approval step
    workflow_engine.approve_step(instance.id, 1, "risk_analyst", "APPROVED")
    
    # Assign multiple approvers to parallel step
    workflow_engine.assign_parallel_approvers(
        instance.id, 
        2, 
        ["underwriter_1", "underwriter_2", "underwriter_3"]
    )
    
    # First approval
    workflow_engine.approve_step(instance.id, 2, "underwriter_1", "APPROVED")
    
    # Step should still be in progress (need 2 approvals)
    updated_instance = workflow_engine.get_instance(instance.id)
    step_2 = workflow_engine._get_step_by_number(updated_instance, 2)
    assert step_2.status == StepStatus.IN_PROGRESS
    
    # Second approval should complete the step
    workflow_engine.approve_step(instance.id, 2, "underwriter_2", "APPROVED")
    
    updated_instance = workflow_engine.get_instance(instance.id)
    step_2 = workflow_engine._get_step_by_number(updated_instance, 2)
    assert step_2.status == StepStatus.APPROVED

def test_sla_monitoring():
    """Test SLA violation detection"""
    
    # Create instance with short SLA
    instance = create_test_workflow_instance_with_short_sla()
    
    # Simulate time passage
    simulate_time_passage(hours=25)
    
    # Check for violations
    violations = workflow_engine.check_sla_violations()
    
    assert len(violations) > 0
    violation = violations[0]
    assert violation["instance_id"] == instance.id
    assert violation["elapsed_hours"] > violation["sla_hours"]
    
    # Test escalation
    escalated = workflow_engine.escalate_overdue_steps()
    assert instance.id in escalated
```

The workflows module provides a powerful and flexible workflow engine that enables banks to model complex approval processes, maintain SLA compliance, and track performance metrics across all business processes.