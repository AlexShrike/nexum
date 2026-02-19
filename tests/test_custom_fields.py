"""
Test suite for custom_fields module

Tests Custom Fields functionality including field definition CRUD operations,
field value management, validation, search capabilities, and export functionality.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, date
import json
import uuid

from core_banking.currency import Money, Currency
from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.custom_fields import (
    CustomFieldManager, FieldDefinition, FieldValue, ValidationRule,
    FieldType, EntityType, ValidationRuleType
)


@pytest.fixture
def storage():
    """In-memory storage for tests"""
    return InMemoryStorage()


@pytest.fixture
def audit_trail(storage):
    """Audit trail for tests"""
    return AuditTrail(storage)


@pytest.fixture
def custom_fields(storage, audit_trail):
    """Custom field manager for tests"""
    return CustomFieldManager(storage, audit_trail)


class TestFieldDefinitionCRUD:
    """Test field definition CRUD operations"""
    
    def test_create_field_basic(self, custom_fields):
        """Test creating a basic field definition"""
        field_def = custom_fields.create_field(
            name="customer_notes",
            label="Customer Notes",
            description="Additional notes about the customer",
            field_type=FieldType.TEXT,
            entity_type=EntityType.CUSTOMER
        )
        
        assert field_def.id is not None
        assert field_def.name == "customer_notes"
        assert field_def.label == "Customer Notes"
        assert field_def.field_type == FieldType.TEXT
        assert field_def.entity_type == EntityType.CUSTOMER
        assert field_def.is_active is True
        assert field_def.is_required is False
    
    def test_create_field_with_options(self, custom_fields):
        """Test creating a field with advanced options"""
        validation_rules = [
            ValidationRule(
                rule_type=ValidationRuleType.MIN_LENGTH,
                value=5,
                error_message="Must be at least 5 characters"
            )
        ]
        
        field_def = custom_fields.create_field(
            name="account_type",
            label="Account Type",
            description="Type of account",
            field_type=FieldType.ENUM,
            entity_type=EntityType.ACCOUNT,
            is_required=True,
            is_searchable=True,
            is_reportable=True,
            enum_values=["SAVINGS", "CHECKING", "BUSINESS"],
            default_value="SAVINGS",
            validation_rules=validation_rules,
            display_order=10,
            group_name="Account Details"
        )
        
        assert field_def.is_required is True
        assert field_def.is_searchable is True
        assert field_def.is_reportable is True
        assert field_def.enum_values == ["SAVINGS", "CHECKING", "BUSINESS"]
        assert field_def.default_value == "SAVINGS"
        assert len(field_def.validation_rules) == 1
        assert field_def.display_order == 10
        assert field_def.group_name == "Account Details"
    
    def test_create_field_duplicate_name(self, custom_fields):
        """Test creating field with duplicate name within entity type"""
        custom_fields.create_field(
            name="test_field",
            label="Test Field",
            description="Test",
            field_type=FieldType.TEXT,
            entity_type=EntityType.CUSTOMER
        )
        
        with pytest.raises(ValueError, match="already exists"):
            custom_fields.create_field(
                name="test_field",
                label="Another Test Field",
                description="Test",
                field_type=FieldType.TEXT,
                entity_type=EntityType.CUSTOMER
            )
    
    def test_create_field_same_name_different_entity(self, custom_fields):
        """Test creating field with same name for different entity types"""
        custom_fields.create_field(
            name="notes",
            label="Customer Notes",
            description="Test",
            field_type=FieldType.TEXT,
            entity_type=EntityType.CUSTOMER
        )
        
        # Should not raise error - same name, different entity type
        custom_fields.create_field(
            name="notes",
            label="Account Notes",
            description="Test",
            field_type=FieldType.TEXT,
            entity_type=EntityType.ACCOUNT
        )
    
    def test_create_enum_field_without_values(self, custom_fields):
        """Test creating ENUM field without enum_values raises error"""
        with pytest.raises(ValueError, match="enum_values"):
            custom_fields.create_field(
                name="bad_enum",
                label="Bad Enum",
                description="Test",
                field_type=FieldType.ENUM,
                entity_type=EntityType.CUSTOMER
            )
    
    def test_create_field_invalid_name(self, custom_fields):
        """Test creating field with invalid name"""
        with pytest.raises(ValueError, match="Field name must start"):
            custom_fields.create_field(
                name="123invalid",
                label="Invalid Name",
                description="Test",
                field_type=FieldType.TEXT,
                entity_type=EntityType.CUSTOMER
            )
    
    def test_get_field_by_id(self, custom_fields):
        """Test getting field by ID"""
        field_def = custom_fields.create_field(
            name="test_field",
            label="Test Field",
            description="Test",
            field_type=FieldType.TEXT,
            entity_type=EntityType.CUSTOMER
        )
        
        retrieved = custom_fields.get_field(field_def.id)
        assert retrieved is not None
        assert retrieved.id == field_def.id
        assert retrieved.name == "test_field"
    
    def test_get_field_by_name(self, custom_fields):
        """Test getting field by name and entity type"""
        custom_fields.create_field(
            name="test_field",
            label="Test Field",
            description="Test",
            field_type=FieldType.TEXT,
            entity_type=EntityType.CUSTOMER
        )
        
        retrieved = custom_fields.get_field_by_name("test_field", EntityType.CUSTOMER)
        assert retrieved is not None
        assert retrieved.name == "test_field"
        assert retrieved.entity_type == EntityType.CUSTOMER


class TestFieldTypeValidation:
    """Test validation for all field types"""
    
    def test_text_field_validation(self, custom_fields):
        """Test TEXT field validation"""
        field_def = custom_fields.create_field(
            name="text_field", 
            label="Text Field", 
            description="Test", 
            field_type=FieldType.TEXT, 
            entity_type=EntityType.CUSTOMER
        )
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, "hello")
        assert is_valid is True
        assert len(errors) == 0
        
        is_valid, errors = custom_fields.validate_value(field_def, "")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, 123)
        assert is_valid is False
        assert "must be a string" in errors[0]
    
    def test_number_field_validation(self, custom_fields):
        """Test NUMBER field validation"""
        field_def = custom_fields.create_field(
            name="number_field", 
            label="Number Field", 
            description="Test", 
            field_type=FieldType.NUMBER, 
            entity_type=EntityType.CUSTOMER
        )
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, 42)
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, 0)
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, 3.14)
        assert is_valid is False
        assert "must be an integer" in errors[0]
        
        is_valid, errors = custom_fields.validate_value(field_def, "not a number")
        assert is_valid is False
        assert "must be an integer" in errors[0]
    
    def test_boolean_field_validation(self, custom_fields):
        """Test BOOLEAN field validation"""
        field_def = custom_fields.create_field(
            name="boolean_field", 
            label="Boolean Field", 
            description="Test", 
            field_type=FieldType.BOOLEAN, 
            entity_type=EntityType.CUSTOMER
        )
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, True)
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, False)
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "true")
        assert is_valid is False
        assert "must be a boolean" in errors[0]
    
    def test_enum_field_validation(self, custom_fields):
        """Test ENUM field validation"""
        field_def = custom_fields.create_field(
            name="enum_field", 
            label="Enum Field", 
            description="Test", 
            field_type=FieldType.ENUM, 
            entity_type=EntityType.CUSTOMER,
            enum_values=["OPTION_A", "OPTION_B", "OPTION_C"]
        )
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, "OPTION_A")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "OPTION_D")
        assert is_valid is False
        assert "must be one of" in errors[0]


class TestFieldValueOperations:
    """Test field value operations"""
    
    def test_set_and_get_value(self, custom_fields):
        """Test setting and getting field values"""
        field_def = custom_fields.create_field(
            name="notes", 
            label="Notes", 
            description="Test", 
            field_type=FieldType.TEXT, 
            entity_type=EntityType.CUSTOMER
        )
        
        # Set value
        field_value = custom_fields.set_value(EntityType.CUSTOMER, "cust123", "notes", "Customer notes here")
        assert field_value.entity_type == EntityType.CUSTOMER
        assert field_value.entity_id == "cust123"
        assert field_value.value == "Customer notes here"
        
        # Get value
        value = custom_fields.get_value(EntityType.CUSTOMER, "cust123", "notes")
        assert value == "Customer notes here"
    
    def test_get_value_with_default(self, custom_fields):
        """Test getting value returns default when not set"""
        field_def = custom_fields.create_field(
            name="status", 
            label="Status", 
            description="Test", 
            field_type=FieldType.TEXT, 
            entity_type=EntityType.CUSTOMER,
            default_value="ACTIVE"
        )
        
        # Get value for entity that has no value set
        value = custom_fields.get_value(EntityType.CUSTOMER, "cust123", "status")
        assert value == "ACTIVE"
    
    def test_delete_value(self, custom_fields):
        """Test deleting field values"""
        field_def = custom_fields.create_field(
            name="notes", 
            label="Notes", 
            description="Test", 
            field_type=FieldType.TEXT, 
            entity_type=EntityType.CUSTOMER
        )
        
        # Set value
        custom_fields.set_value(EntityType.CUSTOMER, "cust123", "notes", "Test notes")
        
        # Delete value
        success = custom_fields.delete_value(EntityType.CUSTOMER, "cust123", "notes")
        assert success is True
        
        # Value should be None now
        value = custom_fields.get_value(EntityType.CUSTOMER, "cust123", "notes")
        assert value is None
    
    def test_set_value_validation_error(self, custom_fields):
        """Test setting value that fails validation"""
        custom_fields.create_field(
            name="email", 
            label="Email", 
            description="Test", 
            field_type=FieldType.EMAIL, 
            entity_type=EntityType.CUSTOMER
        )
        
        with pytest.raises(ValueError, match="Validation failed"):
            custom_fields.set_value(EntityType.CUSTOMER, "cust123", "email", "invalid-email")


class TestSearchOperations:
    """Test search and query operations"""
    
    def test_search_entities_by_field_value(self, custom_fields):
        """Test searching entities by field value"""
        custom_fields.create_field(
            name="status", 
            label="Status", 
            description="Test", 
            field_type=FieldType.TEXT, 
            entity_type=EntityType.CUSTOMER
        )
        
        # Set values for different entities
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "status", "ACTIVE")
        custom_fields.set_value(EntityType.CUSTOMER, "cust2", "status", "INACTIVE")
        custom_fields.set_value(EntityType.CUSTOMER, "cust3", "status", "ACTIVE")
        
        # Search for active customers
        active_customers = custom_fields.search_entities(EntityType.CUSTOMER, "status", "ACTIVE")
        assert len(active_customers) == 2
        assert "cust1" in active_customers
        assert "cust3" in active_customers
        
        # Search for inactive customers
        inactive_customers = custom_fields.search_entities(EntityType.CUSTOMER, "status", "INACTIVE")
        assert len(inactive_customers) == 1
        assert "cust2" in inactive_customers
    
    def test_get_entities_with_field(self, custom_fields):
        """Test getting all entities that have a field set"""
        custom_fields.create_field(
            name="notes", 
            label="Notes", 
            description="Test", 
            field_type=FieldType.TEXT, 
            entity_type=EntityType.CUSTOMER
        )
        
        # Set values for some entities
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "notes", "Notes 1")
        custom_fields.set_value(EntityType.CUSTOMER, "cust2", "notes", "Notes 2")
        # cust3 has no notes set
        
        entities_with_notes = custom_fields.get_entities_with_field(EntityType.CUSTOMER, "notes")
        assert len(entities_with_notes) == 2
        assert "cust1" in entities_with_notes
        assert "cust2" in entities_with_notes
        assert "cust3" not in entities_with_notes