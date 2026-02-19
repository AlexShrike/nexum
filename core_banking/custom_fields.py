"""
Custom Fields Module

Dynamic field definitions — add custom data fields to any entity without schema changes.
Inspired by Oradian's "Custom Fields" feature.
"""

import json
import re
from decimal import Decimal
from datetime import datetime, timezone, date
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import uuid

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType


class FieldType(Enum):
    """Supported field types"""
    TEXT = "text"
    NUMBER = "number"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ENUM = "enum"
    MULTI_ENUM = "multi_enum"
    CURRENCY = "currency"
    PHONE = "phone"
    EMAIL = "email"
    URL = "url"
    JSON = "json"


class EntityType(Enum):
    """Entity types that can have custom fields"""
    CUSTOMER = "customer"
    ACCOUNT = "account"
    LOAN = "loan"
    CREDIT_LINE = "credit_line"
    TRANSACTION = "transaction"
    PRODUCT = "product"
    COLLECTION_CASE = "collection_case"


class ValidationRuleType(Enum):
    """Validation rule types"""
    REQUIRED = "required"
    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"
    MIN_VALUE = "min_value"
    MAX_VALUE = "max_value"
    REGEX = "regex"
    ENUM_VALUES = "enum_values"
    UNIQUE = "unique"


@dataclass
class ValidationRule:
    """Validation rule for field values"""
    rule_type: ValidationRuleType
    value: Any
    error_message: str
    
    def __post_init__(self):
        if not self.error_message:
            raise ValueError("Error message is required for validation rules")


@dataclass
class FieldDefinition(StorageRecord):
    """Custom field definition"""
    name: str
    label: str
    description: str
    field_type: FieldType
    entity_type: EntityType
    is_required: bool = False
    is_searchable: bool = False
    is_reportable: bool = False
    default_value: Optional[Any] = None
    validation_rules: List[ValidationRule] = field(default_factory=list)
    enum_values: List[str] = field(default_factory=list)
    display_order: int = 0
    group_name: Optional[str] = None
    is_active: bool = True
    created_by: str = "system"
    
    def __post_init__(self):
        # Validate field name
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', self.name):
            raise ValueError("Field name must start with letter and contain only letters, numbers, and underscores")
        
        # Validate enum values for ENUM/MULTI_ENUM types
        if self.field_type in [FieldType.ENUM, FieldType.MULTI_ENUM]:
            if not self.enum_values:
                raise ValueError("ENUM and MULTI_ENUM fields must have enum_values defined")
        
        # Validate default value if provided
        if self.default_value is not None:
            is_valid, errors = self._validate_value(self.default_value)
            if not is_valid:
                raise ValueError(f"Invalid default value: {'; '.join(errors)}")
    
    def _validate_value(self, value: Any) -> tuple[bool, List[str]]:
        """Validate a value against this field definition"""
        errors = []
        
        # Handle None values
        if value is None:
            if self.is_required:
                errors.append("Field is required")
            return len(errors) == 0, errors
        
        # Type-specific validation
        if self.field_type == FieldType.TEXT:
            if not isinstance(value, str):
                errors.append("Value must be a string")
        
        elif self.field_type == FieldType.NUMBER:
            if not isinstance(value, int):
                errors.append("Value must be an integer")
        
        elif self.field_type == FieldType.DECIMAL:
            if not isinstance(value, (Decimal, int, float, str)):
                errors.append("Value must be a valid decimal")
            else:
                try:
                    Decimal(str(value))
                except:
                    errors.append("Value must be a valid decimal")
        
        elif self.field_type == FieldType.BOOLEAN:
            if not isinstance(value, bool):
                errors.append("Value must be a boolean")
        
        elif self.field_type == FieldType.DATE:
            if isinstance(value, str):
                try:
                    datetime.strptime(value, '%Y-%m-%d').date()
                except ValueError:
                    errors.append("Date must be in YYYY-MM-DD format")
            elif not isinstance(value, date):
                errors.append("Value must be a date or date string (YYYY-MM-DD)")
        
        elif self.field_type == FieldType.DATETIME:
            if isinstance(value, str):
                try:
                    datetime.fromisoformat(value.replace('Z', '+00:00'))
                except ValueError:
                    errors.append("DateTime must be in ISO format")
            elif not isinstance(value, datetime):
                errors.append("Value must be a datetime or ISO datetime string")
        
        elif self.field_type == FieldType.ENUM:
            if str(value) not in self.enum_values:
                errors.append(f"Value must be one of: {', '.join(self.enum_values)}")
        
        elif self.field_type == FieldType.MULTI_ENUM:
            if not isinstance(value, list):
                errors.append("Value must be a list")
            else:
                invalid_values = [str(v) for v in value if str(v) not in self.enum_values]
                if invalid_values:
                    errors.append(f"Invalid values: {', '.join(invalid_values)}. Must be from: {', '.join(self.enum_values)}")
        
        elif self.field_type == FieldType.CURRENCY:
            if isinstance(value, Money):
                # Validate 2 decimal places for currency
                if value.amount.as_tuple().exponent < -2:
                    errors.append("Currency values must have at most 2 decimal places")
            elif isinstance(value, (Decimal, int, float, str)):
                try:
                    amount = Decimal(str(value))
                    if amount.as_tuple().exponent < -2:
                        errors.append("Currency values must have at most 2 decimal places")
                except:
                    errors.append("Value must be a valid currency amount")
            else:
                errors.append("Value must be a Money object or valid decimal")
        
        elif self.field_type == FieldType.PHONE:
            phone_str = str(value)
            if not re.match(r'^[\+\-\d\s\(\)]*$', phone_str):
                errors.append("Phone must contain only digits, +, -, spaces, and parentheses")
        
        elif self.field_type == FieldType.EMAIL:
            email_str = str(value)
            if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email_str):
                errors.append("Invalid email format")
        
        elif self.field_type == FieldType.URL:
            url_str = str(value)
            if not url_str.startswith(('http://', 'https://')):
                errors.append("URL must start with http:// or https://")
        
        elif self.field_type == FieldType.JSON:
            if isinstance(value, str):
                try:
                    json.loads(value)
                except json.JSONDecodeError:
                    errors.append("Value must be valid JSON")
            elif not isinstance(value, (dict, list)):
                errors.append("Value must be valid JSON (string, dict, or list)")
        
        # Apply validation rules
        for rule in self.validation_rules:
            rule_errors = self._apply_validation_rule(rule, value)
            errors.extend(rule_errors)
        
        return len(errors) == 0, errors
    
    def _apply_validation_rule(self, rule: ValidationRule, value: Any) -> List[str]:
        """Apply a single validation rule"""
        if value is None:
            return []  # Skip validation rules for None values (handled separately)
        
        errors = []
        
        if rule.rule_type == ValidationRuleType.MIN_LENGTH:
            if len(str(value)) < rule.value:
                errors.append(rule.error_message)
        
        elif rule.rule_type == ValidationRuleType.MAX_LENGTH:
            if len(str(value)) > rule.value:
                errors.append(rule.error_message)
        
        elif rule.rule_type == ValidationRuleType.MIN_VALUE:
            try:
                if Decimal(str(value)) < Decimal(str(rule.value)):
                    errors.append(rule.error_message)
            except:
                pass  # Skip if value is not numeric
        
        elif rule.rule_type == ValidationRuleType.MAX_VALUE:
            try:
                if Decimal(str(value)) > Decimal(str(rule.value)):
                    errors.append(rule.error_message)
            except:
                pass  # Skip if value is not numeric
        
        elif rule.rule_type == ValidationRuleType.REGEX:
            if not re.match(rule.value, str(value)):
                errors.append(rule.error_message)
        
        return errors


@dataclass
class FieldValue(StorageRecord):
    """Custom field value for an entity"""
    field_definition_id: str
    entity_type: EntityType
    entity_id: str
    value: Any
    updated_by: str = "system"
    
    def __post_init__(self):
        if not self.field_definition_id or not self.entity_id:
            raise ValueError("Field definition ID and entity ID are required")


class CustomFieldManager:
    """Manager for custom fields and their values"""
    
    def __init__(self, storage: StorageInterface, audit_manager: Optional[AuditTrail] = None):
        self.storage = storage
        self.audit_manager = audit_manager
        self._field_definitions_table = "field_definitions"
        self._field_values_table = "field_values"
    
    # Field definition management
    
    def create_field(self, name: str, label: str, field_type: FieldType, entity_type: EntityType, **kwargs) -> FieldDefinition:
        """Create a new field definition"""
        field_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        field_def = FieldDefinition(
            id=field_id,
            name=name,
            label=label,
            field_type=field_type,
            entity_type=entity_type,
            created_at=now,
            updated_at=now,
            **kwargs
        )
        
        # Check for duplicate name within entity type
        existing = self.get_field_by_name(name, entity_type)
        if existing:
            raise ValueError(f"Field '{name}' already exists for entity type '{entity_type.value}'")
        
        # Save to storage
        self.storage.save(self._field_definitions_table, field_id, field_def.to_dict())
        
        # Audit log
        if self.audit_manager:
            self.audit_manager.log_event(
                event_type=AuditEventType.COMPLIANCE_CHECK,  # Using existing audit event type
                entity_type="field_definition",
                entity_id=field_id,
                details={"action": "created", "field_name": name, "entity_type": entity_type.value}
            )
        
        return field_def
    
    def get_field(self, field_id: str) -> Optional[FieldDefinition]:
        """Get field definition by ID"""
        data = self.storage.load(self._field_definitions_table, field_id)
        if not data:
            return None
        
        # Convert back to proper types
        data['field_type'] = FieldType(data['field_type'])
        data['entity_type'] = EntityType(data['entity_type'])
        
        # Convert validation rules
        if 'validation_rules' in data:
            validation_rules = []
            for rule_data in data['validation_rules']:
                rule = ValidationRule(
                    rule_type=ValidationRuleType(rule_data['rule_type']),
                    value=rule_data['value'],
                    error_message=rule_data['error_message']
                )
                validation_rules.append(rule)
            data['validation_rules'] = validation_rules
        
        return FieldDefinition(**data)
    
    def get_field_by_name(self, name: str, entity_type: EntityType) -> Optional[FieldDefinition]:
        """Get field definition by name and entity type"""
        filters = {"name": name, "entity_type": entity_type.value}
        records = self.storage.find(self._field_definitions_table, filters)
        
        if not records:
            return None
        
        data = records[0]
        data['field_type'] = FieldType(data['field_type'])
        data['entity_type'] = EntityType(data['entity_type'])
        
        # Convert validation rules
        if 'validation_rules' in data:
            validation_rules = []
            for rule_data in data['validation_rules']:
                rule = ValidationRule(
                    rule_type=ValidationRuleType(rule_data['rule_type']),
                    value=rule_data['value'],
                    error_message=rule_data['error_message']
                )
                validation_rules.append(rule)
            data['validation_rules'] = validation_rules
        
        return FieldDefinition(**data)
    
    def list_fields(self, entity_type: Optional[EntityType] = None, group: Optional[str] = None, 
                   is_active: Optional[bool] = None) -> List[FieldDefinition]:
        """List field definitions with optional filters"""
        filters = {}
        if entity_type:
            filters['entity_type'] = entity_type.value
        if group is not None:
            filters['group_name'] = group
        if is_active is not None:
            filters['is_active'] = is_active
        
        records = self.storage.find(self._field_definitions_table, filters)
        fields = []
        
        for data in records:
            data['field_type'] = FieldType(data['field_type'])
            data['entity_type'] = EntityType(data['entity_type'])
            
            # Convert validation rules
            if 'validation_rules' in data:
                validation_rules = []
                for rule_data in data['validation_rules']:
                    rule = ValidationRule(
                        rule_type=ValidationRuleType(rule_data['rule_type']),
                        value=rule_data['value'],
                        error_message=rule_data['error_message']
                    )
                    validation_rules.append(rule)
                data['validation_rules'] = validation_rules
            
            fields.append(FieldDefinition(**data))
        
        # Sort by display_order and name
        return sorted(fields, key=lambda f: (f.display_order, f.name))
    
    def update_field(self, field_id: str, **kwargs) -> FieldDefinition:
        """Update field definition"""
        field_def = self.get_field(field_id)
        if not field_def:
            raise ValueError(f"Field definition {field_id} not found")
        
        # Check if field_type is being changed and values exist
        if 'field_type' in kwargs and kwargs['field_type'] != field_def.field_type:
            if self._has_field_values(field_id):
                raise ValueError("Cannot change field type when field values exist")
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(field_def, key):
                setattr(field_def, key, value)
        
        field_def.updated_at = datetime.now(timezone.utc)
        
        # Save to storage
        self.storage.save(self._field_definitions_table, field_id, field_def.to_dict())
        
        # Audit log
        if self.audit_manager:
            self.audit_manager.log_event(
                event_type=AuditEventType.COMPLIANCE_CHECK,
                entity_type="field_definition",
                entity_id=field_id,
                details={"action": "updated", "changes": list(kwargs.keys())}
            )
        
        return field_def
    
    def deactivate_field(self, field_id: str) -> FieldDefinition:
        """Deactivate a field definition"""
        return self.update_field(field_id, is_active=False)
    
    def activate_field(self, field_id: str) -> FieldDefinition:
        """Activate a field definition"""
        return self.update_field(field_id, is_active=True)
    
    def delete_field(self, field_id: str) -> bool:
        """Delete field definition (only if no values exist)"""
        field_def = self.get_field(field_id)
        if not field_def:
            return False
        
        if self._has_field_values(field_id):
            raise ValueError("Cannot delete field with existing values")
        
        success = self.storage.delete(self._field_definitions_table, field_id)
        
        # Audit log
        if success and self.audit_manager:
            self.audit_manager.log_event(
                event_type=AuditEventType.COMPLIANCE_CHECK,
                entity_type="field_definition",
                entity_id=field_id,
                details={"action": "deleted", "field_name": field_def.name}
            )
        
        return success
    
    # Field value management
    
    def set_value(self, entity_type: EntityType, entity_id: str, field_name: str, 
                 value: Any, updated_by: str = "system") -> FieldValue:
        """Set a field value for an entity"""
        # Get field definition
        field_def = self.get_field_by_name(field_name, entity_type)
        if not field_def:
            raise ValueError(f"Field '{field_name}' not found for entity type '{entity_type.value}'")
        
        if not field_def.is_active:
            raise ValueError(f"Field '{field_name}' is not active")
        
        # Validate value
        is_valid, errors = field_def._validate_value(value)
        if not is_valid:
            raise ValueError(f"Validation failed: {'; '.join(errors)}")
        
        # Check for existing value
        existing_value = self._get_field_value_record(entity_type, entity_id, field_def.id)
        
        now = datetime.now(timezone.utc)
        
        if existing_value:
            # Update existing value
            existing_value.value = value
            existing_value.updated_at = now
            existing_value.updated_by = updated_by
            field_value = existing_value
        else:
            # Create new value
            value_id = str(uuid.uuid4())
            field_value = FieldValue(
                id=value_id,
                field_definition_id=field_def.id,
                entity_type=entity_type,
                entity_id=entity_id,
                value=value,
                created_at=now,
                updated_at=now,
                updated_by=updated_by
            )
        
        # Save to storage
        self.storage.save(self._field_values_table, field_value.id, field_value.to_dict())
        
        # Audit log
        if self.audit_manager:
            self.audit_manager.log_event(
                event_type=AuditEventType.COMPLIANCE_CHECK,
                entity_type="field_value",
                entity_id=field_value.id,
                details={
                    "action": "set_value",
                    "field_name": field_name,
                    "entity_type": entity_type.value,
                    "entity_id": entity_id,
                    "updated_by": updated_by
                }
            )
        
        return field_value
    
    def get_value(self, entity_type: EntityType, entity_id: str, field_name: str) -> Any:
        """Get field value for an entity (returns default if not set)"""
        field_def = self.get_field_by_name(field_name, entity_type)
        if not field_def:
            raise ValueError(f"Field '{field_name}' not found for entity type '{entity_type.value}'")
        
        field_value = self._get_field_value_record(entity_type, entity_id, field_def.id)
        if field_value:
            return field_value.value
        
        return field_def.default_value
    
    def get_all_values(self, entity_type: EntityType, entity_id: str) -> Dict[str, Any]:
        """Get all field values for an entity"""
        # Get all field definitions for this entity type
        field_defs = self.list_fields(entity_type=entity_type, is_active=True)
        
        result = {}
        for field_def in field_defs:
            value = self.get_value(entity_type, entity_id, field_def.name)
            if value is not None:
                result[field_def.name] = value
        
        return result
    
    def delete_value(self, entity_type: EntityType, entity_id: str, field_name: str) -> bool:
        """Delete field value for an entity"""
        field_def = self.get_field_by_name(field_name, entity_type)
        if not field_def:
            return False
        
        field_value = self._get_field_value_record(entity_type, entity_id, field_def.id)
        if not field_value:
            return False
        
        success = self.storage.delete(self._field_values_table, field_value.id)
        
        # Audit log
        if success and self.audit_manager:
            self.audit_manager.log_event(
                event_type=AuditEventType.COMPLIANCE_CHECK,
                entity_type="field_value",
                entity_id=field_value.id,
                details={
                    "action": "deleted",
                    "field_name": field_name,
                    "entity_type": entity_type.value,
                    "entity_id": entity_id
                }
            )
        
        return success
    
    def bulk_set_values(self, entity_type: EntityType, entity_id: str, 
                       values_dict: Dict[str, Any], updated_by: str = "system") -> Dict[str, FieldValue]:
        """Set multiple field values at once"""
        results = {}
        errors = []
        
        for field_name, value in values_dict.items():
            try:
                field_value = self.set_value(entity_type, entity_id, field_name, value, updated_by)
                results[field_name] = field_value
            except Exception as e:
                errors.append(f"{field_name}: {str(e)}")
        
        if errors:
            raise ValueError(f"Bulk set failed for some fields: {'; '.join(errors)}")
        
        return results
    
    # Search and query operations
    
    def search_entities(self, entity_type: EntityType, field_name: str, value: Any) -> List[str]:
        """Search for entity IDs that have a specific field value"""
        field_def = self.get_field_by_name(field_name, entity_type)
        if not field_def:
            return []
        
        filters = {
            "field_definition_id": field_def.id,
            "entity_type": entity_type.value,
            "value": value
        }
        
        records = self.storage.find(self._field_values_table, filters)
        return [record["entity_id"] for record in records]
    
    def get_entities_with_field(self, entity_type: EntityType, field_name: str) -> List[str]:
        """Get all entity IDs that have this field set (any value)"""
        field_def = self.get_field_by_name(field_name, entity_type)
        if not field_def:
            return []
        
        filters = {
            "field_definition_id": field_def.id,
            "entity_type": entity_type.value
        }
        
        records = self.storage.find(self._field_values_table, filters)
        return list(set(record["entity_id"] for record in records))
    
    # Validation operations
    
    def validate_value(self, field_definition: FieldDefinition, value: Any) -> tuple[bool, List[str]]:
        """Validate a value against a field definition"""
        return field_definition._validate_value(value)
    
    def validate_all_required(self, entity_type: EntityType, entity_id: str) -> tuple[bool, List[str]]:
        """Check that all required fields are set for an entity"""
        required_fields = [f for f in self.list_fields(entity_type=entity_type, is_active=True) if f.is_required]
        missing_fields = []
        
        for field_def in required_fields:
            value = self.get_value(entity_type, entity_id, field_def.name)
            if value is None:
                missing_fields.append(field_def.label or field_def.name)
        
        return len(missing_fields) == 0, missing_fields
    
    # Export operations
    
    def export_field_data(self, entity_type: EntityType, field_names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Export field data for reporting"""
        # Get fields to export
        if field_names:
            field_defs = [self.get_field_by_name(name, entity_type) for name in field_names]
            field_defs = [f for f in field_defs if f and f.is_reportable]
        else:
            field_defs = self.list_fields(entity_type=entity_type, is_active=True)
            field_defs = [f for f in field_defs if f.is_reportable]
        
        if not field_defs:
            return []
        
        # Get all entities with values for these fields
        entity_ids = set()
        for field_def in field_defs:
            entity_ids.update(self.get_entities_with_field(entity_type, field_def.name))
        
        # Build export data
        export_data = []
        for entity_id in entity_ids:
            row = {"entity_id": entity_id, "entity_type": entity_type.value}
            for field_def in field_defs:
                value = self.get_value(entity_type, entity_id, field_def.name)
                row[field_def.name] = value
            export_data.append(row)
        
        return export_data
    
    # Helper methods
    
    def _has_field_values(self, field_definition_id: str) -> bool:
        """Check if a field definition has any values"""
        filters = {"field_definition_id": field_definition_id}
        records = self.storage.find(self._field_values_table, filters)
        return len(records) > 0
    
    def _get_field_value_record(self, entity_type: EntityType, entity_id: str, field_definition_id: str) -> Optional[FieldValue]:
        """Get field value record"""
        filters = {
            "field_definition_id": field_definition_id,
            "entity_type": entity_type.value,
            "entity_id": entity_id
        }
        
        records = self.storage.find(self._field_values_table, filters)
        if not records:
            return None
        
        data = records[0]
        data['entity_type'] = EntityType(data['entity_type'])
        return FieldValue(**data)