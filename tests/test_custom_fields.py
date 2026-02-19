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
    
    def test_list_fields_no_filter(self, custom_fields):
        """Test listing all fields"""
        custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        custom_fields.create_field("field2", "Field 2", "Test", FieldType.NUMBER, EntityType.ACCOUNT)
        
        fields = custom_fields.list_fields()
        assert len(fields) == 2
        field_names = [f.name for f in fields]
        assert "field1" in field_names
        assert "field2" in field_names
    
    def test_list_fields_entity_type_filter(self, custom_fields):
        """Test listing fields filtered by entity type"""
        custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        custom_fields.create_field("field2", "Field 2", "Test", FieldType.NUMBER, EntityType.ACCOUNT)
        
        customer_fields = custom_fields.list_fields(entity_type=EntityType.CUSTOMER)
        assert len(customer_fields) == 1
        assert customer_fields[0].name == "field1"
    
    def test_list_fields_group_filter(self, custom_fields):
        """Test listing fields filtered by group"""
        custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER, group_name="Group A")
        custom_fields.create_field("field2", "Field 2", "Test", FieldType.TEXT, EntityType.CUSTOMER, group_name="Group B")
        
        group_a_fields = custom_fields.list_fields(group="Group A")
        assert len(group_a_fields) == 1
        assert group_a_fields[0].name == "field1"
    
    def test_list_fields_active_filter(self, custom_fields):
        """Test listing fields filtered by active status"""
        field1 = custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        custom_fields.create_field("field2", "Field 2", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        # Deactivate field1
        custom_fields.deactivate_field(field1.id)
        
        active_fields = custom_fields.list_fields(is_active=True)
        assert len(active_fields) == 1
        assert active_fields[0].name == "field2"
        
        inactive_fields = custom_fields.list_fields(is_active=False)
        assert len(inactive_fields) == 1
        assert inactive_fields[0].name == "field1"
    
    def test_update_field(self, custom_fields):
        """Test updating field definition"""
        field_def = custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        updated = custom_fields.update_field(
            field_def.id,
            label="Updated Field 1",
            description="Updated description",
            is_required=True
        )
        
        assert updated.label == "Updated Field 1"
        assert updated.description == "Updated description"
        assert updated.is_required is True
    
    def test_update_field_type_with_values_fails(self, custom_fields):
        """Test that updating field type fails when values exist"""
        field_def = custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        # Set a value
        custom_fields.set_value(EntityType.CUSTOMER, "customer123", "field1", "test value")
        
        # Try to change field type
        with pytest.raises(ValueError, match="Cannot change field type"):
            custom_fields.update_field(field_def.id, field_type=FieldType.NUMBER)
    
    def test_activate_deactivate_field(self, custom_fields):
        """Test activating and deactivating fields"""
        field_def = custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        # Deactivate
        deactivated = custom_fields.deactivate_field(field_def.id)
        assert deactivated.is_active is False
        
        # Activate
        activated = custom_fields.activate_field(field_def.id)
        assert activated.is_active is True
    
    def test_delete_field_without_values(self, custom_fields):
        """Test deleting field without values"""
        field_def = custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        success = custom_fields.delete_field(field_def.id)
        assert success is True
        
        # Field should no longer exist
        retrieved = custom_fields.get_field(field_def.id)
        assert retrieved is None
    
    def test_delete_field_with_values_fails(self, custom_fields):
        """Test that deleting field with values fails"""
        field_def = custom_fields.create_field("field1", "Field 1", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        # Set a value
        custom_fields.set_value(EntityType.CUSTOMER, "customer123", "field1", "test value")
        
        # Try to delete
        with pytest.raises(ValueError, match="Cannot delete field with existing values"):
            custom_fields.delete_field(field_def.id)


class TestFieldTypeValidation:
    """Test validation for all field types"""
    
    def test_text_field_validation(self, custom_fields):
        """Test TEXT field validation"""
        field_def = custom_fields.create_field("text_field", "Text Field", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
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
        field_def = custom_fields.create_field("number_field", "Number Field", "Test", FieldType.NUMBER, EntityType.CUSTOMER)
        
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
    
    def test_decimal_field_validation(self, custom_fields):
        """Test DECIMAL field validation"""
        field_def = custom_fields.create_field("decimal_field", "Decimal Field", "Test", FieldType.DECIMAL, EntityType.CUSTOMER)
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, Decimal("123.45"))
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, 123)
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, 123.45)
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "123.45")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "not a decimal")
        assert is_valid is False
        assert "valid decimal" in errors[0]
    
    def test_boolean_field_validation(self, custom_fields):
        """Test BOOLEAN field validation"""
        field_def = custom_fields.create_field("boolean_field", "Boolean Field", "Test", FieldType.BOOLEAN, EntityType.CUSTOMER)
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, True)
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, False)
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "true")
        assert is_valid is False
        assert "must be a boolean" in errors[0]
        
        is_valid, errors = custom_fields.validate_value(field_def, 1)
        assert is_valid is False
        assert "must be a boolean" in errors[0]
    
    def test_date_field_validation(self, custom_fields):
        """Test DATE field validation"""
        field_def = custom_fields.create_field("date_field", "Date Field", "Test", FieldType.DATE, EntityType.CUSTOMER)
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, date(2023, 12, 25))
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "2023-12-25")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "2023/12/25")
        assert is_valid is False
        assert "YYYY-MM-DD format" in errors[0]
        
        is_valid, errors = custom_fields.validate_value(field_def, "invalid-date")
        assert is_valid is False
        assert "YYYY-MM-DD format" in errors[0]
    
    def test_datetime_field_validation(self, custom_fields):
        """Test DATETIME field validation"""
        field_def = custom_fields.create_field("datetime_field", "DateTime Field", "Test", FieldType.DATETIME, EntityType.CUSTOMER)
        
        # Valid values
        now = datetime.now(timezone.utc)
        is_valid, errors = custom_fields.validate_value(field_def, now)
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "2023-12-25T10:30:00Z")
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "2023-12-25T10:30:00+00:00")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "2023-12-25")
        assert is_valid is False
        assert "ISO format" in errors[0]
    
    def test_enum_field_validation(self, custom_fields):
        """Test ENUM field validation"""
        field_def = custom_fields.create_field(
            "enum_field", "Enum Field", "Test", FieldType.ENUM, EntityType.CUSTOMER,
            enum_values=["OPTION_A", "OPTION_B", "OPTION_C"]
        )
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, "OPTION_A")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "OPTION_D")
        assert is_valid is False
        assert "must be one of" in errors[0]
    
    def test_multi_enum_field_validation(self, custom_fields):
        """Test MULTI_ENUM field validation"""
        field_def = custom_fields.create_field(
            "multi_enum_field", "Multi Enum Field", "Test", FieldType.MULTI_ENUM, EntityType.CUSTOMER,
            enum_values=["OPTION_A", "OPTION_B", "OPTION_C"]
        )
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, ["OPTION_A", "OPTION_B"])
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, [])
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "OPTION_A")
        assert is_valid is False
        assert "must be a list" in errors[0]
        
        is_valid, errors = custom_fields.validate_value(field_def, ["OPTION_A", "OPTION_D"])
        assert is_valid is False
        assert "Invalid values" in errors[0]
    
    def test_currency_field_validation(self, custom_fields):
        """Test CURRENCY field validation"""
        field_def = custom_fields.create_field("currency_field", "Currency Field", "Test", FieldType.CURRENCY, EntityType.CUSTOMER)
        
        # Valid values
        usd = Currency.USD
        money = Money(Decimal("123.45"), usd)
        is_valid, errors = custom_fields.validate_value(field_def, money)
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, Decimal("123.45"))
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "123.45")
        assert is_valid is True
        
        # Invalid values - more than 2 decimal places
        is_valid, errors = custom_fields.validate_value(field_def, Decimal("123.456"))
        assert is_valid is False
        assert "2 decimal places" in errors[0]
    
    def test_phone_field_validation(self, custom_fields):
        """Test PHONE field validation"""
        field_def = custom_fields.create_field("phone_field", "Phone Field", "Test", FieldType.PHONE, EntityType.CUSTOMER)
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, "+1-234-567-8900")
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "1234567890")
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "(123) 456-7890")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "123-456-789a")
        assert is_valid is False
        assert "digits, +, -, spaces, and parentheses" in errors[0]
    
    def test_email_field_validation(self, custom_fields):
        """Test EMAIL field validation"""
        field_def = custom_fields.create_field("email_field", "Email Field", "Test", FieldType.EMAIL, EntityType.CUSTOMER)
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, "test@example.com")
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "user.name+tag@domain.com")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "invalid-email")
        assert is_valid is False
        assert "Invalid email format" in errors[0]
        
        is_valid, errors = custom_fields.validate_value(field_def, "@example.com")
        assert is_valid is False
        assert "Invalid email format" in errors[0]
    
    def test_url_field_validation(self, custom_fields):
        """Test URL field validation"""
        field_def = custom_fields.create_field("url_field", "URL Field", "Test", FieldType.URL, EntityType.CUSTOMER)
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, "https://www.example.com")
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "http://example.com/path")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "www.example.com")
        assert is_valid is False
        assert "must start with http://" in errors[0]
        
        is_valid, errors = custom_fields.validate_value(field_def, "ftp://example.com")
        assert is_valid is False
        assert "must start with http://" in errors[0]
    
    def test_json_field_validation(self, custom_fields):
        """Test JSON field validation"""
        field_def = custom_fields.create_field("json_field", "JSON Field", "Test", FieldType.JSON, EntityType.CUSTOMER)
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, {"key": "value"})
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, [1, 2, 3])
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, '{"key": "value"}')
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, '{"invalid": json}')
        assert is_valid is False
        assert "valid JSON" in errors[0]
        
        is_valid, errors = custom_fields.validate_value(field_def, 123)
        assert is_valid is False
        assert "valid JSON" in errors[0]


class TestValidationRules:
    """Test validation rules"""
    
    def test_min_length_validation(self, custom_fields):
        """Test MIN_LENGTH validation rule"""
        validation_rules = [
            ValidationRule(
                rule_type=ValidationRuleType.MIN_LENGTH,
                value=5,
                error_message="Must be at least 5 characters"
            )
        ]
        
        field_def = custom_fields.create_field(
            "text_field", "Text Field", "Test", FieldType.TEXT, EntityType.CUSTOMER,
            validation_rules=validation_rules
        )
        
        # Valid value
        is_valid, errors = custom_fields.validate_value(field_def, "hello")
        assert is_valid is True
        
        # Invalid value
        is_valid, errors = custom_fields.validate_value(field_def, "hi")
        assert is_valid is False
        assert "Must be at least 5 characters" in errors
    
    def test_max_length_validation(self, custom_fields):
        """Test MAX_LENGTH validation rule"""
        validation_rules = [
            ValidationRule(
                rule_type=ValidationRuleType.MAX_LENGTH,
                value=10,
                error_message="Must be at most 10 characters"
            )
        ]
        
        field_def = custom_fields.create_field(
            "text_field", "Text Field", "Test", FieldType.TEXT, EntityType.CUSTOMER,
            validation_rules=validation_rules
        )
        
        # Valid value
        is_valid, errors = custom_fields.validate_value(field_def, "hello")
        assert is_valid is True
        
        # Invalid value
        is_valid, errors = custom_fields.validate_value(field_def, "this is too long")
        assert is_valid is False
        assert "Must be at most 10 characters" in errors
    
    def test_min_value_validation(self, custom_fields):
        """Test MIN_VALUE validation rule"""
        validation_rules = [
            ValidationRule(
                rule_type=ValidationRuleType.MIN_VALUE,
                value=0,
                error_message="Must be at least 0"
            )
        ]
        
        field_def = custom_fields.create_field(
            "number_field", "Number Field", "Test", FieldType.NUMBER, EntityType.CUSTOMER,
            validation_rules=validation_rules
        )
        
        # Valid value
        is_valid, errors = custom_fields.validate_value(field_def, 10)
        assert is_valid is True
        
        # Invalid value
        is_valid, errors = custom_fields.validate_value(field_def, -5)
        assert is_valid is False
        assert "Must be at least 0" in errors
    
    def test_max_value_validation(self, custom_fields):
        """Test MAX_VALUE validation rule"""
        validation_rules = [
            ValidationRule(
                rule_type=ValidationRuleType.MAX_VALUE,
                value=100,
                error_message="Must be at most 100"
            )
        ]
        
        field_def = custom_fields.create_field(
            "number_field", "Number Field", "Test", FieldType.NUMBER, EntityType.CUSTOMER,
            validation_rules=validation_rules
        )
        
        # Valid value
        is_valid, errors = custom_fields.validate_value(field_def, 50)
        assert is_valid is True
        
        # Invalid value
        is_valid, errors = custom_fields.validate_value(field_def, 150)
        assert is_valid is False
        assert "Must be at most 100" in errors
    
    def test_regex_validation(self, custom_fields):
        """Test REGEX validation rule"""
        validation_rules = [
            ValidationRule(
                rule_type=ValidationRuleType.REGEX,
                value=r'^[A-Z]{2,4}$',
                error_message="Must be 2-4 uppercase letters"
            )
        ]
        
        field_def = custom_fields.create_field(
            "code_field", "Code Field", "Test", FieldType.TEXT, EntityType.CUSTOMER,
            validation_rules=validation_rules
        )
        
        # Valid values
        is_valid, errors = custom_fields.validate_value(field_def, "US")
        assert is_valid is True
        
        is_valid, errors = custom_fields.validate_value(field_def, "USA")
        assert is_valid is True
        
        # Invalid values
        is_valid, errors = custom_fields.validate_value(field_def, "us")
        assert is_valid is False
        assert "Must be 2-4 uppercase letters" in errors
        
        is_valid, errors = custom_fields.validate_value(field_def, "TOOLONG")
        assert is_valid is False
        assert "Must be 2-4 uppercase letters" in errors
    
    def test_required_field_validation(self, custom_fields):
        """Test required field validation"""
        field_def = custom_fields.create_field(
            "required_field", "Required Field", "Test", FieldType.TEXT, EntityType.CUSTOMER,
            is_required=True
        )
        
        # Valid value
        is_valid, errors = custom_fields.validate_value(field_def, "hello")
        assert is_valid is True
        
        # Invalid value (None)
        is_valid, errors = custom_fields.validate_value(field_def, None)
        assert is_valid is False
        assert "Field is required" in errors


class TestFieldValueOperations:
    """Test field value operations"""
    
    def test_set_and_get_value(self, custom_fields):
        """Test setting and getting field values"""
        field_def = custom_fields.create_field("notes", "Notes", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
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
            "status", "Status", "Test", FieldType.TEXT, EntityType.CUSTOMER,
            default_value="ACTIVE"
        )
        
        # Get value for entity that has no value set
        value = custom_fields.get_value(EntityType.CUSTOMER, "cust123", "status")
        assert value == "ACTIVE"
    
    def test_get_all_values(self, custom_fields):
        """Test getting all values for an entity"""
        # Create multiple fields
        custom_fields.create_field("notes", "Notes", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        custom_fields.create_field("priority", "Priority", "Test", FieldType.NUMBER, EntityType.CUSTOMER, default_value=1)
        custom_fields.create_field("verified", "Verified", "Test", FieldType.BOOLEAN, EntityType.CUSTOMER)
        
        # Set some values
        custom_fields.set_value(EntityType.CUSTOMER, "cust123", "notes", "Test notes")
        custom_fields.set_value(EntityType.CUSTOMER, "cust123", "verified", True)
        
        # Get all values
        values = custom_fields.get_all_values(EntityType.CUSTOMER, "cust123")
        assert values["notes"] == "Test notes"
        assert values["priority"] == 1  # Default value
        assert values["verified"] is True
    
    def test_delete_value(self, custom_fields):
        """Test deleting field values"""
        field_def = custom_fields.create_field("notes", "Notes", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        # Set value
        custom_fields.set_value(EntityType.CUSTOMER, "cust123", "notes", "Test notes")
        
        # Delete value
        success = custom_fields.delete_value(EntityType.CUSTOMER, "cust123", "notes")
        assert success is True
        
        # Value should be None now
        value = custom_fields.get_value(EntityType.CUSTOMER, "cust123", "notes")
        assert value is None
    
    def test_bulk_set_values(self, custom_fields):
        """Test bulk setting values"""
        # Create multiple fields
        custom_fields.create_field("name", "Name", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        custom_fields.create_field("age", "Age", "Test", FieldType.NUMBER, EntityType.CUSTOMER)
        custom_fields.create_field("verified", "Verified", "Test", FieldType.BOOLEAN, EntityType.CUSTOMER)
        
        # Bulk set values
        values_dict = {
            "name": "John Doe",
            "age": 30,
            "verified": True
        }
        
        results = custom_fields.bulk_set_values(EntityType.CUSTOMER, "cust123", values_dict)
        
        assert len(results) == 3
        assert "name" in results
        assert "age" in results
        assert "verified" in results
        
        # Verify values were set
        assert custom_fields.get_value(EntityType.CUSTOMER, "cust123", "name") == "John Doe"
        assert custom_fields.get_value(EntityType.CUSTOMER, "cust123", "age") == 30
        assert custom_fields.get_value(EntityType.CUSTOMER, "cust123", "verified") is True
    
    def test_bulk_set_values_validation_error(self, custom_fields):
        """Test bulk set with validation errors"""
        # Create field with validation
        custom_fields.create_field("age", "Age", "Test", FieldType.NUMBER, EntityType.CUSTOMER)
        
        # Try to bulk set with invalid value
        values_dict = {
            "age": "not a number"  # Invalid for NUMBER field
        }
        
        with pytest.raises(ValueError, match="Bulk set failed"):
            custom_fields.bulk_set_values(EntityType.CUSTOMER, "cust123", values_dict)
    
    def test_set_value_validation_error(self, custom_fields):
        """Test setting value that fails validation"""
        custom_fields.create_field("email", "Email", "Test", FieldType.EMAIL, EntityType.CUSTOMER)
        
        with pytest.raises(ValueError, match="Validation failed"):
            custom_fields.set_value(EntityType.CUSTOMER, "cust123", "email", "invalid-email")
    
    def test_set_value_inactive_field(self, custom_fields):
        """Test setting value on inactive field fails"""
        field_def = custom_fields.create_field("notes", "Notes", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        # Deactivate field
        custom_fields.deactivate_field(field_def.id)
        
        with pytest.raises(ValueError, match="not active"):
            custom_fields.set_value(EntityType.CUSTOMER, "cust123", "notes", "test value")
    
    def test_update_existing_value(self, custom_fields):
        """Test updating an existing field value"""
        custom_fields.create_field("notes", "Notes", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        # Set initial value
        field_value1 = custom_fields.set_value(EntityType.CUSTOMER, "cust123", "notes", "Initial notes")
        value_id1 = field_value1.id
        
        # Update value
        field_value2 = custom_fields.set_value(EntityType.CUSTOMER, "cust123", "notes", "Updated notes")
        value_id2 = field_value2.id
        
        # Should be the same record ID (update, not create)
        assert value_id1 == value_id2
        
        # Value should be updated
        value = custom_fields.get_value(EntityType.CUSTOMER, "cust123", "notes")
        assert value == "Updated notes"


class TestSearchOperations:
    """Test search and query operations"""
    
    def test_search_entities_by_field_value(self, custom_fields):
        """Test searching entities by field value"""
        custom_fields.create_field("status", "Status", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
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
        custom_fields.create_field("notes", "Notes", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        
        # Set values for some entities
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "notes", "Notes 1")
        custom_fields.set_value(EntityType.CUSTOMER, "cust2", "notes", "Notes 2")
        # cust3 has no notes set
        
        entities_with_notes = custom_fields.get_entities_with_field(EntityType.CUSTOMER, "notes")
        assert len(entities_with_notes) == 2
        assert "cust1" in entities_with_notes
        assert "cust2" in entities_with_notes
        assert "cust3" not in entities_with_notes
    
    def test_validate_all_required_fields(self, custom_fields):
        """Test validating all required fields for an entity"""
        # Create required and optional fields
        custom_fields.create_field("name", "Name", "Test", FieldType.TEXT, EntityType.CUSTOMER, is_required=True)
        custom_fields.create_field("email", "Email", "Test", FieldType.EMAIL, EntityType.CUSTOMER, is_required=True)
        custom_fields.create_field("notes", "Notes", "Test", FieldType.TEXT, EntityType.CUSTOMER, is_required=False)
        
        # Set only some required fields
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "name", "John Doe")
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "notes", "Optional notes")
        
        # Validate - should fail because email is missing
        is_valid, missing_fields = custom_fields.validate_all_required(EntityType.CUSTOMER, "cust1")
        assert is_valid is False
        assert "Email" in missing_fields
        
        # Set email
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "email", "john@example.com")
        
        # Validate again - should pass
        is_valid, missing_fields = custom_fields.validate_all_required(EntityType.CUSTOMER, "cust1")
        assert is_valid is True
        assert len(missing_fields) == 0


class TestExportOperations:
    """Test export operations"""
    
    def test_export_field_data(self, custom_fields):
        """Test exporting field data for reporting"""
        # Create reportable and non-reportable fields
        custom_fields.create_field("name", "Name", "Test", FieldType.TEXT, EntityType.CUSTOMER, is_reportable=True)
        custom_fields.create_field("email", "Email", "Test", FieldType.EMAIL, EntityType.CUSTOMER, is_reportable=True)
        custom_fields.create_field("secret", "Secret", "Test", FieldType.TEXT, EntityType.CUSTOMER, is_reportable=False)
        
        # Set values for multiple entities
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "name", "John Doe")
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "email", "john@example.com")
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "secret", "secret value")
        
        custom_fields.set_value(EntityType.CUSTOMER, "cust2", "name", "Jane Smith")
        custom_fields.set_value(EntityType.CUSTOMER, "cust2", "email", "jane@example.com")
        
        # Export all reportable fields
        export_data = custom_fields.export_field_data(EntityType.CUSTOMER)
        
        assert len(export_data) == 2
        
        # Check first record
        record1 = next(r for r in export_data if r["entity_id"] == "cust1")
        assert record1["name"] == "John Doe"
        assert record1["email"] == "john@example.com"
        assert "secret" not in record1  # Not reportable, so not included
        
        # Check second record
        record2 = next(r for r in export_data if r["entity_id"] == "cust2")
        assert record2["name"] == "Jane Smith"
        assert record2["email"] == "jane@example.com"
    
    def test_export_specific_fields(self, custom_fields):
        """Test exporting specific fields"""
        # Create multiple reportable fields
        custom_fields.create_field("name", "Name", "Test", FieldType.TEXT, EntityType.CUSTOMER, is_reportable=True)
        custom_fields.create_field("email", "Email", "Test", FieldType.EMAIL, EntityType.CUSTOMER, is_reportable=True)
        custom_fields.create_field("phone", "Phone", "Test", FieldType.PHONE, EntityType.CUSTOMER, is_reportable=True)
        
        # Set values
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "name", "John Doe")
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "email", "john@example.com")
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "phone", "123-456-7890")
        
        # Export only specific fields
        export_data = custom_fields.export_field_data(EntityType.CUSTOMER, field_names=["name", "email"])
        
        assert len(export_data) == 1
        record = export_data[0]
        assert record["name"] == "John Doe"
        assert record["email"] == "john@example.com"
        assert "phone" not in record  # Not requested
    
    def test_export_empty_result(self, custom_fields):
        """Test exporting when no data exists"""
        custom_fields.create_field("name", "Name", "Test", FieldType.TEXT, EntityType.CUSTOMER, is_reportable=True)
        
        # No values set
        export_data = custom_fields.export_field_data(EntityType.CUSTOMER)
        assert len(export_data) == 0


class TestMultipleEntityTypes:
    """Test custom fields across multiple entity types"""
    
    def test_same_field_name_different_entities(self, custom_fields):
        """Test same field name for different entity types"""
        # Create "notes" field for both CUSTOMER and ACCOUNT
        custom_fields.create_field("notes", "Customer Notes", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        custom_fields.create_field("notes", "Account Notes", "Test", FieldType.TEXT, EntityType.ACCOUNT)
        
        # Set values for both entity types
        custom_fields.set_value(EntityType.CUSTOMER, "cust1", "notes", "Customer notes")
        custom_fields.set_value(EntityType.ACCOUNT, "acc1", "notes", "Account notes")
        
        # Values should be separate
        customer_notes = custom_fields.get_value(EntityType.CUSTOMER, "cust1", "notes")
        account_notes = custom_fields.get_value(EntityType.ACCOUNT, "acc1", "notes")
        
        assert customer_notes == "Customer notes"
        assert account_notes == "Account notes"
    
    def test_list_fields_by_entity_type(self, custom_fields):
        """Test listing fields filtered by entity type"""
        # Create fields for different entity types
        custom_fields.create_field("customer_field", "Customer Field", "Test", FieldType.TEXT, EntityType.CUSTOMER)
        custom_fields.create_field("account_field", "Account Field", "Test", FieldType.TEXT, EntityType.ACCOUNT)
        custom_fields.create_field("loan_field", "Loan Field", "Test", FieldType.TEXT, EntityType.LOAN)
        
        # Get customer fields only
        customer_fields = custom_fields.list_fields(entity_type=EntityType.CUSTOMER)
        assert len(customer_fields) == 1
        assert customer_fields[0].name == "customer_field"
        
        # Get account fields only
        account_fields = custom_fields.list_fields(entity_type=EntityType.ACCOUNT)
        assert len(account_fields) == 1
        assert account_fields[0].name == "account_field"


class TestDefaultValues:
    """Test default value functionality"""
    
    def test_field_with_valid_default_value(self, custom_fields):
        """Test creating field with valid default value"""
        field_def = custom_fields.create_field(
            "status", "Status", "Test", FieldType.ENUM, EntityType.CUSTOMER,
            enum_values=["ACTIVE", "INACTIVE", "PENDING"],
            default_value="PENDING"
        )
        
        assert field_def.default_value == "PENDING"
    
    def test_field_with_invalid_default_value(self, custom_fields):
        """Test creating field with invalid default value raises error"""
        with pytest.raises(ValueError, match="Invalid default value"):
            custom_fields.create_field(
                "status", "Status", "Test", FieldType.ENUM, EntityType.CUSTOMER,
                enum_values=["ACTIVE", "INACTIVE"],
                default_value="INVALID_STATUS"
            )
    
    def test_get_default_value_when_no_value_set(self, custom_fields):
        """Test that default value is returned when no value is set"""
        custom_fields.create_field(
            "priority", "Priority", "Test", FieldType.NUMBER, EntityType.CUSTOMER,
            default_value=1
        )
        
        # No value set, should return default
        value = custom_fields.get_value(EntityType.CUSTOMER, "cust1", "priority")
        assert value == 1


class TestFieldOrdering:
    """Test field ordering and grouping"""
    
    def test_field_display_order(self, custom_fields):
        """Test fields are ordered by display_order"""
        # Create fields with different display orders
        custom_fields.create_field("field_c", "Field C", "Test", FieldType.TEXT, EntityType.CUSTOMER, display_order=30)
        custom_fields.create_field("field_a", "Field A", "Test", FieldType.TEXT, EntityType.CUSTOMER, display_order=10)
        custom_fields.create_field("field_b", "Field B", "Test", FieldType.TEXT, EntityType.CUSTOMER, display_order=20)
        
        fields = custom_fields.list_fields(entity_type=EntityType.CUSTOMER)
        
        # Should be ordered by display_order
        assert fields[0].name == "field_a"
        assert fields[1].name == "field_b"
        assert fields[2].name == "field_c"
    
    def test_field_alphabetical_order_when_same_display_order(self, custom_fields):
        """Test fields with same display_order are ordered alphabetically"""
        # Create fields with same display order
        custom_fields.create_field("zebra", "Zebra", "Test", FieldType.TEXT, EntityType.CUSTOMER, display_order=10)
        custom_fields.create_field("alpha", "Alpha", "Test", FieldType.TEXT, EntityType.CUSTOMER, display_order=10)
        custom_fields.create_field("beta", "Beta", "Test", FieldType.TEXT, EntityType.CUSTOMER, display_order=10)
        
        fields = custom_fields.list_fields(entity_type=EntityType.CUSTOMER)
        
        # Should be ordered alphabetically by name
        assert fields[0].name == "alpha"
        assert fields[1].name == "beta"
        assert fields[2].name == "zebra"