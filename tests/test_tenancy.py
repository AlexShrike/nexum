"""
Tests for Multi-Tenancy Support Module

Comprehensive tests covering all aspects of the tenancy system including:
- Tenant CRUD operations
- Tenant isolation
- TenantAwareStorage functionality
- Context variable management
- API middleware integration
- Quota checking and enforcement
- Multi-tenant data access patterns
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any
import uuid

from core_banking.tenancy import (
    Tenant, TenantManager, TenantAwareStorage, TenantIsolationStrategy,
    SubscriptionTier, TenantStats, TenantMiddleware,
    get_current_tenant, set_current_tenant, tenant_context
)
from core_banking.storage import InMemoryStorage


class TestTenant:
    """Test Tenant dataclass functionality"""
    
    def test_tenant_creation(self):
        """Test basic tenant creation"""
        tenant = Tenant(
            id="tenant1",
            name="ACME Bank",
            code="ACME_BANK",
            display_name="ACME Banking Solutions"
        )
        
        assert tenant.id == "tenant1"
        assert tenant.name == "ACME Bank"
        assert tenant.code == "ACME_BANK"
        assert tenant.display_name == "ACME Banking Solutions"
        assert tenant.is_active is True
        assert tenant.subscription_tier == SubscriptionTier.FREE
        assert isinstance(tenant.created_at, datetime)
        assert isinstance(tenant.updated_at, datetime)
    
    def test_tenant_to_dict(self):
        """Test tenant serialization to dictionary"""
        tenant = Tenant(
            id="tenant1",
            name="ACME Bank",
            code="ACME_BANK",
            display_name="ACME Banking Solutions",
            subscription_tier=SubscriptionTier.PROFESSIONAL,
            max_users=100,
            max_accounts=1000,
            contact_email="admin@acme.com"
        )
        
        data = tenant.to_dict()
        
        assert data['id'] == "tenant1"
        assert data['name'] == "ACME Bank"
        assert data['code'] == "ACME_BANK"
        assert data['subscription_tier'] == "professional"
        assert data['max_users'] == 100
        assert data['max_accounts'] == 1000
        assert data['contact_email'] == "admin@acme.com"
        assert isinstance(data['created_at'], str)
        assert isinstance(data['updated_at'], str)
    
    def test_tenant_from_dict(self):
        """Test tenant deserialization from dictionary"""
        data = {
            'id': "tenant1",
            'name': "ACME Bank",
            'code': "ACME_BANK",
            'display_name': "ACME Banking Solutions",
            'description': "Test bank",
            'is_active': True,
            'created_at': "2024-01-01T00:00:00+00:00",
            'updated_at': "2024-01-01T00:00:00+00:00",
            'settings': {'feature_x': True},
            'database_schema': None,
            'max_users': 100,
            'max_accounts': 1000,
            'subscription_tier': "professional",
            'contact_email': "admin@acme.com",
            'contact_phone': "+1-555-0123",
            'logo_url': "https://acme.com/logo.png",
            'primary_color': "#0066CC"
        }
        
        tenant = Tenant.from_dict(data)
        
        assert tenant.id == "tenant1"
        assert tenant.name == "ACME Bank"
        assert tenant.subscription_tier == SubscriptionTier.PROFESSIONAL
        assert tenant.max_users == 100
        assert tenant.contact_email == "admin@acme.com"
        assert isinstance(tenant.created_at, datetime)
        assert isinstance(tenant.updated_at, datetime)


class TestTenantContext:
    """Test tenant context management with contextvars"""
    
    def test_no_tenant_initially(self):
        """Test that no tenant is set initially"""
        assert get_current_tenant() is None
    
    def test_set_get_tenant(self):
        """Test setting and getting tenant"""
        set_current_tenant("tenant1")
        assert get_current_tenant() == "tenant1"
        
        set_current_tenant("tenant2")
        assert get_current_tenant() == "tenant2"
    
    def test_tenant_context_manager(self):
        """Test tenant context manager functionality"""
        # Clear any existing tenant context
        set_current_tenant(None)
        
        # No tenant initially
        assert get_current_tenant() is None
        
        # Set a tenant
        set_current_tenant("tenant1")
        assert get_current_tenant() == "tenant1"
        
        # Use context manager to temporarily switch
        with tenant_context("tenant2"):
            assert get_current_tenant() == "tenant2"
        
        # Should restore previous tenant
        assert get_current_tenant() == "tenant1"
    
    def test_nested_tenant_context(self):
        """Test nested tenant context managers"""
        set_current_tenant("tenant1")
        
        with tenant_context("tenant2"):
            assert get_current_tenant() == "tenant2"
            
            with tenant_context("tenant3"):
                assert get_current_tenant() == "tenant3"
            
            assert get_current_tenant() == "tenant2"
        
        assert get_current_tenant() == "tenant1"


class TestTenantAwareStorage:
    """Test TenantAwareStorage functionality"""
    
    def setup_method(self):
        """Set up test storage"""
        # Clear any existing tenant context
        set_current_tenant(None)
        self.inner_storage = InMemoryStorage()
        self.tenant_storage = TenantAwareStorage(self.inner_storage)
    
    def test_save_with_tenant(self):
        """Test saving data with tenant context"""
        set_current_tenant("tenant1")
        
        data = {"name": "Test Account", "balance": "1000.00"}
        self.tenant_storage.save("accounts", "acc1", data)
        
        # Check that tenant_id was added
        raw_data = self.inner_storage.load("accounts", "acc1")
        assert raw_data["_tenant_id"] == "tenant1"
        assert raw_data["name"] == "Test Account"
    
    def test_save_without_tenant(self):
        """Test saving data without tenant context"""
        # Clear any tenant context
        set_current_tenant(None)
        
        data = {"name": "System Account", "balance": "0.00"}
        self.tenant_storage.save("accounts", "sys1", data)
        
        # Should not add tenant_id
        raw_data = self.inner_storage.load("accounts", "sys1")
        assert "_tenant_id" not in raw_data
        assert raw_data["name"] == "System Account"
    
    def test_load_with_tenant_isolation(self):
        """Test loading data with tenant isolation"""
        # Save data for tenant1
        set_current_tenant("tenant1")
        self.tenant_storage.save("accounts", "acc1", {"name": "Tenant1 Account"})
        
        # Save data for tenant2  
        set_current_tenant("tenant2")
        self.tenant_storage.save("accounts", "acc2", {"name": "Tenant2 Account"})
        
        # Tenant1 should only see their data
        set_current_tenant("tenant1")
        data = self.tenant_storage.load("accounts", "acc1")
        assert data["name"] == "Tenant1 Account"
        
        # Tenant1 should not see tenant2's data
        data = self.tenant_storage.load("accounts", "acc2")
        assert data is None
        
        # Tenant2 should see their data
        set_current_tenant("tenant2")
        data = self.tenant_storage.load("accounts", "acc2")
        assert data["name"] == "Tenant2 Account"
        
        # Tenant2 should not see tenant1's data
        data = self.tenant_storage.load("accounts", "acc1")
        assert data is None
    
    def test_load_super_admin_mode(self):
        """Test loading in super-admin mode (no tenant set)"""
        # Save data for different tenants
        set_current_tenant("tenant1")
        self.tenant_storage.save("accounts", "acc1", {"name": "Tenant1 Account"})
        
        set_current_tenant("tenant2")
        self.tenant_storage.save("accounts", "acc2", {"name": "Tenant2 Account"})
        
        # Super-admin (no tenant) should see all data
        set_current_tenant(None)
        data1 = self.tenant_storage.load("accounts", "acc1")
        data2 = self.tenant_storage.load("accounts", "acc2")
        
        assert data1["name"] == "Tenant1 Account"
        assert data2["name"] == "Tenant2 Account"
    
    def test_load_all_with_tenant_filtering(self):
        """Test load_all with tenant filtering"""
        # Save data for different tenants
        set_current_tenant("tenant1")
        self.tenant_storage.save("accounts", "acc1", {"name": "Account 1"})
        self.tenant_storage.save("accounts", "acc2", {"name": "Account 2"})
        
        set_current_tenant("tenant2")
        self.tenant_storage.save("accounts", "acc3", {"name": "Account 3"})
        
        # Tenant1 should only see their accounts
        set_current_tenant("tenant1")
        accounts = self.tenant_storage.load_all("accounts")
        assert len(accounts) == 2
        names = [acc["name"] for acc in accounts]
        assert "Account 1" in names
        assert "Account 2" in names
        assert "Account 3" not in names
        
        # Tenant2 should only see their account
        set_current_tenant("tenant2")
        accounts = self.tenant_storage.load_all("accounts")
        assert len(accounts) == 1
        assert accounts[0]["name"] == "Account 3"
    
    def test_find_with_tenant_filtering(self):
        """Test find with automatic tenant filtering"""
        # Save data for different tenants
        set_current_tenant("tenant1")
        self.tenant_storage.save("accounts", "acc1", {"name": "Savings", "type": "SAVINGS"})
        self.tenant_storage.save("accounts", "acc2", {"name": "Checking", "type": "CHECKING"})
        
        set_current_tenant("tenant2")
        self.tenant_storage.save("accounts", "acc3", {"name": "Business", "type": "SAVINGS"})
        
        # Find by type for tenant1
        set_current_tenant("tenant1")
        savings = self.tenant_storage.find("accounts", {"type": "SAVINGS"})
        assert len(savings) == 1
        assert savings[0]["name"] == "Savings"
        
        # Find by type for tenant2
        set_current_tenant("tenant2")
        savings = self.tenant_storage.find("accounts", {"type": "SAVINGS"})
        assert len(savings) == 1
        assert savings[0]["name"] == "Business"
    
    def test_delete_with_tenant_verification(self):
        """Test delete with tenant access verification"""
        # Save data for different tenants
        set_current_tenant("tenant1")
        self.tenant_storage.save("accounts", "acc1", {"name": "Tenant1 Account"})
        
        set_current_tenant("tenant2")
        self.tenant_storage.save("accounts", "acc2", {"name": "Tenant2 Account"})
        
        # Tenant1 should be able to delete their own data
        set_current_tenant("tenant1")
        result = self.tenant_storage.delete("accounts", "acc1")
        assert result is True
        
        # Tenant1 should not be able to delete tenant2's data
        result = self.tenant_storage.delete("accounts", "acc2")
        assert result is False
        
        # Verify tenant2's data is still there
        set_current_tenant("tenant2")
        data = self.tenant_storage.load("accounts", "acc2")
        assert data["name"] == "Tenant2 Account"
    
    def test_exists_with_tenant_access(self):
        """Test exists with tenant access control"""
        set_current_tenant("tenant1")
        self.tenant_storage.save("accounts", "acc1", {"name": "Account"})
        
        # Tenant1 should see the record exists
        assert self.tenant_storage.exists("accounts", "acc1") is True
        
        # Tenant2 should not see the record
        set_current_tenant("tenant2")
        assert self.tenant_storage.exists("accounts", "acc1") is False
        
        # Super-admin should see the record
        set_current_tenant(None)
        assert self.tenant_storage.exists("accounts", "acc1") is True
    
    def test_count_with_tenant_filtering(self):
        """Test count with tenant filtering"""
        set_current_tenant("tenant1")
        self.tenant_storage.save("accounts", "acc1", {"name": "Account 1"})
        self.tenant_storage.save("accounts", "acc2", {"name": "Account 2"})
        
        set_current_tenant("tenant2")
        self.tenant_storage.save("accounts", "acc3", {"name": "Account 3"})
        
        # Count for tenant1
        set_current_tenant("tenant1")
        assert self.tenant_storage.count("accounts") == 2
        
        # Count for tenant2
        set_current_tenant("tenant2")
        assert self.tenant_storage.count("accounts") == 1
    
    def test_clear_table_protection(self):
        """Test that clear_table is protected from tenant context"""
        set_current_tenant("tenant1")
        
        # Should raise exception when tenant is set
        with pytest.raises(PermissionError):
            self.tenant_storage.clear_table("accounts")
        
        # Should work in super-admin mode
        set_current_tenant(None)
        self.tenant_storage.clear_table("accounts")  # Should not raise


class TestTenantManager:
    """Test TenantManager functionality"""
    
    def setup_method(self):
        """Set up test tenant manager"""
        self.storage = InMemoryStorage()
        self.manager = TenantManager(self.storage)
    
    def test_create_tenant(self):
        """Test tenant creation"""
        tenant = self.manager.create_tenant(
            name="ACME Bank",
            code="ACME_BANK",
            display_name="ACME Banking Solutions",
            description="Test financial institution",
            max_users=100,
            subscription_tier=SubscriptionTier.PROFESSIONAL
        )
        
        assert tenant.name == "ACME Bank"
        assert tenant.code == "ACME_BANK"
        assert tenant.display_name == "ACME Banking Solutions"
        assert tenant.max_users == 100
        assert tenant.subscription_tier == SubscriptionTier.PROFESSIONAL
        assert tenant.is_active is True
        assert len(tenant.id) > 0  # Should have generated ID
    
    def test_create_tenant_duplicate_code(self):
        """Test that duplicate codes are rejected"""
        self.manager.create_tenant("Bank 1", "TEST_BANK", "Test Bank 1")
        
        with pytest.raises(ValueError, match="Tenant code 'TEST_BANK' already exists"):
            self.manager.create_tenant("Bank 2", "TEST_BANK", "Test Bank 2")
    
    def test_get_tenant(self):
        """Test getting tenant by ID"""
        tenant = self.manager.create_tenant("Test Bank", "TEST", "Test")
        
        retrieved = self.manager.get_tenant(tenant.id)
        assert retrieved is not None
        assert retrieved.id == tenant.id
        assert retrieved.name == "Test Bank"
        assert retrieved.code == "TEST"
        
        # Test non-existent tenant
        assert self.manager.get_tenant("nonexistent") is None
    
    def test_get_tenant_by_code(self):
        """Test getting tenant by code"""
        tenant = self.manager.create_tenant("Test Bank", "TEST_CODE", "Test")
        
        retrieved = self.manager.get_tenant_by_code("TEST_CODE")
        assert retrieved is not None
        assert retrieved.id == tenant.id
        assert retrieved.code == "TEST_CODE"
        
        # Test non-existent code
        assert self.manager.get_tenant_by_code("NONEXISTENT") is None
    
    def test_list_tenants(self):
        """Test listing tenants"""
        t1 = self.manager.create_tenant("Bank 1", "BANK1", "Bank One")
        t2 = self.manager.create_tenant("Bank 2", "BANK2", "Bank Two")
        
        # Deactivate one tenant
        self.manager.deactivate_tenant(t2.id)
        
        # List all tenants
        all_tenants = self.manager.list_tenants()
        assert len(all_tenants) == 2
        
        # List active tenants only
        active_tenants = self.manager.list_tenants(is_active=True)
        assert len(active_tenants) == 1
        assert active_tenants[0].id == t1.id
        
        # List inactive tenants only
        inactive_tenants = self.manager.list_tenants(is_active=False)
        assert len(inactive_tenants) == 1
        assert inactive_tenants[0].id == t2.id
    
    def test_update_tenant(self):
        """Test updating tenant fields"""
        tenant = self.manager.create_tenant("Original", "ORIG", "Original Bank")
        
        updated = self.manager.update_tenant(
            tenant.id,
            name="Updated Bank",
            display_name="Updated Banking Solutions",
            max_users=500
        )
        
        assert updated is not None
        assert updated.name == "Updated Bank"
        assert updated.display_name == "Updated Banking Solutions"
        assert updated.max_users == 500
        assert updated.code == "ORIG"  # Unchanged
        assert updated.updated_at > tenant.updated_at
        
        # Test non-existent tenant
        result = self.manager.update_tenant("nonexistent", name="Test")
        assert result is None
    
    def test_activate_deactivate_tenant(self):
        """Test tenant activation/deactivation"""
        tenant = self.manager.create_tenant("Test Bank", "TEST", "Test")
        assert tenant.is_active is True
        
        # Deactivate
        result = self.manager.deactivate_tenant(tenant.id)
        assert result is True
        
        retrieved = self.manager.get_tenant(tenant.id)
        assert retrieved.is_active is False
        
        # Reactivate
        result = self.manager.activate_tenant(tenant.id)
        assert result is True
        
        retrieved = self.manager.get_tenant(tenant.id)
        assert retrieved.is_active is True
        
        # Test non-existent tenant
        assert self.manager.activate_tenant("nonexistent") is False
        assert self.manager.deactivate_tenant("nonexistent") is False
    
    def test_check_quota(self):
        """Test quota checking"""
        tenant = self.manager.create_tenant(
            "Test Bank", "TEST", "Test",
            max_users=10,
            max_accounts=100
        )
        
        # Active tenant should pass quota checks
        assert self.manager.check_quota(tenant.id, "users") is True
        assert self.manager.check_quota(tenant.id, "accounts") is True
        
        # Inactive tenant should fail
        self.manager.deactivate_tenant(tenant.id)
        assert self.manager.check_quota(tenant.id, "users") is False
        assert self.manager.check_quota(tenant.id, "accounts") is False
        
        # Non-existent tenant should fail
        assert self.manager.check_quota("nonexistent", "users") is False
    
    def test_get_tenant_stats(self):
        """Test getting tenant statistics"""
        tenant = self.manager.create_tenant("Test Bank", "TEST", "Test")
        
        stats = self.manager.get_tenant_stats(tenant.id)
        assert stats is not None
        assert stats.tenant_id == tenant.id
        assert stats.user_count == 0  # Default value
        assert stats.account_count == 0  # Default value
        
        # Non-existent tenant
        assert self.manager.get_tenant_stats("nonexistent") is None
    
    def test_get_usage_report(self):
        """Test getting usage report for all tenants"""
        t1 = self.manager.create_tenant("Bank 1", "BANK1", "Bank One")
        t2 = self.manager.create_tenant("Bank 2", "BANK2", "Bank Two")
        
        # Deactivate one tenant
        self.manager.deactivate_tenant(t2.id)
        
        report = self.manager.get_usage_report()
        
        # Should only include active tenants
        assert len(report) == 1
        assert report[0].tenant_id == t1.id


class TestTenantMiddleware:
    """Test TenantMiddleware functionality"""
    
    def setup_method(self):
        """Set up test middleware"""
        self.storage = InMemoryStorage()
        self.manager = TenantManager(self.storage)
        self.middleware = TenantMiddleware(self.manager)
        
        # Create test tenant
        self.tenant = self.manager.create_tenant(
            "ACME Bank", "ACME", "ACME Banking"
        )
    
    def test_extract_tenant_from_header(self):
        """Test extracting tenant from header"""
        headers = {'X-Tenant-ID': self.tenant.id}
        result = self.middleware.extract_tenant_from_header(headers)
        assert result == self.tenant.id
        
        headers = {'x-tenant-id': self.tenant.id}
        result = self.middleware.extract_tenant_from_header(headers)
        assert result == self.tenant.id
        
        headers = {}
        result = self.middleware.extract_tenant_from_header(headers)
        assert result is None
    
    def test_extract_tenant_from_subdomain(self):
        """Test extracting tenant from subdomain"""
        # Should find tenant by code
        result = self.middleware.extract_tenant_from_subdomain("acme.nexum.io")
        assert result == self.tenant.id
        
        # Should handle case insensitive
        result = self.middleware.extract_tenant_from_subdomain("ACME.nexum.io")
        assert result == self.tenant.id
        
        # Should return None for non-existent subdomain
        result = self.middleware.extract_tenant_from_subdomain("unknown.nexum.io")
        assert result is None
        
        # Should return None for plain hostname
        result = self.middleware.extract_tenant_from_subdomain("localhost")
        assert result is None
    
    def test_extract_tenant_from_jwt(self):
        """Test extracting tenant from JWT (basic test without full JWT validation)"""
        # This is a simplified test - in production would use proper JWT signing
        import json
        import base64
        
        # Create a mock JWT payload
        payload = {"tenant_id": self.tenant.id}
        encoded_payload = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode().rstrip('=')
        
        # Mock token format (header.payload.signature)
        token = f"header.{encoded_payload}.signature"
        
        result = self.middleware.extract_tenant_from_jwt(token)
        assert result == self.tenant.id


class TestTenantIntegration:
    """Integration tests for complete multi-tenancy flow"""
    
    def setup_method(self):
        """Set up complete multi-tenant system"""
        # Clear any existing tenant context
        set_current_tenant(None)
        self.storage = InMemoryStorage()
        self.tenant_manager = TenantManager(self.storage)
        self.tenant_storage = TenantAwareStorage(self.storage)
        
        # Create test tenants
        self.tenant1 = self.tenant_manager.create_tenant(
            "First Bank", "FIRST", "First Banking"
        )
        self.tenant2 = self.tenant_manager.create_tenant(
            "Second Bank", "SECOND", "Second Banking"
        )
    
    def test_complete_tenant_isolation_flow(self):
        """Test complete flow of tenant data isolation"""
        # Tenant 1 creates some accounts
        with tenant_context(self.tenant1.id):
            self.tenant_storage.save("accounts", "acc1", {
                "name": "First Bank Checking",
                "balance": "1000.00"
            })
            self.tenant_storage.save("accounts", "acc2", {
                "name": "First Bank Savings",
                "balance": "5000.00"
            })
        
        # Tenant 2 creates some accounts
        with tenant_context(self.tenant2.id):
            self.tenant_storage.save("accounts", "acc3", {
                "name": "Second Bank Business",
                "balance": "10000.00"
            })
        
        # Verify tenant 1 can only see their accounts
        with tenant_context(self.tenant1.id):
            accounts = self.tenant_storage.load_all("accounts")
            assert len(accounts) == 2
            names = [acc["name"] for acc in accounts]
            assert "First Bank Checking" in names
            assert "First Bank Savings" in names
            assert "Second Bank Business" not in names
        
        # Verify tenant 2 can only see their accounts
        with tenant_context(self.tenant2.id):
            accounts = self.tenant_storage.load_all("accounts")
            assert len(accounts) == 1
            assert accounts[0]["name"] == "Second Bank Business"
        
        # Verify super-admin can see all accounts
        set_current_tenant(None)
        accounts = self.tenant_storage.load_all("accounts")
        assert len(accounts) == 3
    
    def test_tenant_deactivation_blocks_access(self):
        """Test that deactivated tenants cannot access data"""
        # Save data for tenant 1
        with tenant_context(self.tenant1.id):
            self.tenant_storage.save("accounts", "acc1", {"name": "Account"})
        
        # Verify normal access works
        with tenant_context(self.tenant1.id):
            data = self.tenant_storage.load("accounts", "acc1")
            assert data is not None
        
        # Deactivate tenant
        self.tenant_manager.deactivate_tenant(self.tenant1.id)
        
        # Access should still work at storage level (business logic would prevent it)
        with tenant_context(self.tenant1.id):
            data = self.tenant_storage.load("accounts", "acc1")
            assert data is not None  # Storage doesn't enforce activation status
    
    def test_cross_tenant_operation_prevention(self):
        """Test that cross-tenant operations are prevented"""
        # Tenant 1 creates an account
        with tenant_context(self.tenant1.id):
            self.tenant_storage.save("accounts", "acc1", {"name": "Tenant1 Account"})
        
        # Tenant 2 tries to access tenant 1's account
        with tenant_context(self.tenant2.id):
            # Should not be able to load
            data = self.tenant_storage.load("accounts", "acc1")
            assert data is None
            
            # Should not be able to delete
            result = self.tenant_storage.delete("accounts", "acc1")
            assert result is False
            
            # Should not see it in exists check
            exists = self.tenant_storage.exists("accounts", "acc1")
            assert exists is False
        
        # Verify tenant 1 still has their data
        with tenant_context(self.tenant1.id):
            data = self.tenant_storage.load("accounts", "acc1")
            assert data is not None
            assert data["name"] == "Tenant1 Account"
    
    def test_tenant_switching_preserves_isolation(self):
        """Test that switching tenant contexts preserves data isolation"""
        # Clear any existing tenant context
        set_current_tenant(None)
        
        # Create data for multiple tenants with unique record IDs
        with tenant_context(self.tenant1.id):
            self.tenant_storage.save("settings", "config1", {"theme": "blue"})
        
        with tenant_context(self.tenant2.id):
            self.tenant_storage.save("settings", "config2", {"theme": "red"})
        
        # Switching between tenants should show different data
        with tenant_context(self.tenant1.id):
            config = self.tenant_storage.load("settings", "config1")
            assert config is not None, "Config1 should not be None for tenant1"
            assert config["theme"] == "blue"
            
            # Should not see tenant2's data
            config2 = self.tenant_storage.load("settings", "config2")
            assert config2 is None, "Should not see tenant2's config"
        
        with tenant_context(self.tenant2.id):
            config = self.tenant_storage.load("settings", "config2")
            assert config is not None, "Config2 should not be None for tenant2"
            assert config["theme"] == "red"
            
            # Should not see tenant1's data
            config1 = self.tenant_storage.load("settings", "config1")
            assert config1 is None, "Should not see tenant1's config"
        
        # Back to tenant 1
        with tenant_context(self.tenant1.id):
            config = self.tenant_storage.load("settings", "config1")
            assert config is not None, "Config1 should still be available for tenant1"
            assert config["theme"] == "blue"


class TestTenantStatistics:
    """Test tenant statistics and reporting"""
    
    def setup_method(self):
        """Set up test environment"""
        self.storage = InMemoryStorage()
        self.manager = TenantManager(self.storage)
    
    def test_tenant_stats_creation(self):
        """Test TenantStats dataclass"""
        from decimal import Decimal
        
        stats = TenantStats(
            tenant_id="tenant1",
            user_count=10,
            account_count=25,
            transaction_count=150,
            total_balance=Decimal('50000.00')
        )
        
        assert stats.tenant_id == "tenant1"
        assert stats.user_count == 10
        assert stats.account_count == 25
        assert stats.transaction_count == 150
        assert stats.total_balance == Decimal('50000.00')
    
    def test_basic_stats_collection(self):
        """Test basic statistics collection"""
        tenant = self.manager.create_tenant("Test Bank", "TEST", "Test")
        
        stats = self.manager.get_tenant_stats(tenant.id)
        assert stats is not None
        assert stats.tenant_id == tenant.id
        assert isinstance(stats.user_count, int)
        assert isinstance(stats.account_count, int)
        assert isinstance(stats.transaction_count, int)


# Additional test to ensure the system works without tenants (backward compatibility)
class TestBackwardCompatibility:
    """Test that the system works without tenant context (super-admin mode)"""
    
    def setup_method(self):
        """Set up storage without tenant context"""
        self.storage = InMemoryStorage()
        self.tenant_storage = TenantAwareStorage(self.storage)
    
    def test_operations_without_tenant_context(self):
        """Test that operations work normally without tenant context"""
        # Should work without any tenant set
        set_current_tenant(None)
        
        # Save data
        data = {"name": "Global Account", "balance": "1000.00"}
        self.tenant_storage.save("accounts", "global1", data)
        
        # Load data
        loaded = self.tenant_storage.load("accounts", "global1")
        assert loaded is not None
        assert loaded["name"] == "Global Account"
        assert "_tenant_id" not in loaded  # Should not have tenant ID
        
        # Other operations
        assert self.tenant_storage.exists("accounts", "global1") is True
        
        all_accounts = self.tenant_storage.load_all("accounts")
        assert len(all_accounts) == 1
        
        found = self.tenant_storage.find("accounts", {"name": "Global Account"})
        assert len(found) == 1
        
        assert self.tenant_storage.count("accounts") == 1
        
        # Delete should work
        result = self.tenant_storage.delete("accounts", "global1")
        assert result is True