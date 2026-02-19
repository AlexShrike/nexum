# Custom Fields Module

The custom fields module provides a dynamic field system that allows adding custom data fields to any entity without database schema changes. This powerful extension mechanism enables banks to capture additional information specific to their business requirements while maintaining system flexibility and upgradability.

## Overview

The custom fields system enables:

- **Dynamic Field Definitions**: Add new fields to entities without code changes
- **Type-Safe Validation**: Comprehensive validation rules for different field types
- **Flexible Data Types**: Support for text, numbers, dates, currencies, and complex types
- **Entity Extension**: Extend customers, accounts, loans, transactions, and other entities
- **Search and Reporting**: Make custom fields searchable and reportable
- **Data Export**: Include custom fields in all export and reporting functions

## Key Concepts

### Field Types
The system supports various data types:
- **TEXT**: Free-form text with length validation
- **NUMBER**: Integer values with range validation
- **DECIMAL**: Decimal numbers with precision control
- **BOOLEAN**: True/false values
- **DATE**: Date values with range validation
- **DATETIME**: Date and time values
- **ENUM**: Single selection from predefined options
- **MULTI_ENUM**: Multiple selections from predefined options
- **CURRENCY**: Monetary values with currency specification
- **PHONE**: Phone numbers with format validation
- **EMAIL**: Email addresses with format validation
- **URL**: Web addresses with format validation
- **JSON**: Structured data in JSON format

### Entity Types
Custom fields can be added to core entities:
- **CUSTOMER**: Additional customer information and preferences
- **ACCOUNT**: Account-specific attributes and settings
- **LOAN**: Loan characteristics and collateral information
- **CREDIT_LINE**: Credit line terms and conditions
- **TRANSACTION**: Transaction metadata and categorization
- **PRODUCT**: Product features and parameters
- **COLLECTION_CASE**: Collection-specific data and notes

## Core Classes

### FieldDefinition

Defines the structure and validation rules for a custom field:

```python
from core_banking.custom_fields import FieldDefinition, FieldType, EntityType, ValidationRule, ValidationRuleType

# Define a custom risk score field for customers
risk_score_field = FieldDefinition(
    name="risk_score",
    label="Risk Score",
    description="Customer risk assessment score (1-100)",
    field_type=FieldType.NUMBER,
    entity_type=EntityType.CUSTOMER,
    
    # Validation rules
    validation_rules=[
        ValidationRule(
            rule_type=ValidationRuleType.REQUIRED,
            value=True,
            error_message="Risk score is required"
        ),
        ValidationRule(
            rule_type=ValidationRuleType.MIN_VALUE,
            value=1,
            error_message="Risk score must be at least 1"
        ),
        ValidationRule(
            rule_type=ValidationRuleType.MAX_VALUE,
            value=100,
            error_message="Risk score cannot exceed 100"
        )
    ],
    
    # Configuration
    is_required=True,
    is_searchable=True,
    is_reportable=True,
    default_value=50,
    display_order=10,
    group_name="Risk Assessment",
    
    created_by="risk_manager"
)

# Define a loan purpose enum field
loan_purpose_field = FieldDefinition(
    name="loan_purpose",
    label="Loan Purpose",
    description="Primary purpose of the loan",
    field_type=FieldType.ENUM,
    entity_type=EntityType.LOAN,
    
    # Enum values
    enum_values=[
        "home_purchase",
        "home_refinance", 
        "debt_consolidation",
        "auto_purchase",
        "business_expansion",
        "education",
        "other"
    ],
    
    validation_rules=[
        ValidationRule(
            rule_type=ValidationRuleType.REQUIRED,
            value=True,
            error_message="Loan purpose is required"
        )
    ],
    
    is_required=True,
    is_searchable=True,
    is_reportable=True,
    display_order=5,
    group_name="Loan Details"
)
```

### FieldValue

Stores the actual custom field values for entity instances:

```python
from core_banking.custom_fields import FieldValue

@dataclass
class FieldValue(StorageRecord):
    entity_type: str      # "customer", "account", "loan", etc.
    entity_id: str        # ID of the entity instance
    field_name: str       # Name of the custom field
    field_value: Any      # The actual value
    field_type: FieldType # Type for validation and formatting
    
    # Metadata
    created_by: str
    last_modified_by: str
    
    def get_typed_value(self) -> Any:
        """Get value converted to appropriate Python type"""
        
        if self.field_type == FieldType.TEXT:
            return str(self.field_value) if self.field_value else ""
        
        elif self.field_type == FieldType.NUMBER:
            return int(self.field_value) if self.field_value is not None else None
        
        elif self.field_type == FieldType.DECIMAL:
            return Decimal(str(self.field_value)) if self.field_value is not None else None
        
        elif self.field_type == FieldType.BOOLEAN:
            return bool(self.field_value) if self.field_value is not None else None
        
        elif self.field_type == FieldType.DATE:
            if isinstance(self.field_value, str):
                return datetime.fromisoformat(self.field_value).date()
            return self.field_value
        
        elif self.field_type == FieldType.DATETIME:
            if isinstance(self.field_value, str):
                return datetime.fromisoformat(self.field_value)
            return self.field_value
        
        elif self.field_type in [FieldType.ENUM, FieldType.PHONE, FieldType.EMAIL, FieldType.URL]:
            return str(self.field_value) if self.field_value else ""
        
        elif self.field_type == FieldType.MULTI_ENUM:
            if isinstance(self.field_value, str):
                return json.loads(self.field_value)
            return self.field_value or []
        
        elif self.field_type == FieldType.JSON:
            if isinstance(self.field_value, str):
                return json.loads(self.field_value)
            return self.field_value
        
        elif self.field_type == FieldType.CURRENCY:
            if isinstance(self.field_value, dict):
                return Money(
                    Decimal(self.field_value["amount"]),
                    Currency[self.field_value["currency"]]
                )
            return self.field_value
        
        return self.field_value

# Example field values
customer_risk_score = FieldValue(
    entity_type="customer",
    entity_id="cust_123456",
    field_name="risk_score",
    field_value=75,
    field_type=FieldType.NUMBER,
    created_by="risk_analyst"
)

loan_purpose_value = FieldValue(
    entity_type="loan",
    entity_id="loan_789012",
    field_name="loan_purpose",
    field_value="debt_consolidation",
    field_type=FieldType.ENUM,
    created_by="loan_officer"
)
```

## Custom Field Management

### CustomFieldManager

Main interface for managing custom fields:

```python
from core_banking.custom_fields import CustomFieldManager

class CustomFieldManager:
    def __init__(self, storage: StorageInterface, audit_trail: AuditTrail):
        self.storage = storage
        self.audit = audit_trail
    
    def create_field_definition(self, definition: FieldDefinition) -> str:
        """Create new custom field definition"""
        
        # Validate field definition
        self._validate_field_definition(definition)
        
        # Check for name conflicts
        existing = self.get_field_definition_by_name(
            definition.entity_type,
            definition.name
        )
        
        if existing:
            raise ValueError(f"Field '{definition.name}' already exists for entity type '{definition.entity_type}'")
        
        # Create the definition
        definition.id = str(uuid.uuid4())
        definition.created_at = datetime.now(timezone.utc)
        
        self.storage.store(definition)
        
        # Log creation
        self.audit.log_event(
            AuditEventType.CUSTOM_FIELD_CREATED,
            entity_id=definition.id,
            details={
                "field_name": definition.name,
                "entity_type": definition.entity_type.value,
                "field_type": definition.field_type.value
            }
        )
        
        return definition.id
    
    def set_field_value(
        self,
        entity_type: str,
        entity_id: str,
        field_name: str,
        value: Any,
        user_id: str
    ) -> FieldValue:
        """Set custom field value for an entity"""
        
        # Get field definition
        definition = self.get_field_definition_by_name(entity_type, field_name)
        if not definition:
            raise ValueError(f"Custom field '{field_name}' not found for entity type '{entity_type}'")
        
        if not definition.is_active:
            raise ValueError(f"Custom field '{field_name}' is not active")
        
        # Validate value
        validation_result = self._validate_field_value(definition, value)
        if not validation_result.is_valid:
            raise ValueError(f"Validation failed: {'; '.join(validation_result.errors)}")
        
        # Check if value already exists
        existing_value = self.get_field_value(entity_type, entity_id, field_name)
        
        if existing_value:
            # Update existing value
            existing_value.field_value = value
            existing_value.last_modified_by = user_id
            existing_value.updated_at = datetime.now(timezone.utc)
            
            self.storage.update(existing_value.id, existing_value)
            field_value = existing_value
        else:
            # Create new value
            field_value = FieldValue(
                entity_type=entity_type,
                entity_id=entity_id,
                field_name=field_name,
                field_value=value,
                field_type=definition.field_type,
                created_by=user_id,
                last_modified_by=user_id
            )
            
            self.storage.store(field_value)
        
        # Log value change
        self.audit.log_event(
            AuditEventType.CUSTOM_FIELD_VALUE_SET,
            entity_id=field_value.id,
            user_id=user_id,
            details={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "field_name": field_name,
                "new_value": str(value)
            }
        )
        
        return field_value
```

## Field Validation

### Comprehensive Validation System

```python
class FieldValidator:
    """Validate custom field values against their definitions"""
    
    def validate_field_value(
        self,
        definition: FieldDefinition,
        value: Any
    ) -> ValidationResult:
        """Validate a field value against its definition"""
        
        errors = []
        
        # Check required fields
        if definition.is_required and (value is None or value == ""):
            errors.append(f"Field '{definition.label}' is required")
            return ValidationResult(False, errors)
        
        # Skip validation for empty optional fields
        if value is None or value == "":
            return ValidationResult(True, [])
        
        # Type-specific validation
        if definition.field_type == FieldType.TEXT:
            errors.extend(self._validate_text_field(definition, value))
        
        elif definition.field_type == FieldType.NUMBER:
            errors.extend(self._validate_number_field(definition, value))
        
        elif definition.field_type == FieldType.DECIMAL:
            errors.extend(self._validate_decimal_field(definition, value))
        
        elif definition.field_type == FieldType.EMAIL:
            errors.extend(self._validate_email_field(definition, value))
        
        elif definition.field_type == FieldType.PHONE:
            errors.extend(self._validate_phone_field(definition, value))
        
        elif definition.field_type == FieldType.URL:
            errors.extend(self._validate_url_field(definition, value))
        
        elif definition.field_type == FieldType.ENUM:
            errors.extend(self._validate_enum_field(definition, value))
        
        elif definition.field_type == FieldType.MULTI_ENUM:
            errors.extend(self._validate_multi_enum_field(definition, value))
        
        elif definition.field_type == FieldType.DATE:
            errors.extend(self._validate_date_field(definition, value))
        
        elif definition.field_type == FieldType.CURRENCY:
            errors.extend(self._validate_currency_field(definition, value))
        
        # Apply custom validation rules
        for rule in definition.validation_rules:
            rule_errors = self._apply_validation_rule(rule, value)
            errors.extend(rule_errors)
        
        return ValidationResult(len(errors) == 0, errors)
    
    def _validate_text_field(self, definition: FieldDefinition, value: Any) -> List[str]:
        """Validate text field"""
        errors = []
        
        if not isinstance(value, str):
            errors.append("Value must be text")
            return errors
        
        # Check length constraints from validation rules
        for rule in definition.validation_rules:
            if rule.rule_type == ValidationRuleType.MIN_LENGTH:
                if len(value) < rule.value:
                    errors.append(rule.error_message)
            
            elif rule.rule_type == ValidationRuleType.MAX_LENGTH:
                if len(value) > rule.value:
                    errors.append(rule.error_message)
            
            elif rule.rule_type == ValidationRuleType.REGEX:
                if not re.match(rule.value, value):
                    errors.append(rule.error_message)
        
        return errors
    
    def _validate_number_field(self, definition: FieldDefinition, value: Any) -> List[str]:
        """Validate numeric field"""
        errors = []
        
        try:
            numeric_value = int(value)
        except (ValueError, TypeError):
            errors.append("Value must be a number")
            return errors
        
        # Check range constraints
        for rule in definition.validation_rules:
            if rule.rule_type == ValidationRuleType.MIN_VALUE:
                if numeric_value < rule.value:
                    errors.append(rule.error_message)
            
            elif rule.rule_type == ValidationRuleType.MAX_VALUE:
                if numeric_value > rule.value:
                    errors.append(rule.error_message)
        
        return errors
    
    def _validate_email_field(self, definition: FieldDefinition, value: Any) -> List[str]:
        """Validate email field"""
        errors = []
        
        if not isinstance(value, str):
            errors.append("Email must be text")
            return errors
        
        # Basic email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, value):
            errors.append("Invalid email format")
        
        return errors
    
    def _validate_phone_field(self, definition: FieldDefinition, value: Any) -> List[str]:
        """Validate phone field"""
        errors = []
        
        if not isinstance(value, str):
            errors.append("Phone number must be text")
            return errors
        
        # Remove common phone number characters for validation
        cleaned_phone = re.sub(r'[^\d]', '', value)
        
        # Check length (allowing for international numbers)
        if len(cleaned_phone) < 10 or len(cleaned_phone) > 15:
            errors.append("Phone number must be 10-15 digits")
        
        return errors
    
    def _validate_enum_field(self, definition: FieldDefinition, value: Any) -> List[str]:
        """Validate enum field"""
        errors = []
        
        if value not in definition.enum_values:
            errors.append(f"Value must be one of: {', '.join(definition.enum_values)}")
        
        return errors
    
    def _validate_currency_field(self, definition: FieldDefinition, value: Any) -> List[str]:
        """Validate currency field"""
        errors = []
        
        if isinstance(value, dict):
            # Expecting {"amount": "123.45", "currency": "USD"}
            if "amount" not in value or "currency" not in value:
                errors.append("Currency field must have 'amount' and 'currency' properties")
            else:
                try:
                    Decimal(str(value["amount"]))
                except (ValueError, TypeError):
                    errors.append("Currency amount must be a valid decimal")
                
                if value["currency"] not in [c.value for c in Currency]:
                    errors.append(f"Invalid currency code: {value['currency']}")
        
        elif isinstance(value, Money):
            # Already a Money object, validation passed
            pass
        
        else:
            errors.append("Currency field must be a Money object or dict with amount/currency")
        
        return errors
```

## Field Operations

### Bulk Operations and Management

```python
def set_multiple_field_values(
    self,
    entity_type: str,
    entity_id: str,
    field_values: Dict[str, Any],
    user_id: str
) -> List[FieldValue]:
    """Set multiple custom field values at once"""
    
    results = []
    errors = []
    
    for field_name, value in field_values.items():
        try:
            field_value = self.set_field_value(
                entity_type, entity_id, field_name, value, user_id
            )
            results.append(field_value)
        except Exception as e:
            errors.append(f"Failed to set {field_name}: {str(e)}")
    
    if errors:
        raise ValueError(f"Some fields failed to update: {'; '.join(errors)}")
    
    return results

def get_all_field_values(
    self,
    entity_type: str,
    entity_id: str
) -> Dict[str, Any]:
    """Get all custom field values for an entity"""
    
    field_values = self.storage.query({
        "entity_type": entity_type,
        "entity_id": entity_id
    })
    
    result = {}
    
    for field_value in field_values:
        result[field_value.field_name] = field_value.get_typed_value()
    
    return result

def copy_field_values(
    self,
    from_entity_type: str,
    from_entity_id: str,
    to_entity_type: str,
    to_entity_id: str,
    field_names: List[str] = None,
    user_id: str = "system"
) -> List[FieldValue]:
    """Copy custom field values between entities"""
    
    # Get source field values
    source_values = self.get_all_field_values(from_entity_type, from_entity_id)
    
    # Filter by field names if specified
    if field_names:
        source_values = {k: v for k, v in source_values.items() if k in field_names}
    
    # Set values on target entity
    return self.set_multiple_field_values(
        to_entity_type, to_entity_id, source_values, user_id
    )
```

## Search and Query

### Custom Field Search Capabilities

```python
def search_entities_by_custom_fields(
    self,
    entity_type: str,
    search_criteria: Dict[str, Any]
) -> List[str]:
    """Search entities based on custom field values"""
    
    # Build search query
    query_conditions = []
    
    for field_name, criteria in search_criteria.items():
        # Get field definition to understand data type
        field_def = self.get_field_definition_by_name(entity_type, field_name)
        if not field_def or not field_def.is_searchable:
            continue
        
        # Build condition based on criteria
        if isinstance(criteria, dict):
            # Range or complex criteria
            if "min" in criteria or "max" in criteria:
                # Numeric range search
                if "min" in criteria:
                    query_conditions.append({
                        "field_name": field_name,
                        "field_value_gte": criteria["min"]
                    })
                
                if "max" in criteria:
                    query_conditions.append({
                        "field_name": field_name,
                        "field_value_lte": criteria["max"]
                    })
            
            elif "contains" in criteria:
                # Text search
                query_conditions.append({
                    "field_name": field_name,
                    "field_value_contains": criteria["contains"]
                })
            
            elif "in" in criteria:
                # Multiple values
                query_conditions.append({
                    "field_name": field_name,
                    "field_value_in": criteria["in"]
                })
        
        else:
            # Exact match
            query_conditions.append({
                "field_name": field_name,
                "field_value": criteria
            })
    
    # Execute search
    matching_values = []
    
    for condition in query_conditions:
        field_values = self.storage.query(condition)
        matching_values.extend(field_values)
    
    # Extract unique entity IDs
    entity_ids = list(set(fv.entity_id for fv in matching_values))
    
    return entity_ids

# Example searches
# Find customers with risk score between 70-90
high_risk_customers = custom_field_manager.search_entities_by_custom_fields(
    entity_type="customer",
    search_criteria={
        "risk_score": {"min": 70, "max": 90}
    }
)

# Find loans for debt consolidation
debt_consolidation_loans = custom_field_manager.search_entities_by_custom_fields(
    entity_type="loan", 
    search_criteria={
        "loan_purpose": "debt_consolidation"
    }
)

# Find customers with email containing "@gmail.com"
gmail_customers = custom_field_manager.search_entities_by_custom_fields(
    entity_type="customer",
    search_criteria={
        "alternate_email": {"contains": "@gmail.com"}
    }
)
```

## Integration with Core Entities

### Extending Core Banking Entities

```python
class EnhancedCustomer:
    """Customer class extended with custom fields"""
    
    def __init__(self, customer: Customer, custom_field_manager: CustomFieldManager):
        self.customer = customer
        self.custom_field_manager = custom_field_manager
    
    def get_custom_field(self, field_name: str) -> Any:
        """Get custom field value"""
        field_value = self.custom_field_manager.get_field_value(
            "customer", self.customer.id, field_name
        )
        
        return field_value.get_typed_value() if field_value else None
    
    def set_custom_field(self, field_name: str, value: Any, user_id: str) -> None:
        """Set custom field value"""
        self.custom_field_manager.set_field_value(
            "customer", self.customer.id, field_name, value, user_id
        )
    
    def get_all_custom_fields(self) -> Dict[str, Any]:
        """Get all custom field values"""
        return self.custom_field_manager.get_all_field_values(
            "customer", self.customer.id
        )
    
    @property
    def risk_score(self) -> Optional[int]:
        """Get customer risk score (custom field)"""
        return self.get_custom_field("risk_score")
    
    @risk_score.setter
    def risk_score(self, value: int, user_id: str = "system"):
        """Set customer risk score"""
        self.set_custom_field("risk_score", value, user_id)

# Usage example
enhanced_customer = EnhancedCustomer(customer, custom_field_manager)

# Get custom field value
risk_score = enhanced_customer.risk_score
print(f"Customer risk score: {risk_score}")

# Set custom field value
enhanced_customer.risk_score = 85

# Get all custom fields
all_custom_data = enhanced_customer.get_all_custom_fields()
```

## Export and Reporting Integration

### Including Custom Fields in Reports

```python
def export_entities_with_custom_fields(
    self,
    entity_type: str,
    entity_ids: List[str] = None,
    include_inactive_fields: bool = False,
    format: str = "csv"
) -> str:
    """Export entities with their custom field values"""
    
    # Get field definitions for entity type
    field_definitions = self.get_field_definitions_for_entity(
        entity_type, include_inactive=include_inactive_fields
    )
    
    # Get entities to export
    if entity_ids:
        entities = [self._get_entity(entity_type, eid) for eid in entity_ids]
    else:
        entities = self._get_all_entities(entity_type)
    
    # Build export data
    export_data = []
    
    for entity in entities:
        row = self._entity_to_dict(entity)  # Core entity fields
        
        # Add custom field values
        custom_values = self.get_all_field_values(entity_type, entity.id)
        
        for field_def in field_definitions:
            field_name = field_def.name
            field_value = custom_values.get(field_name)
            
            # Format value for export
            if field_value is not None:
                if field_def.field_type == FieldType.CURRENCY:
                    row[field_def.label] = f"{field_value.amount} {field_value.currency.code}"
                elif field_def.field_type == FieldType.MULTI_ENUM:
                    row[field_def.label] = ", ".join(field_value) if field_value else ""
                elif field_def.field_type == FieldType.JSON:
                    row[field_def.label] = json.dumps(field_value)
                else:
                    row[field_def.label] = str(field_value)
            else:
                row[field_def.label] = ""
        
        export_data.append(row)
    
    # Format output
    if format.lower() == "csv":
        return self._format_as_csv(export_data)
    elif format.lower() == "json":
        return json.dumps(export_data, indent=2, default=str)
    else:
        return export_data

def _format_as_csv(self, data: List[Dict[str, Any]]) -> str:
    """Format data as CSV"""
    if not data:
        return ""
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    
    return output.getvalue()
```

## Testing Custom Fields

```python
def test_custom_field_creation():
    """Test creating custom field definitions"""
    
    # Create text field with validation
    field_def = FieldDefinition(
        name="customer_notes",
        label="Customer Notes",
        description="Additional notes about the customer",
        field_type=FieldType.TEXT,
        entity_type=EntityType.CUSTOMER,
        validation_rules=[
            ValidationRule(
                rule_type=ValidationRuleType.MAX_LENGTH,
                value=1000,
                error_message="Notes cannot exceed 1000 characters"
            )
        ]
    )
    
    field_id = custom_field_manager.create_field_definition(field_def)
    assert field_id is not None
    
    # Retrieve and verify
    retrieved_def = custom_field_manager.get_field_definition(field_id)
    assert retrieved_def.name == "customer_notes"
    assert retrieved_def.field_type == FieldType.TEXT

def test_field_value_validation():
    """Test field value validation"""
    
    # Create numeric field with range validation
    field_def = FieldDefinition(
        name="credit_score",
        field_type=FieldType.NUMBER,
        entity_type=EntityType.CUSTOMER,
        validation_rules=[
            ValidationRule(
                rule_type=ValidationRuleType.MIN_VALUE,
                value=300,
                error_message="Credit score minimum is 300"
            ),
            ValidationRule(
                rule_type=ValidationRuleType.MAX_VALUE,
                value=850,
                error_message="Credit score maximum is 850"
            )
        ]
    )
    
    validator = FieldValidator()
    
    # Test valid value
    result = validator.validate_field_value(field_def, 750)
    assert result.is_valid
    
    # Test invalid value (too low)
    result = validator.validate_field_value(field_def, 250)
    assert not result.is_valid
    assert "Credit score minimum is 300" in result.errors
    
    # Test invalid value (too high)
    result = validator.validate_field_value(field_def, 900)
    assert not result.is_valid
    assert "Credit score maximum is 850" in result.errors

def test_enum_field_operations():
    """Test enum field creation and validation"""
    
    # Create enum field for loan purposes
    field_def = FieldDefinition(
        name="loan_purpose",
        field_type=FieldType.ENUM,
        entity_type=EntityType.LOAN,
        enum_values=["auto", "home", "personal", "business"],
        is_required=True
    )
    
    field_id = custom_field_manager.create_field_definition(field_def)
    
    # Test setting valid enum value
    loan_id = "loan_123"
    custom_field_manager.set_field_value(
        "loan", loan_id, "loan_purpose", "auto", "user_123"
    )
    
    # Verify value was set
    field_value = custom_field_manager.get_field_value("loan", loan_id, "loan_purpose")
    assert field_value.field_value == "auto"
    
    # Test setting invalid enum value
    try:
        custom_field_manager.set_field_value(
            "loan", loan_id, "loan_purpose", "invalid_purpose", "user_123"
        )
        assert False, "Should have raised validation error"
    except ValueError as e:
        assert "must be one of" in str(e)

def test_custom_field_search():
    """Test searching entities by custom fields"""
    
    # Create test data
    customers = create_test_customers_with_custom_fields()
    
    # Search by risk score range
    high_risk_customers = custom_field_manager.search_entities_by_custom_fields(
        "customer",
        {"risk_score": {"min": 80, "max": 100}}
    )
    
    assert len(high_risk_customers) > 0
    
    # Search by text field
    vip_customers = custom_field_manager.search_entities_by_custom_fields(
        "customer",
        {"customer_tier": "VIP"}
    )
    
    assert len(vip_customers) > 0

def test_multi_enum_field():
    """Test multi-selection enum fields"""
    
    # Create multi-enum field for account features
    field_def = FieldDefinition(
        name="account_features",
        field_type=FieldType.MULTI_ENUM,
        entity_type=EntityType.ACCOUNT,
        enum_values=["online_banking", "mobile_app", "overdraft_protection", "interest_bearing", "debit_card"]
    )
    
    field_id = custom_field_manager.create_field_definition(field_def)
    
    # Set multiple values
    account_id = "acc_456"
    features = ["online_banking", "mobile_app", "debit_card"]
    
    custom_field_manager.set_field_value(
        "account", account_id, "account_features", features, "user_123"
    )
    
    # Verify values
    field_value = custom_field_manager.get_field_value("account", account_id, "account_features")
    retrieved_features = field_value.get_typed_value()
    
    assert isinstance(retrieved_features, list)
    assert len(retrieved_features) == 3
    assert "online_banking" in retrieved_features
    assert "mobile_app" in retrieved_features
    assert "debit_card" in retrieved_features
```

The custom fields module provides a powerful and flexible system for extending core banking entities with additional data without requiring database schema changes, making the system highly adaptable to specific business requirements while maintaining data integrity and validation.