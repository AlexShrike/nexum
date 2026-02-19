"""
Test suite for workflow engine module

Tests workflow definitions, instances, step processing, parallel approvals,
auto-approval conditions, SLA management, and all workflow lifecycle operations.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.workflows import (
    WorkflowEngine, WorkflowDefinition, WorkflowStepDefinition, WorkflowInstance,
    WorkflowType, StepType, StepStatus, WorkflowStatus
)


@pytest.fixture
def storage():
    """Create in-memory storage for testing"""
    return InMemoryStorage()


@pytest.fixture
def audit_manager(storage):
    """Create audit manager for testing"""
    return AuditTrail(storage)


@pytest.fixture
def workflow_engine(storage, audit_manager):
    """Create workflow engine for testing"""
    return WorkflowEngine(storage, audit_manager)


@pytest.fixture
def sample_loan_workflow():
    """Create a sample loan approval workflow definition"""
    steps = [
        WorkflowStepDefinition(
            step_number=1,
            name="Initial Review",
            step_type=StepType.REVIEW,
            required_role="loan_officer",
            sla_hours=24,
            auto_approve_conditions={"amount_below": 1000},
            can_skip=False
        ),
        WorkflowStepDefinition(
            step_number=2,
            name="Credit Check",
            step_type=StepType.VERIFICATION,
            required_role="credit_analyst",
            sla_hours=48,
            can_skip=True
        ),
        WorkflowStepDefinition(
            step_number=3,
            name="Manager Approval",
            step_type=StepType.APPROVAL,
            required_role="branch_manager",
            sla_hours=24,
            escalation_role="regional_manager"
        )
    ]
    
    return WorkflowDefinition(
        id="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        name="Loan Approval Process",
        description="Standard loan approval workflow",
        workflow_type=WorkflowType.LOAN_APPROVAL,
        steps=steps,
        version="1.0",
        is_active=True,
        created_by="admin",
        sla_hours=72
    )


@pytest.fixture
def parallel_approval_workflow():
    """Create a workflow with parallel approval step"""
    steps = [
        WorkflowStepDefinition(
            step_number=1,
            name="Document Review",
            step_type=StepType.REVIEW,
            required_role="analyst",
            sla_hours=24
        ),
        WorkflowStepDefinition(
            step_number=2,
            name="Senior Management Approval",
            step_type=StepType.PARALLEL_APPROVAL,
            required_role="senior_manager",
            required_approvals=2,  # 2 out of 3 required
            sla_hours=48
        ),
        WorkflowStepDefinition(
            step_number=3,
            name="Final Processing",
            step_type=StepType.NOTIFICATION,
            required_role="operations",
            sla_hours=12
        )
    ]
    
    return WorkflowDefinition(
        id="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        name="High-Value Transaction Approval",
        description="Parallel approval for high-value transactions",
        workflow_type=WorkflowType.TRANSACTION_OVERRIDE,
        steps=steps,
        version="1.0",
        is_active=True,
        created_by="admin",
        sla_hours=84
    )


class TestWorkflowDefinitions:
    """Test workflow definition management"""
    
    def test_create_workflow_definition(self, workflow_engine, sample_loan_workflow):
        """Test creating a workflow definition"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        assert definition_id is not None
        assert len(definition_id) > 0
        
        # Retrieve and verify
        retrieved = workflow_engine.get_definition(definition_id)
        assert retrieved is not None
        assert retrieved.name == "Loan Approval Process"
        assert retrieved.workflow_type == WorkflowType.LOAN_APPROVAL
        assert len(retrieved.steps) == 3
        assert retrieved.is_active is True
    
    def test_create_definition_validation(self, workflow_engine):
        """Test workflow definition validation"""
        # Empty steps
        with pytest.raises(ValueError, match="must have at least one step"):
            definition = WorkflowDefinition(
                id="",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                name="Invalid Workflow",
                description="No steps",
                workflow_type=WorkflowType.CUSTOM,
                steps=[],
                created_by="admin"
            )
            workflow_engine.create_definition(definition)
        
        # Duplicate step numbers
        with pytest.raises(ValueError, match="Step numbers must be unique"):
            steps = [
                WorkflowStepDefinition(1, "Step 1", StepType.APPROVAL, "role1"),
                WorkflowStepDefinition(1, "Step 2", StepType.APPROVAL, "role2")  # Duplicate
            ]
            definition = WorkflowDefinition(
                id="",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                name="Invalid Workflow",
                description="Duplicate steps",
                workflow_type=WorkflowType.CUSTOM,
                steps=steps,
                created_by="admin"
            )
            workflow_engine.create_definition(definition)
        
        # Non-consecutive step numbers
        with pytest.raises(ValueError, match="Step numbers must be consecutive"):
            steps = [
                WorkflowStepDefinition(1, "Step 1", StepType.APPROVAL, "role1"),
                WorkflowStepDefinition(3, "Step 3", StepType.APPROVAL, "role2")  # Skip 2
            ]
            definition = WorkflowDefinition(
                id="",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                name="Invalid Workflow",
                description="Non-consecutive steps",
                workflow_type=WorkflowType.CUSTOM,
                steps=steps,
                created_by="admin"
            )
            workflow_engine.create_definition(definition)
    
    def test_list_definitions(self, workflow_engine, sample_loan_workflow):
        """Test listing workflow definitions"""
        # Create multiple definitions
        definition_id1 = workflow_engine.create_definition(sample_loan_workflow)
        
        account_workflow = WorkflowDefinition(
            id="",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            name="Account Opening",
            description="Account opening process",
            workflow_type=WorkflowType.ACCOUNT_OPENING,
            steps=[
                WorkflowStepDefinition(1, "KYC Check", StepType.VERIFICATION, "compliance")
            ],
            created_by="admin"
        )
        definition_id2 = workflow_engine.create_definition(account_workflow)
        
        # Test listing all
        all_definitions = workflow_engine.list_definitions()
        assert len(all_definitions) == 2
        
        # Test filtering by type
        loan_definitions = workflow_engine.list_definitions(WorkflowType.LOAN_APPROVAL)
        assert len(loan_definitions) == 1
        assert loan_definitions[0].name == "Loan Approval Process"
        
        account_definitions = workflow_engine.list_definitions(WorkflowType.ACCOUNT_OPENING)
        assert len(account_definitions) == 1
        assert account_definitions[0].name == "Account Opening"
    
    def test_activate_deactivate_definition(self, workflow_engine, sample_loan_workflow):
        """Test activating and deactivating workflow definitions"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Should be active by default
        definition = workflow_engine.get_definition(definition_id)
        assert definition.is_active is True
        
        # Deactivate
        result = workflow_engine.deactivate_definition(definition_id)
        assert result is True
        
        definition = workflow_engine.get_definition(definition_id)
        assert definition.is_active is False
        
        # Reactivate
        result = workflow_engine.activate_definition(definition_id)
        assert result is True
        
        definition = workflow_engine.get_definition(definition_id)
        assert definition.is_active is True
        
        # Test with non-existent definition
        result = workflow_engine.activate_definition("non-existent")
        assert result is False


class TestWorkflowInstances:
    """Test workflow instance management"""
    
    def test_start_workflow(self, workflow_engine, sample_loan_workflow):
        """Test starting a workflow instance"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Start workflow
        context = {"loan_amount": 5000, "customer_id": "CUST001"}
        instance_id = workflow_engine.start_workflow(
            definition_id,
            "loan",
            "LOAN001",
            "loan_officer_1",
            context
        )
        
        assert instance_id is not None
        
        # Retrieve and verify instance
        instance = workflow_engine.get_workflow(instance_id)
        assert instance is not None
        assert instance.definition_id == definition_id
        assert instance.workflow_type == WorkflowType.LOAN_APPROVAL
        assert instance.status == WorkflowStatus.ACTIVE
        assert instance.entity_type == "loan"
        assert instance.entity_id == "LOAN001"
        assert instance.initiated_by == "loan_officer_1"
        assert instance.current_step == 1
        assert instance.context == context
        
        # Check that steps are created
        assert len(instance.steps) == 3
        assert instance.steps[0].status == StepStatus.PENDING
        assert instance.steps[1].status == StepStatus.PENDING
        assert instance.steps[2].status == StepStatus.PENDING
    
    def test_start_workflow_inactive_definition(self, workflow_engine, sample_loan_workflow):
        """Test that inactive definitions cannot start workflows"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        workflow_engine.deactivate_definition(definition_id)
        
        instance_id = workflow_engine.start_workflow(
            definition_id,
            "loan",
            "LOAN001",
            "loan_officer_1"
        )
        
        assert instance_id is None
    
    def test_get_workflows_with_filters(self, workflow_engine, sample_loan_workflow):
        """Test getting workflows with various filters"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Start multiple workflows
        instance_id1 = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "officer1"
        )
        instance_id2 = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN002", "officer2"
        )
        
        # Approve one workflow to completion
        workflow_engine.approve_step(instance_id1, 1, "officer1")
        workflow_engine.approve_step(instance_id1, 2, "analyst1")
        workflow_engine.approve_step(instance_id1, 3, "manager1")
        
        # Test filtering by status
        active_workflows = workflow_engine.get_workflows(status=WorkflowStatus.ACTIVE)
        assert len(active_workflows) == 1
        assert active_workflows[0].id == instance_id2
        
        completed_workflows = workflow_engine.get_workflows(status=WorkflowStatus.COMPLETED)
        assert len(completed_workflows) == 1
        assert completed_workflows[0].id == instance_id1
        
        # Test filtering by workflow type
        loan_workflows = workflow_engine.get_workflows(workflow_type=WorkflowType.LOAN_APPROVAL)
        assert len(loan_workflows) == 2
        
        # Test filtering by entity ID
        specific_workflows = workflow_engine.get_workflows(entity_id="LOAN001")
        assert len(specific_workflows) == 1
        assert specific_workflows[0].id == instance_id1


class TestStepActions:
    """Test workflow step actions"""
    
    def test_assign_step(self, workflow_engine, sample_loan_workflow):
        """Test assigning a step to a user"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Assign first step
        result = workflow_engine.assign_step(instance_id, 1, "loan_officer_1")
        assert result is True
        
        # Verify assignment
        workflow = workflow_engine.get_workflow(instance_id)
        current_step = workflow.steps[0]  # First step
        assert current_step.assigned_to == "loan_officer_1"
        assert current_step.assigned_at is not None
        assert current_step.status == StepStatus.IN_PROGRESS
    
    def test_approve_step_advances_workflow(self, workflow_engine, sample_loan_workflow):
        """Test that approving a step advances the workflow"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Initially on step 1
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 1
        assert workflow.steps[0].status == StepStatus.PENDING
        
        # Approve first step
        result = workflow_engine.approve_step(instance_id, 1, "loan_officer_1", "Approved")
        assert result is True
        
        # Should advance to step 2
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 2
        assert workflow.steps[0].status == StepStatus.APPROVED
        assert workflow.steps[0].decision == "APPROVED"
        assert workflow.steps[0].comments == "Approved"
        assert workflow.steps[1].status == StepStatus.PENDING
    
    def test_reject_step_rejects_workflow(self, workflow_engine, sample_loan_workflow):
        """Test that rejecting a step rejects the entire workflow"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Reject first step
        result = workflow_engine.reject_step(instance_id, 1, "loan_officer_1", "Insufficient credit")
        assert result is True
        
        # Workflow should be rejected
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.status == WorkflowStatus.REJECTED
        assert workflow.completed_at is not None
        assert workflow.steps[0].status == StepStatus.REJECTED
        assert workflow.steps[0].decision == "REJECTED"
        assert workflow.steps[0].comments == "Insufficient credit"
    
    def test_multi_step_approval_chain(self, workflow_engine, sample_loan_workflow):
        """Test a complete multi-step approval chain"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Step 1: Initial Review
        workflow_engine.approve_step(instance_id, 1, "loan_officer_1", "Initial review complete")
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 2
        assert workflow.status == WorkflowStatus.ACTIVE
        
        # Step 2: Credit Check
        workflow_engine.approve_step(instance_id, 2, "credit_analyst_1", "Credit check passed")
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 3
        assert workflow.status == WorkflowStatus.ACTIVE
        
        # Step 3: Manager Approval (final step)
        workflow_engine.approve_step(instance_id, 3, "branch_manager_1", "Final approval")
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.completed_at is not None
        
        # All steps should be approved
        assert all(step.status == StepStatus.APPROVED for step in workflow.steps)
    
    def test_skip_optional_step(self, workflow_engine, sample_loan_workflow):
        """Test skipping an optional step"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Approve first step to get to second step (which is skippable)
        workflow_engine.approve_step(instance_id, 1, "loan_officer_1")
        
        # Skip second step
        result = workflow_engine.skip_step(instance_id, 2, "supervisor", "Customer has existing credit history")
        assert result is True
        
        # Should advance to step 3
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 3
        assert workflow.steps[1].status == StepStatus.SKIPPED
        assert workflow.steps[1].comments == "Customer has existing credit history"
        assert workflow.steps[2].status == StepStatus.PENDING
    
    def test_cannot_skip_non_skippable_step(self, workflow_engine, sample_loan_workflow):
        """Test that non-skippable steps cannot be skipped"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Try to skip first step (not skippable)
        result = workflow_engine.skip_step(instance_id, 1, "supervisor", "Skip attempt")
        assert result is False
        
        # Step should remain pending
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.steps[0].status == StepStatus.PENDING


class TestParallelApproval:
    """Test parallel approval functionality"""
    
    def test_parallel_approval_step(self, workflow_engine, parallel_approval_workflow):
        """Test parallel approval requiring 2 out of 3 approvers"""
        definition_id = workflow_engine.create_definition(parallel_approval_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "transaction", "TXN001", "initiator"
        )
        
        # Complete first step
        workflow_engine.approve_step(instance_id, 1, "analyst_1")
        
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 2
        
        # First approval - not enough yet
        workflow_engine.approve_step(instance_id, 2, "senior_manager_1", "First approval")
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 2  # Still on step 2
        assert workflow.steps[1].status == StepStatus.IN_PROGRESS  # Not yet approved
        assert len(workflow.steps[1].approvals) == 1
        
        # Second approval - should be enough
        workflow_engine.approve_step(instance_id, 2, "senior_manager_2", "Second approval")
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 3  # Should advance
        assert workflow.steps[1].status == StepStatus.APPROVED
        assert len(workflow.steps[1].approvals) == 2
        
        # Check individual approvals
        approvals = workflow.steps[1].approvals
        assert approvals[0].approver == "senior_manager_1"
        assert approvals[0].decision == "APPROVED"
        assert approvals[1].approver == "senior_manager_2"
        assert approvals[1].decision == "APPROVED"


class TestAutoApproval:
    """Test auto-approval functionality"""
    
    def test_auto_approve_conditions_met(self, workflow_engine, sample_loan_workflow):
        """Test auto-approval when conditions are met"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Start workflow with amount below threshold
        context = {"amount_below": 500}  # Below 1000 threshold
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator", context
        )
        
        # Check auto-approval
        result = workflow_engine.check_auto_approvals(instance_id)
        assert result is True
        
        # First step should be auto-approved and workflow advanced
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 2
        assert workflow.steps[0].status == StepStatus.APPROVED
        assert workflow.steps[0].completed_by == "system"
        assert workflow.steps[0].comments == "Auto-approved"
    
    def test_auto_approve_conditions_not_met(self, workflow_engine, sample_loan_workflow):
        """Test no auto-approval when conditions are not met"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Start workflow with amount above threshold
        context = {"amount_below": 2000}  # Above 1000 threshold
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator", context
        )
        
        # Check auto-approval
        result = workflow_engine.check_auto_approvals(instance_id)
        assert result is False
        
        # First step should remain pending
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 1
        assert workflow.steps[0].status == StepStatus.PENDING
    
    def test_auto_approve_missing_context(self, workflow_engine, sample_loan_workflow):
        """Test no auto-approval when required context is missing"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Start workflow without required context
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator", {}
        )
        
        # Check auto-approval
        result = workflow_engine.check_auto_approvals(instance_id)
        assert result is False
        
        # First step should remain pending
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 1
        assert workflow.steps[0].status == StepStatus.PENDING


class TestSLAManagement:
    """Test SLA breach detection and escalation"""
    
    def test_sla_breach_detection(self, workflow_engine, sample_loan_workflow):
        """Test SLA breach detection and escalation"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Manually set initiated time to past to simulate SLA breach
        workflow = workflow_engine.get_workflow(instance_id)
        past_time = datetime.now(timezone.utc) - timedelta(hours=48)  # 2 days ago
        workflow.initiated_at = past_time
        workflow.steps[0].created_at = past_time
        
        # Save the modified workflow back
        data = workflow.to_dict()
        data['workflow_type'] = workflow.workflow_type.value
        data['status'] = workflow.status.value
        data['steps'] = [workflow_engine._step_instance_to_dict(step) for step in workflow.steps]
        workflow_engine.storage.save('workflow_instances', instance_id, data)
        
        # Check for SLA breaches
        breaches = workflow_engine.check_sla_breaches()
        
        assert len(breaches) == 1
        breach = breaches[0]
        assert breach['workflow_id'] == instance_id
        assert breach['step_number'] == 1
        assert breach['sla_hours'] == 24
        assert breach['escalated_to'] is None  # First step has no escalation role
        
        # Step should be marked as timed out
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.steps[0].status == StepStatus.TIMED_OUT
    
    def test_sla_breach_with_escalation(self, workflow_engine, sample_loan_workflow):
        """Test SLA breach with escalation to another role"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Approve steps to get to manager approval (which has escalation)
        workflow_engine.approve_step(instance_id, 1, "officer")
        workflow_engine.approve_step(instance_id, 2, "analyst")
        
        # Manually set time to simulate SLA breach for manager approval step
        workflow = workflow_engine.get_workflow(instance_id)
        past_time = datetime.now(timezone.utc) - timedelta(hours=48)  # 2 days ago
        workflow.steps[2].created_at = past_time  # Third step (manager approval)
        
        # Save the modified workflow back
        data = workflow.to_dict()
        data['workflow_type'] = workflow.workflow_type.value
        data['status'] = workflow.status.value
        data['steps'] = [workflow_engine._step_instance_to_dict(step) for step in workflow.steps]
        workflow_engine.storage.save('workflow_instances', instance_id, data)
        
        # Check for SLA breaches
        breaches = workflow_engine.check_sla_breaches()
        
        assert len(breaches) == 1
        breach = breaches[0]
        assert breach['workflow_id'] == instance_id
        assert breach['step_number'] == 3
        assert breach['escalated_to'] == "regional_manager"
        
        # Step should be escalated
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.steps[2].status == StepStatus.ESCALATED
        assert workflow.steps[2].assigned_to == "regional_manager"


class TestWorkflowControl:
    """Test workflow control operations"""
    
    def test_cancel_workflow(self, workflow_engine, sample_loan_workflow):
        """Test cancelling an active workflow"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Cancel workflow
        result = workflow_engine.cancel_workflow(instance_id, "supervisor", "Customer withdrew application")
        assert result is True
        
        # Workflow should be cancelled
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.status == WorkflowStatus.CANCELLED
        assert workflow.cancelled_at is not None
    
    def test_cannot_cancel_completed_workflow(self, workflow_engine, sample_loan_workflow):
        """Test that completed workflows cannot be cancelled"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Complete workflow
        workflow_engine.approve_step(instance_id, 1, "officer")
        workflow_engine.approve_step(instance_id, 2, "analyst")
        workflow_engine.approve_step(instance_id, 3, "manager")
        
        # Try to cancel completed workflow
        result = workflow_engine.cancel_workflow(instance_id, "supervisor", "Test cancel")
        assert result is False
    
    def test_get_workflow_history(self, workflow_engine, sample_loan_workflow):
        """Test getting workflow history for an entity"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Create multiple workflows for same entity
        instance_id1 = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "officer1"
        )
        instance_id2 = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "officer2"
        )
        
        # Create workflow for different entity
        instance_id3 = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN002", "officer3"
        )
        
        # Get history for LOAN001
        history = workflow_engine.get_workflow_history("loan", "LOAN001")
        assert len(history) == 2
        
        workflow_ids = [w.id for w in history]
        assert instance_id1 in workflow_ids
        assert instance_id2 in workflow_ids
        assert instance_id3 not in workflow_ids


class TestPendingTasks:
    """Test pending task management"""
    
    def test_get_pending_tasks(self, workflow_engine, sample_loan_workflow):
        """Test getting pending tasks"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Start multiple workflows
        instance_id1 = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator1"
        )
        instance_id2 = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN002", "initiator2"
        )
        
        # Get all pending tasks
        tasks = workflow_engine.get_pending_tasks()
        assert len(tasks) == 2
        
        # Both should be for loan officers (first step)
        for task in tasks:
            assert task['step_number'] == 1
            assert task['step_name'] == "Initial Review"
            assert task['required_role'] == "loan_officer"
            assert task['workflow_id'] in [instance_id1, instance_id2]
    
    def test_get_pending_tasks_by_role(self, workflow_engine, sample_loan_workflow):
        """Test getting pending tasks filtered by role"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Approve first step to move to credit analyst role
        workflow_engine.approve_step(instance_id, 1, "loan_officer")
        
        # Get tasks for loan officers (should be none)
        loan_officer_tasks = workflow_engine.get_pending_tasks(role="loan_officer")
        assert len(loan_officer_tasks) == 0
        
        # Get tasks for credit analysts (should be one)
        analyst_tasks = workflow_engine.get_pending_tasks(role="credit_analyst")
        assert len(analyst_tasks) == 1
        assert analyst_tasks[0]['step_name'] == "Credit Check"
        assert analyst_tasks[0]['required_role'] == "credit_analyst"
    
    def test_get_pending_tasks_by_user(self, workflow_engine, sample_loan_workflow):
        """Test getting pending tasks filtered by assigned user"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        # Assign step to specific user
        workflow_engine.assign_step(instance_id, 1, "john_doe")
        
        # Get tasks for assigned user
        user_tasks = workflow_engine.get_pending_tasks(user="john_doe")
        assert len(user_tasks) == 1
        assert user_tasks[0]['assigned_to'] == "john_doe"
        
        # Get tasks for different user
        other_tasks = workflow_engine.get_pending_tasks(user="jane_doe")
        assert len(other_tasks) == 0


class TestWorkflowIntegration:
    """Integration tests for complete workflow scenarios"""
    
    def test_complete_loan_approval_workflow(self, workflow_engine, sample_loan_workflow):
        """Test a complete loan approval workflow from start to finish"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Start loan approval for $5000 loan
        context = {
            "loan_amount": 5000,
            "customer_id": "CUST001",
            "credit_score": 720,
            "requested_term": 36
        }
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "system", context
        )
        
        # Verify initial state
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.status == WorkflowStatus.ACTIVE
        assert workflow.current_step == 1
        
        # Step 1: Initial Review by loan officer
        tasks = workflow_engine.get_pending_tasks(role="loan_officer")
        assert len(tasks) == 1
        
        workflow_engine.assign_step(instance_id, 1, "loan_officer_john")
        workflow_engine.approve_step(instance_id, 1, "loan_officer_john", "Customer meets basic criteria")
        
        # Step 2: Credit Check by analyst
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 2
        
        tasks = workflow_engine.get_pending_tasks(role="credit_analyst")
        assert len(tasks) == 1
        
        workflow_engine.approve_step(instance_id, 2, "analyst_jane", "Credit check passed")
        
        # Step 3: Manager Approval
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.current_step == 3
        
        tasks = workflow_engine.get_pending_tasks(role="branch_manager")
        assert len(tasks) == 1
        
        workflow_engine.approve_step(instance_id, 3, "manager_bob", "Final approval granted")
        
        # Workflow should be completed
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.completed_at is not None
        
        # All steps should be approved
        for step in workflow.steps:
            assert step.status == StepStatus.APPROVED
    
    def test_workflow_with_rejection(self, workflow_engine, sample_loan_workflow):
        """Test workflow that gets rejected at a step"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "system"
        )
        
        # Approve first step
        workflow_engine.approve_step(instance_id, 1, "loan_officer")
        
        # Reject at credit check step
        workflow_engine.reject_step(instance_id, 2, "credit_analyst", "Credit score too low")
        
        # Workflow should be rejected
        workflow = workflow_engine.get_workflow(instance_id)
        assert workflow.status == WorkflowStatus.REJECTED
        assert workflow.completed_at is not None
        
        # First step approved, second rejected, third unchanged
        assert workflow.steps[0].status == StepStatus.APPROVED
        assert workflow.steps[1].status == StepStatus.REJECTED
        assert workflow.steps[2].status == StepStatus.PENDING  # Never reached
    
    def test_cannot_start_workflow_from_inactive_definition(self, workflow_engine, sample_loan_workflow):
        """Test that workflows cannot be started from inactive definitions"""
        definition_id = workflow_engine.create_definition(sample_loan_workflow)
        
        # Deactivate definition
        workflow_engine.deactivate_definition(definition_id)
        
        # Attempt to start workflow
        instance_id = workflow_engine.start_workflow(
            definition_id, "loan", "LOAN001", "initiator"
        )
        
        assert instance_id is None