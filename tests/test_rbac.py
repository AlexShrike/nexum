"""
Test suite for RBAC module

Tests role management, user management, authentication, authorization,
and security features including password policies and session management.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from core_banking.storage import InMemoryStorage
from core_banking.audit import AuditTrail
from core_banking.currency import Money, Currency
from core_banking.rbac import (
    RBACManager, Permission, Role, User, Session, PasswordPolicy
)


@pytest.fixture
def storage():
    """Create in-memory storage for tests"""
    return InMemoryStorage()


@pytest.fixture
def audit(storage):
    """Create audit trail for tests"""
    return AuditTrail(storage)


@pytest.fixture
def rbac_manager(storage, audit):
    """Create RBAC manager for tests"""
    return RBACManager(storage, audit)


class TestSystemRoles:
    """Test system role creation and management"""
    
    def test_system_roles_created_on_init(self, rbac_manager):
        """Test that system roles are created on initialization"""
        roles = rbac_manager.list_roles()
        role_names = {role.name for role in roles}
        
        expected_roles = {
            "ADMIN", "BRANCH_MANAGER", "LOAN_OFFICER", "TELLER",
            "AUDITOR", "COMPLIANCE_OFFICER", "COLLECTOR", "READ_ONLY"
        }
        
        assert role_names == expected_roles
        assert len(roles) == 8
    
    def test_system_roles_have_correct_properties(self, rbac_manager):
        """Test that system roles have correct properties"""
        roles = rbac_manager.list_roles()
        
        admin_role = next(r for r in roles if r.name == "ADMIN")
        assert admin_role.is_system_role
        assert len(admin_role.permissions) == len(Permission)  # All permissions
        
        teller_role = next(r for r in roles if r.name == "TELLER")
        assert teller_role.is_system_role
        assert Permission.VIEW_ACCOUNT in teller_role.permissions
        assert Permission.CREATE_TRANSACTION in teller_role.permissions
        assert Permission.MANAGE_USERS not in teller_role.permissions
    
    def test_system_roles_cannot_be_deleted(self, rbac_manager):
        """Test that system roles cannot be deleted"""
        roles = rbac_manager.list_roles()
        admin_role = next(r for r in roles if r.name == "ADMIN")
        
        result = rbac_manager.delete_role(admin_role.id)
        assert not result
        
        # Role should still exist
        role_after = rbac_manager.get_role(admin_role.id)
        assert role_after is not None


class TestRoleManagement:
    """Test role CRUD operations"""
    
    def test_create_role(self, rbac_manager):
        """Test creating a new role"""
        permissions = {Permission.VIEW_ACCOUNT, Permission.CREATE_TRANSACTION}
        max_amount = Money(Decimal("10000.00"), Currency.USD)
        
        role_id = rbac_manager.create_role(
            name="Test Role",
            permissions=permissions,
            description="Test role for unit tests",
            max_transaction_amount=max_amount
        )
        
        assert role_id is not None
        
        role = rbac_manager.get_role(role_id)
        assert role is not None
        assert role.name == "Test Role"
        assert role.permissions == permissions
        assert not role.is_system_role
        assert role.max_transaction_amount == max_amount
    
    def test_get_nonexistent_role(self, rbac_manager):
        """Test getting non-existent role returns None"""
        role = rbac_manager.get_role("nonexistent")
        assert role is None
    
    def test_update_role(self, rbac_manager):
        """Test updating role properties"""
        # Create role
        permissions = {Permission.VIEW_ACCOUNT}
        role_id = rbac_manager.create_role("Test Role", permissions)
        
        # Update role
        new_permissions = {Permission.VIEW_ACCOUNT, Permission.CREATE_TRANSACTION}
        updated = rbac_manager.update_role(
            role_id,
            permissions=new_permissions,
            description="Updated description"
        )
        
        assert updated
        
        role = rbac_manager.get_role(role_id)
        assert role.permissions == new_permissions
        assert role.description == "Updated description"
    
    def test_update_system_role_fails(self, rbac_manager):
        """Test that system roles cannot be updated"""
        roles = rbac_manager.list_roles()
        admin_role = next(r for r in roles if r.name == "ADMIN")
        
        result = rbac_manager.update_role(
            admin_role.id,
            permissions={Permission.VIEW_ACCOUNT}
        )
        assert not result
    
    def test_delete_role(self, rbac_manager):
        """Test deleting a role"""
        permissions = {Permission.VIEW_ACCOUNT}
        role_id = rbac_manager.create_role("Test Role", permissions)
        
        deleted = rbac_manager.delete_role(role_id)
        assert deleted
        
        role = rbac_manager.get_role(role_id)
        assert role is None
    
    def test_delete_role_with_assigned_users_fails(self, rbac_manager):
        """Test that roles with assigned users cannot be deleted"""
        # Create role
        permissions = {Permission.VIEW_ACCOUNT}
        role_id = rbac_manager.create_role("Test Role", permissions)
        
        # Create user with role
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[role_id],
            created_by="admin"
        )
        
        # Try to delete role
        deleted = rbac_manager.delete_role(role_id)
        assert not deleted
        
        # Role should still exist
        role = rbac_manager.get_role(role_id)
        assert role is not None


class TestUserManagement:
    """Test user CRUD operations"""
    
    def test_create_user(self, rbac_manager):
        """Test creating a new user"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[teller_role.id],
            created_by="admin",
            password="TestPass123!"
        )
        
        assert user_id is not None
        
        user = rbac_manager.get_user(user_id)
        assert user is not None
        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.is_active
        assert not user.is_locked
        assert teller_role.id in user.roles
        assert user.password_hash is not None
        assert user.password_salt is not None
    
    def test_get_user_by_username(self, rbac_manager):
        """Test getting user by username"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin"
        )
        
        user = rbac_manager.get_user_by_username("testuser")
        assert user is not None
        assert user.id == user_id
    
    def test_get_nonexistent_user(self, rbac_manager):
        """Test getting non-existent user returns None"""
        user = rbac_manager.get_user("nonexistent")
        assert user is None
        
        user = rbac_manager.get_user_by_username("nonexistent")
        assert user is None
    
    def test_update_user(self, rbac_manager):
        """Test updating user properties"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin"
        )
        
        updated = rbac_manager.update_user(
            user_id,
            email="updated@example.com",
            full_name="Updated User",
            branch_id="BRANCH001"
        )
        
        assert updated
        
        user = rbac_manager.get_user(user_id)
        assert user.email == "updated@example.com"
        assert user.full_name == "Updated User"
        assert user.branch_id == "BRANCH001"
    
    def test_deactivate_user(self, rbac_manager):
        """Test deactivating a user"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin"
        )
        
        deactivated = rbac_manager.deactivate_user(user_id)
        assert deactivated
        
        user = rbac_manager.get_user(user_id)
        assert not user.is_active
    
    def test_activate_user(self, rbac_manager):
        """Test activating a user"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin"
        )
        
        # Deactivate first
        rbac_manager.deactivate_user(user_id)
        
        # Then activate
        activated = rbac_manager.activate_user(user_id)
        assert activated
        
        user = rbac_manager.get_user(user_id)
        assert user.is_active
        assert not user.is_locked
        assert user.failed_login_attempts == 0
    
    def test_list_users_with_filters(self, rbac_manager):
        """Test listing users with filters"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        admin_role = next(r for r in roles if r.name == "ADMIN")
        
        # Create users
        user1_id = rbac_manager.create_user(
            username="user1", email="user1@example.com", 
            full_name="User 1", roles=[teller_role.id], created_by="admin"
        )
        user2_id = rbac_manager.create_user(
            username="user2", email="user2@example.com", 
            full_name="User 2", roles=[admin_role.id], created_by="admin"
        )
        
        # Deactivate user2
        rbac_manager.deactivate_user(user2_id)
        
        # Test filters
        all_users = rbac_manager.list_users()
        assert len(all_users) == 2
        
        active_users = rbac_manager.list_users(is_active=True)
        assert len(active_users) == 1
        assert active_users[0].id == user1_id
        
        teller_users = rbac_manager.list_users(role=teller_role.id)
        assert len(teller_users) == 1
        assert teller_users[0].id == user1_id


class TestRoleAssignment:
    """Test role assignment and removal"""
    
    def test_assign_role(self, rbac_manager):
        """Test assigning role to user"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        admin_role = next(r for r in roles if r.name == "ADMIN")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[teller_role.id],
            created_by="admin"
        )
        
        # Assign additional role
        assigned = rbac_manager.assign_role(user_id, admin_role.id)
        assert assigned
        
        user = rbac_manager.get_user(user_id)
        assert teller_role.id in user.roles
        assert admin_role.id in user.roles
    
    def test_assign_duplicate_role(self, rbac_manager):
        """Test assigning role that user already has"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[teller_role.id],
            created_by="admin"
        )
        
        # Assign same role again
        assigned = rbac_manager.assign_role(user_id, teller_role.id)
        assert assigned
        
        user = rbac_manager.get_user(user_id)
        assert user.roles.count(teller_role.id) == 1  # Should not duplicate
    
    def test_remove_role(self, rbac_manager):
        """Test removing role from user"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        admin_role = next(r for r in roles if r.name == "ADMIN")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[teller_role.id, admin_role.id],
            created_by="admin"
        )
        
        # Remove role
        removed = rbac_manager.remove_role(user_id, teller_role.id)
        assert removed
        
        user = rbac_manager.get_user(user_id)
        assert teller_role.id not in user.roles
        assert admin_role.id in user.roles
    
    def test_assign_nonexistent_role(self, rbac_manager):
        """Test assigning non-existent role fails"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin"
        )
        
        assigned = rbac_manager.assign_role(user_id, "nonexistent")
        assert not assigned


class TestAuthentication:
    """Test authentication functionality"""
    
    def test_successful_authentication(self, rbac_manager):
        """Test successful user authentication"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        session = rbac_manager.authenticate(
            "testuser", "TestPass123!", 
            ip_address="127.0.0.1", user_agent="Test Agent"
        )
        
        assert session is not None
        assert session.user_id == user_id
        assert session.is_valid
        assert session.ip_address == "127.0.0.1"
        assert session.user_agent == "Test Agent"
        
        # Check that user's last login is updated
        user = rbac_manager.get_user(user_id)
        assert user.last_login is not None
        assert user.failed_login_attempts == 0
    
    def test_authentication_invalid_username(self, rbac_manager):
        """Test authentication with invalid username"""
        with pytest.raises(ValueError, match="Invalid credentials"):
            rbac_manager.authenticate("nonexistent", "password")
    
    def test_authentication_invalid_password(self, rbac_manager):
        """Test authentication with invalid password"""
        rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        with pytest.raises(ValueError, match="Invalid credentials"):
            rbac_manager.authenticate("testuser", "wrongpassword")
    
    def test_authentication_inactive_user(self, rbac_manager):
        """Test authentication with inactive user"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        rbac_manager.deactivate_user(user_id)
        
        with pytest.raises(ValueError, match="Account is not available"):
            rbac_manager.authenticate("testuser", "TestPass123!")
    
    def test_authentication_locked_user(self, rbac_manager):
        """Test authentication with locked user"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        rbac_manager.lock_user(user_id)
        
        with pytest.raises(ValueError, match="Account is not available"):
            rbac_manager.authenticate("testuser", "TestPass123!")
    
    def test_account_lockout_after_failed_attempts(self, rbac_manager):
        """Test account lockout after too many failed login attempts"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        # Make failed attempts (default policy: 5 attempts)
        for i in range(4):
            with pytest.raises(ValueError):
                rbac_manager.authenticate("testuser", "wrongpassword")
        
        user = rbac_manager.get_user(user_id)
        assert user.failed_login_attempts == 4
        assert not user.is_locked
        
        # Fifth attempt should lock the account
        with pytest.raises(ValueError):
            rbac_manager.authenticate("testuser", "wrongpassword")
        
        user = rbac_manager.get_user(user_id)
        assert user.is_locked
    
    def test_lock_and_unlock_user(self, rbac_manager):
        """Test manually locking and unlocking user"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        # Lock user
        locked = rbac_manager.lock_user(user_id)
        assert locked
        
        user = rbac_manager.get_user(user_id)
        assert user.is_locked
        
        # Try to authenticate
        with pytest.raises(ValueError):
            rbac_manager.authenticate("testuser", "TestPass123!")
        
        # Unlock user
        unlocked = rbac_manager.unlock_user(user_id)
        assert unlocked
        
        user = rbac_manager.get_user(user_id)
        assert not user.is_locked
        assert user.failed_login_attempts == 0
        
        # Should be able to authenticate now
        session = rbac_manager.authenticate("testuser", "TestPass123!")
        assert session is not None


class TestSessionManagement:
    """Test session management"""
    
    def test_validate_session(self, rbac_manager):
        """Test session validation"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        session = rbac_manager.authenticate("testuser", "TestPass123!")
        
        # Validate session
        user = rbac_manager.validate_session(session.id)
        assert user is not None
        assert user.id == user_id
    
    def test_validate_nonexistent_session(self, rbac_manager):
        """Test validating non-existent session"""
        user = rbac_manager.validate_session("nonexistent")
        assert user is None
    
    def test_validate_expired_session(self, rbac_manager, storage):
        """Test validating expired session"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        session = rbac_manager.authenticate("testuser", "TestPass123!")
        
        # Manually expire session
        session_data = storage.load('sessions', session.id)
        session_data['expires_at'] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        storage.save('sessions', session.id, session_data)
        
        # Should not validate
        user = rbac_manager.validate_session(session.id)
        assert user is None
    
    def test_logout(self, rbac_manager):
        """Test user logout"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        session = rbac_manager.authenticate("testuser", "TestPass123!")
        
        # Logout
        logged_out = rbac_manager.logout(session.id)
        assert logged_out
        
        # Session should no longer be valid
        user = rbac_manager.validate_session(session.id)
        assert user is None
    
    def test_logout_nonexistent_session(self, rbac_manager):
        """Test logout with non-existent session"""
        logged_out = rbac_manager.logout("nonexistent")
        assert not logged_out


class TestPasswordManagement:
    """Test password management"""
    
    def test_change_password(self, rbac_manager):
        """Test changing user password"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="OldPass123!"
        )
        
        # Change password
        changed = rbac_manager.change_password(user_id, "OldPass123!", "NewPass456@")
        assert changed
        
        # Should authenticate with new password
        session = rbac_manager.authenticate("testuser", "NewPass456@")
        assert session is not None
        
        # Should not authenticate with old password
        with pytest.raises(ValueError):
            rbac_manager.authenticate("testuser", "OldPass123!")
    
    def test_change_password_wrong_old_password(self, rbac_manager):
        """Test changing password with wrong old password"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        changed = rbac_manager.change_password(user_id, "wrongpass", "NewPass456@")
        assert not changed
    
    def test_change_password_policy_violation(self, rbac_manager):
        """Test changing password that violates policy"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        with pytest.raises(ValueError, match="Password policy violations"):
            rbac_manager.change_password(user_id, "TestPass123!", "weak")
    
    def test_reset_password(self, rbac_manager):
        """Test password reset by admin"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        temp_password = rbac_manager.reset_password(user_id, "admin")
        assert temp_password is not None
        assert len(temp_password) > 0
        
        # Should authenticate with temporary password
        session = rbac_manager.authenticate("testuser", temp_password)
        assert session is not None
        
        # Should not authenticate with old password
        with pytest.raises(ValueError):
            rbac_manager.authenticate("testuser", "TestPass123!")
    
    def test_password_history(self, rbac_manager):
        """Test password history prevents reuse"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="Password1!"
        )
        
        # Change password several times
        rbac_manager.change_password(user_id, "Password1!", "Password2!")
        rbac_manager.change_password(user_id, "Password2!", "Password3!")
        
        # Try to reuse old password
        with pytest.raises(ValueError, match="Cannot reuse recent passwords"):
            rbac_manager.change_password(user_id, "Password3!", "Password1!")


class TestPasswordPolicy:
    """Test password policy validation"""
    
    def test_password_policy_validation(self, rbac_manager):
        """Test password policy validation"""
        # Test valid password
        valid, violations = rbac_manager.validate_password("StrongPass123!")
        assert valid
        assert len(violations) == 0
        
        # Test too short
        valid, violations = rbac_manager.validate_password("Short1!")
        assert not valid
        assert "Minimum length 8" in violations
        
        # Test missing uppercase
        valid, violations = rbac_manager.validate_password("lowercase123!")
        assert not valid
        assert "Must contain uppercase letter" in violations
        
        # Test missing lowercase
        valid, violations = rbac_manager.validate_password("UPPERCASE123!")
        assert not valid
        assert "Must contain lowercase letter" in violations
        
        # Test missing digit
        valid, violations = rbac_manager.validate_password("NoDigitsHere!")
        assert not valid
        assert "Must contain digit" in violations
        
        # Test missing special character
        valid, violations = rbac_manager.validate_password("NoSpecial123")
        assert not valid
        assert "Must contain special character" in violations
    
    def test_custom_password_policy(self, rbac_manager):
        """Test setting custom password policy"""
        custom_policy = PasswordPolicy(
            min_length=12,
            require_uppercase=False,
            require_lowercase=True,
            require_digit=True,
            require_special=False
        )
        
        rbac_manager.set_password_policy(custom_policy)
        
        # Test with new policy
        valid, violations = rbac_manager.validate_password("lowercase123")
        assert valid  # Should pass with new policy
        
        # Test minimum length
        valid, violations = rbac_manager.validate_password("short123")
        assert not valid
        assert "Minimum length 12" in violations


class TestAuthorization:
    """Test authorization and permission checking"""
    
    def test_check_permission(self, rbac_manager):
        """Test checking single permission"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[teller_role.id],
            created_by="admin"
        )
        
        # Should have teller permissions
        assert rbac_manager.check_permission(user_id, Permission.VIEW_ACCOUNT)
        assert rbac_manager.check_permission(user_id, Permission.CREATE_TRANSACTION)
        
        # Should not have admin permissions
        assert not rbac_manager.check_permission(user_id, Permission.MANAGE_USERS)
    
    def test_check_permissions_all(self, rbac_manager):
        """Test checking multiple permissions (all required)"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[teller_role.id],
            created_by="admin"
        )
        
        # Should have all teller permissions
        teller_permissions = {Permission.VIEW_ACCOUNT, Permission.CREATE_TRANSACTION}
        assert rbac_manager.check_permissions(user_id, teller_permissions)
        
        # Should not have admin permissions
        admin_permissions = {Permission.MANAGE_USERS, Permission.SYSTEM_CONFIG}
        assert not rbac_manager.check_permissions(user_id, admin_permissions)
        
        # Mixed permissions
        mixed_permissions = {Permission.VIEW_ACCOUNT, Permission.MANAGE_USERS}
        assert not rbac_manager.check_permissions(user_id, mixed_permissions)
    
    def test_check_any_permission(self, rbac_manager):
        """Test checking multiple permissions (any required)"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[teller_role.id],
            created_by="admin"
        )
        
        # Should have some teller permissions
        mixed_permissions = {Permission.VIEW_ACCOUNT, Permission.MANAGE_USERS}
        assert rbac_manager.check_any_permission(user_id, mixed_permissions)
        
        # Should not have any admin permissions
        admin_permissions = {Permission.MANAGE_USERS, Permission.SYSTEM_CONFIG}
        assert not rbac_manager.check_any_permission(user_id, admin_permissions)
    
    def test_get_user_permissions(self, rbac_manager):
        """Test getting all user permissions"""
        roles = rbac_manager.list_roles()
        teller_role = next(r for r in roles if r.name == "TELLER")
        auditor_role = next(r for r in roles if r.name == "AUDITOR")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[teller_role.id, auditor_role.id],
            created_by="admin"
        )
        
        permissions = rbac_manager.get_user_permissions(user_id)
        
        # Should have union of both role permissions
        expected_permissions = teller_role.permissions | auditor_role.permissions
        assert permissions == expected_permissions
    
    def test_check_amount_limit(self, rbac_manager):
        """Test checking amount limits per role"""
        # Create role with transaction limit
        permissions = {Permission.CREATE_TRANSACTION}
        max_amount = Money(Decimal("1000.00"), Currency.USD)
        
        role_id = rbac_manager.create_role(
            name="Limited Teller",
            permissions=permissions,
            max_transaction_amount=max_amount
        )
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[role_id],
            created_by="admin"
        )
        
        # Should allow transaction within limit
        small_amount = Money(Decimal("500.00"), Currency.USD)
        assert rbac_manager.check_amount_limit(user_id, small_amount, 'transaction')
        
        # Should not allow transaction over limit
        large_amount = Money(Decimal("2000.00"), Currency.USD)
        assert not rbac_manager.check_amount_limit(user_id, large_amount, 'transaction')
    
    def test_permission_check_inactive_user(self, rbac_manager):
        """Test permission check for inactive user returns False"""
        roles = rbac_manager.list_roles()
        admin_role = next(r for r in roles if r.name == "ADMIN")
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[admin_role.id],
            created_by="admin"
        )
        
        # Deactivate user
        rbac_manager.deactivate_user(user_id)
        
        # Should not have any permissions
        assert not rbac_manager.check_permission(user_id, Permission.MANAGE_USERS)
        permissions = rbac_manager.get_user_permissions(user_id)
        assert len(permissions) == 0


class TestAuditTrail:
    """Test audit trail for RBAC events"""
    
    def test_user_creation_audited(self, rbac_manager, audit):
        """Test that user creation is audited"""
        initial_events = len(audit.get_all_events())
        
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin"
        )
        
        events = audit.get_all_events()
        assert len(events) > initial_events
        
        # Find the user creation event
        user_events = [e for e in events if e.entity_id == user_id and e.entity_type == 'user']
        assert len(user_events) > 0
    
    def test_authentication_audited(self, rbac_manager, audit):
        """Test that authentication attempts are audited"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        initial_events = len(audit.get_all_events())
        
        # Successful login
        session = rbac_manager.authenticate("testuser", "TestPass123!")
        
        events = audit.get_all_events()
        assert len(events) > initial_events
        
        # Find authentication success event
        auth_events = [e for e in events 
                      if e.entity_type == 'authentication' and 
                      e.metadata.get('action') == 'login_success']
        assert len(auth_events) > 0
        
        # Failed login
        initial_events = len(events)
        with pytest.raises(ValueError):
            rbac_manager.authenticate("testuser", "wrongpassword")
        
        events = audit.get_all_events()
        assert len(events) > initial_events
        
        # Find authentication failure event
        fail_events = [e for e in events 
                      if e.entity_type == 'authentication' and 
                      e.metadata.get('action') == 'login_failed']
        assert len(fail_events) > 0


class TestUserDeactivationBlocksAuth:
    """Test that deactivated users cannot authenticate"""
    
    def test_deactivated_user_cannot_login(self, rbac_manager):
        """Test that deactivated user cannot authenticate"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        # Should be able to authenticate initially
        session = rbac_manager.authenticate("testuser", "TestPass123!")
        assert session is not None
        
        # Deactivate user
        rbac_manager.deactivate_user(user_id)
        
        # Should not be able to authenticate anymore
        with pytest.raises(ValueError, match="Account is not available"):
            rbac_manager.authenticate("testuser", "TestPass123!")
    
    def test_deactivation_invalidates_sessions(self, rbac_manager):
        """Test that deactivating user invalidates existing sessions"""
        user_id = rbac_manager.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Test User",
            roles=[],
            created_by="admin",
            password="TestPass123!"
        )
        
        # Create session
        session = rbac_manager.authenticate("testuser", "TestPass123!")
        assert rbac_manager.validate_session(session.id) is not None
        
        # Deactivate user
        rbac_manager.deactivate_user(user_id)
        
        # Session should no longer be valid
        assert rbac_manager.validate_session(session.id) is None