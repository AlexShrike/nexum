"""
Customer Management Module

Manages customer profiles, KYC (Know Your Customer) status, transaction limits
based on KYC tiers, and beneficiary management.
"""

from decimal import Decimal
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid
import re

from .currency import Money, Currency
from .storage import StorageInterface, StorageRecord
from .audit import AuditTrail, AuditEventType


class KYCStatus(Enum):
    """KYC verification status"""
    NONE = "none"           # No KYC submitted
    PENDING = "pending"     # KYC submitted, under review
    VERIFIED = "verified"   # KYC approved
    EXPIRED = "expired"     # KYC verification expired
    REJECTED = "rejected"   # KYC rejected


class KYCTier(Enum):
    """KYC tiers with different limits and privileges"""
    TIER_0 = "tier_0"  # No KYC - very limited
    TIER_1 = "tier_1"  # Basic KYC - moderate limits
    TIER_2 = "tier_2"  # Enhanced KYC - high limits
    TIER_3 = "tier_3"  # Full KYC - highest limits


@dataclass
class KYCLimits:
    """Transaction limits per KYC tier"""
    daily_transaction_limit: Money
    monthly_transaction_limit: Money
    single_transaction_limit: Money
    annual_cumulative_limit: Optional[Money] = None
    
    def __post_init__(self):
        # Ensure all amounts use same currency
        currencies = {
            self.daily_transaction_limit.currency,
            self.monthly_transaction_limit.currency, 
            self.single_transaction_limit.currency
        }
        
        if self.annual_cumulative_limit:
            currencies.add(self.annual_cumulative_limit.currency)
        
        if len(currencies) > 1:
            raise ValueError("All KYC limits must use the same currency")


@dataclass
class Address:
    """Customer address"""
    line1: str
    city: str
    state: str
    postal_code: str
    country: str
    line2: Optional[str] = None
    
    def __post_init__(self):
        # Basic validation
        if not self.line1 or not self.city or not self.state:
            raise ValueError("Address line1, city, and state are required")
        
        # Validate country code (2-letter ISO)
        if not re.match(r'^[A-Z]{2}$', self.country):
            raise ValueError("Country must be 2-letter ISO code (e.g., 'US', 'CA')")


@dataclass
class Beneficiary:
    """Beneficiary for account or customer"""
    name: str
    relationship: str  # e.g., "spouse", "child", "parent", "trust"
    percentage: Decimal  # Percentage of benefit (0-100)
    contact_info: Optional[str] = None
    
    def __post_init__(self):
        if self.percentage < Decimal('0') or self.percentage > Decimal('100'):
            raise ValueError("Beneficiary percentage must be between 0 and 100")


@dataclass
class Customer(StorageRecord):
    """
    Customer profile with KYC status and limits
    """
    first_name: str
    last_name: str
    email: str
    phone: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    address: Optional[Address] = None
    kyc_status: KYCStatus = KYCStatus.NONE
    kyc_tier: KYCTier = KYCTier.TIER_0
    kyc_verified_at: Optional[datetime] = None
    kyc_expires_at: Optional[datetime] = None
    kyc_documents: List[str] = field(default_factory=list)  # Document IDs/references
    tax_id: Optional[str] = None  # SSN, TIN, etc.
    nationality: Optional[str] = None  # 2-letter country code
    beneficiaries: List[Beneficiary] = field(default_factory=list)
    notes: Optional[str] = None
    is_active: bool = True
    
    def __post_init__(self):
        
        # Email validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, self.email):
            raise ValueError("Invalid email format")
        
        # Validate beneficiary percentages sum to <= 100%
        if self.beneficiaries:
            total_percentage = sum(b.percentage for b in self.beneficiaries)
            if total_percentage > Decimal('100'):
                raise ValueError(f"Total beneficiary percentages ({total_percentage}%) exceed 100%")
    
    @property
    def full_name(self) -> str:
        """Get customer's full name"""
        return f"{self.first_name} {self.last_name}"
    
    @property
    def age(self) -> Optional[int]:
        """Calculate customer's age"""
        if not self.date_of_birth:
            return None
        
        today = datetime.now(timezone.utc).date()
        birth_date = self.date_of_birth.date()
        age = today.year - birth_date.year
        
        # Adjust if birthday hasn't occurred this year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1
        
        return age
    
    @property
    def is_kyc_expired(self) -> bool:
        """Check if KYC has expired"""
        if not self.kyc_expires_at:
            return False
        return datetime.now(timezone.utc) > self.kyc_expires_at
    
    @property
    def needs_kyc_renewal(self) -> bool:
        """Check if KYC needs renewal (expires within 30 days)"""
        if not self.kyc_expires_at:
            return False
        
        warning_date = self.kyc_expires_at - timedelta(days=30)
        return datetime.now(timezone.utc) > warning_date
    
    def can_perform_transaction(self, amount: Money) -> bool:
        """Check if customer can perform a transaction based on KYC tier"""
        # Inactive customers cannot transact
        if not self.is_active:
            return False
        
        # Expired KYC customers have restricted access
        if self.is_kyc_expired and self.kyc_status == KYCStatus.VERIFIED:
            return False
        
        # Additional checks can be added here based on business rules
        return True


class CustomerManager:
    """
    Manages customer lifecycle, KYC processes, and tier-based limits
    """
    
    def __init__(self, storage: StorageInterface, audit_trail: AuditTrail):
        self.storage = storage
        self.audit_trail = audit_trail
        self.table_name = "customers"
        
        # Default KYC limits by tier (in USD - adjust for other currencies)
        self._default_kyc_limits = {
            KYCTier.TIER_0: KYCLimits(
                daily_transaction_limit=Money(Decimal('100'), Currency.USD),
                monthly_transaction_limit=Money(Decimal('1000'), Currency.USD),
                single_transaction_limit=Money(Decimal('100'), Currency.USD)
            ),
            KYCTier.TIER_1: KYCLimits(
                daily_transaction_limit=Money(Decimal('1000'), Currency.USD),
                monthly_transaction_limit=Money(Decimal('10000'), Currency.USD),
                single_transaction_limit=Money(Decimal('1000'), Currency.USD),
                annual_cumulative_limit=Money(Decimal('50000'), Currency.USD)
            ),
            KYCTier.TIER_2: KYCLimits(
                daily_transaction_limit=Money(Decimal('10000'), Currency.USD),
                monthly_transaction_limit=Money(Decimal('100000'), Currency.USD),
                single_transaction_limit=Money(Decimal('10000'), Currency.USD),
                annual_cumulative_limit=Money(Decimal('500000'), Currency.USD)
            ),
            KYCTier.TIER_3: KYCLimits(
                daily_transaction_limit=Money(Decimal('100000'), Currency.USD),
                monthly_transaction_limit=Money(Decimal('1000000'), Currency.USD),
                single_transaction_limit=Money(Decimal('100000'), Currency.USD)
                # No annual limit for highest tier
            )
        }
    
    def create_customer(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: Optional[str] = None,
        date_of_birth: Optional[datetime] = None,
        address: Optional[Address] = None
    ) -> Customer:
        """
        Create a new customer
        
        Args:
            first_name: Customer's first name
            last_name: Customer's last name  
            email: Customer's email address
            phone: Optional phone number
            date_of_birth: Optional date of birth
            address: Optional address
            
        Returns:
            Created Customer object
        """
        now = datetime.now(timezone.utc)
        customer_id = str(uuid.uuid4())
        
        customer = Customer(
            id=customer_id,
            created_at=now,
            updated_at=now,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            date_of_birth=date_of_birth,
            address=address
        )
        
        # Save customer
        self._save_customer(customer)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_CREATED,
            entity_type="customer",
            entity_id=customer.id,
            metadata={
                "full_name": customer.full_name,
                "email": email,
                "kyc_tier": customer.kyc_tier.value
            }
        )
        
        return customer
    
    def get_customer(self, customer_id: str) -> Optional[Customer]:
        """Get customer by ID"""
        customer_dict = self.storage.load(self.table_name, customer_id)
        if customer_dict:
            return self._customer_from_dict(customer_dict)
        return None
    
    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        """Get customer by email address"""
        customers = self.storage.find(self.table_name, {"email": email})
        if customers:
            return self._customer_from_dict(customers[0])
        return None
    
    def update_customer_info(
        self,
        customer_id: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[Address] = None
    ) -> Customer:
        """Update customer information"""
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        
        old_data = {
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "email": customer.email,
            "phone": customer.phone
        }
        
        # Update fields if provided
        if first_name is not None:
            customer.first_name = first_name
        if last_name is not None:
            customer.last_name = last_name
        if email is not None:
            customer.email = email
        if phone is not None:
            customer.phone = phone
        if address is not None:
            customer.address = address
        
        customer.updated_at = datetime.now(timezone.utc)
        
        # Save customer
        self._save_customer(customer)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_UPDATED,
            entity_type="customer",
            entity_id=customer.id,
            metadata={
                "old_data": old_data,
                "new_data": {
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "email": customer.email,
                    "phone": customer.phone
                }
            }
        )
        
        return customer
    
    def update_kyc_status(
        self,
        customer_id: str,
        new_status: KYCStatus,
        new_tier: Optional[KYCTier] = None,
        documents: Optional[List[str]] = None,
        expiry_days: Optional[int] = None
    ) -> Customer:
        """
        Update customer KYC status and tier
        
        Args:
            customer_id: Customer ID
            new_status: New KYC status
            new_tier: New KYC tier (if status is VERIFIED)
            documents: List of document references
            expiry_days: Days until KYC expires (for VERIFIED status)
            
        Returns:
            Updated Customer object
        """
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        
        old_status = customer.kyc_status
        old_tier = customer.kyc_tier
        
        now = datetime.now(timezone.utc)
        customer.kyc_status = new_status
        customer.updated_at = now
        
        if documents:
            customer.kyc_documents = documents
        
        if new_status == KYCStatus.VERIFIED:
            customer.kyc_verified_at = now
            
            # Set tier if provided
            if new_tier:
                customer.kyc_tier = new_tier
            
            # Set expiry if provided
            if expiry_days:
                customer.kyc_expires_at = now + timedelta(days=expiry_days)
        
        elif new_status == KYCStatus.EXPIRED:
            customer.kyc_expires_at = now
            # Downgrade to lower tier when expired
            customer.kyc_tier = KYCTier.TIER_0
        
        elif new_status == KYCStatus.REJECTED:
            customer.kyc_tier = KYCTier.TIER_0
            customer.kyc_verified_at = None
            customer.kyc_expires_at = None
        
        # Save customer
        self._save_customer(customer)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.KYC_STATUS_CHANGED,
            entity_type="customer",
            entity_id=customer.id,
            metadata={
                "old_status": old_status.value,
                "new_status": new_status.value,
                "old_tier": old_tier.value,
                "new_tier": customer.kyc_tier.value,
                "documents": documents or [],
                "expires_at": customer.kyc_expires_at.isoformat() if customer.kyc_expires_at else None
            }
        )
        
        return customer
    
    def add_beneficiary(
        self,
        customer_id: str,
        beneficiary: Beneficiary
    ) -> Customer:
        """Add beneficiary to customer"""
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        
        customer.beneficiaries.append(beneficiary)
        
        # Validate total percentages
        total_percentage = sum(b.percentage for b in customer.beneficiaries)
        if total_percentage > Decimal('100'):
            raise ValueError(f"Total beneficiary percentages ({total_percentage}%) exceed 100%")
        
        customer.updated_at = datetime.now(timezone.utc)
        self._save_customer(customer)
        
        return customer
    
    def remove_beneficiary(
        self,
        customer_id: str,
        beneficiary_name: str
    ) -> Customer:
        """Remove beneficiary from customer"""
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        
        original_count = len(customer.beneficiaries)
        customer.beneficiaries = [
            b for b in customer.beneficiaries 
            if b.name != beneficiary_name
        ]
        
        if len(customer.beneficiaries) == original_count:
            raise ValueError(f"Beneficiary '{beneficiary_name}' not found")
        
        customer.updated_at = datetime.now(timezone.utc)
        self._save_customer(customer)
        
        return customer
    
    def deactivate_customer(self, customer_id: str, reason: str) -> Customer:
        """Deactivate a customer account"""
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        
        customer.is_active = False
        customer.updated_at = datetime.now(timezone.utc)
        
        self._save_customer(customer)
        
        # Log audit event
        self.audit_trail.log_event(
            event_type=AuditEventType.CUSTOMER_UPDATED,
            entity_type="customer",
            entity_id=customer.id,
            metadata={
                "action": "deactivated",
                "reason": reason
            }
        )
        
        return customer
    
    def get_kyc_limits(self, customer_id: str, currency: Currency) -> KYCLimits:
        """
        Get transaction limits for customer based on KYC tier
        
        Args:
            customer_id: Customer ID
            currency: Currency for limits
            
        Returns:
            KYCLimits for the customer's tier in requested currency
        """
        customer = self.get_customer(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        
        # Get default limits for tier (in USD)
        default_limits = self._default_kyc_limits[customer.kyc_tier]
        
        # If requesting USD, return as-is
        if currency == Currency.USD:
            return default_limits
        
        # For other currencies, would need to convert based on exchange rates
        # For now, return same amounts but in requested currency
        # In production, implement proper currency conversion
        return KYCLimits(
            daily_transaction_limit=Money(default_limits.daily_transaction_limit.amount, currency),
            monthly_transaction_limit=Money(default_limits.monthly_transaction_limit.amount, currency),
            single_transaction_limit=Money(default_limits.single_transaction_limit.amount, currency),
            annual_cumulative_limit=Money(
                default_limits.annual_cumulative_limit.amount, currency
            ) if default_limits.annual_cumulative_limit else None
        )
    
    def get_customers_needing_kyc_renewal(self, days_ahead: int = 30) -> List[Customer]:
        """Get customers whose KYC will expire within specified days"""
        all_customers = self.storage.load_all(self.table_name)
        customers = [self._customer_from_dict(data) for data in all_customers]
        
        cutoff_date = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        
        return [
            customer for customer in customers
            if (customer.kyc_expires_at and 
                customer.kyc_expires_at <= cutoff_date and
                customer.kyc_status == KYCStatus.VERIFIED)
        ]
    
    def search_customers(
        self,
        email: Optional[str] = None,
        name: Optional[str] = None,
        kyc_status: Optional[KYCStatus] = None,
        kyc_tier: Optional[KYCTier] = None,
        is_active: Optional[bool] = None
    ) -> List[Customer]:
        """Search customers by various criteria"""
        all_customers = self.storage.load_all(self.table_name)
        customers = [self._customer_from_dict(data) for data in all_customers]
        
        filtered_customers = customers
        
        if email:
            filtered_customers = [
                c for c in filtered_customers 
                if email.lower() in c.email.lower()
            ]
        
        if name:
            name_lower = name.lower()
            filtered_customers = [
                c for c in filtered_customers
                if (name_lower in c.first_name.lower() or 
                    name_lower in c.last_name.lower() or
                    name_lower in c.full_name.lower())
            ]
        
        if kyc_status:
            filtered_customers = [
                c for c in filtered_customers
                if c.kyc_status == kyc_status
            ]
        
        if kyc_tier:
            filtered_customers = [
                c for c in filtered_customers
                if c.kyc_tier == kyc_tier
            ]
        
        if is_active is not None:
            filtered_customers = [
                c for c in filtered_customers
                if c.is_active == is_active
            ]
        
        return filtered_customers
    
    def _save_customer(self, customer: Customer) -> None:
        """Save customer to storage"""
        customer_dict = self._customer_to_dict(customer)
        self.storage.save(self.table_name, customer.id, customer_dict)
    
    def _customer_to_dict(self, customer: Customer) -> Dict:
        """Convert Customer to dictionary for storage"""
        result = customer.to_dict()
        result['kyc_status'] = customer.kyc_status.value
        result['kyc_tier'] = customer.kyc_tier.value
        
        if customer.date_of_birth:
            result['date_of_birth'] = customer.date_of_birth.isoformat()
        
        if customer.kyc_verified_at:
            result['kyc_verified_at'] = customer.kyc_verified_at.isoformat()
        
        if customer.kyc_expires_at:
            result['kyc_expires_at'] = customer.kyc_expires_at.isoformat()
        
        if customer.address:
            result['address'] = {
                'line1': customer.address.line1,
                'line2': customer.address.line2,
                'city': customer.address.city,
                'state': customer.address.state,
                'postal_code': customer.address.postal_code,
                'country': customer.address.country
            }
        
        if customer.beneficiaries:
            result['beneficiaries'] = [
                {
                    'name': b.name,
                    'relationship': b.relationship,
                    'percentage': str(b.percentage),
                    'contact_info': b.contact_info
                } for b in customer.beneficiaries
            ]
        
        return result
    
    def _customer_from_dict(self, data: Dict) -> Customer:
        """Convert dictionary to Customer"""
        created_at = datetime.fromisoformat(data['created_at'])
        updated_at = datetime.fromisoformat(data['updated_at'])
        
        date_of_birth = None
        if data.get('date_of_birth'):
            date_of_birth = datetime.fromisoformat(data['date_of_birth'])
        
        kyc_verified_at = None
        if data.get('kyc_verified_at'):
            kyc_verified_at = datetime.fromisoformat(data['kyc_verified_at'])
        
        kyc_expires_at = None
        if data.get('kyc_expires_at'):
            kyc_expires_at = datetime.fromisoformat(data['kyc_expires_at'])
        
        address = None
        if data.get('address'):
            addr_data = data['address']
            address = Address(
                line1=addr_data['line1'],
                line2=addr_data.get('line2'),
                city=addr_data['city'],
                state=addr_data['state'],
                postal_code=addr_data['postal_code'],
                country=addr_data['country']
            )
        
        beneficiaries = []
        if data.get('beneficiaries'):
            for b_data in data['beneficiaries']:
                beneficiary = Beneficiary(
                    name=b_data['name'],
                    relationship=b_data['relationship'],
                    percentage=Decimal(b_data['percentage']),
                    contact_info=b_data.get('contact_info')
                )
                beneficiaries.append(beneficiary)
        
        return Customer(
            id=data['id'],
            created_at=created_at,
            updated_at=updated_at,
            first_name=data['first_name'],
            last_name=data['last_name'],
            email=data['email'],
            phone=data.get('phone'),
            date_of_birth=date_of_birth,
            address=address,
            kyc_status=KYCStatus(data['kyc_status']),
            kyc_tier=KYCTier(data['kyc_tier']),
            kyc_verified_at=kyc_verified_at,
            kyc_expires_at=kyc_expires_at,
            kyc_documents=data.get('kyc_documents', []),
            tax_id=data.get('tax_id'),
            nationality=data.get('nationality'),
            beneficiaries=beneficiaries,
            notes=data.get('notes'),
            is_active=data.get('is_active', True)
        )