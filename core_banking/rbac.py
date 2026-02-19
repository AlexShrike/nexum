"""
Role-Based Access Control (RBAC) & Admin Module

User management, roles, permissions, session management with comprehensive security.
Inspired by Oradian's "Administration Control Module" and "Security Controls and MFA."
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from .audit import AuditEventType, AuditTrail
from .currency import Money
from .storage import StorageInterface, StorageRecord


class Permission(Enum):
    """System permissions"""
    # Account permissions
    CREATE_ACCOUNT = "create_account"
    VIEW_ACCOUNT = "view_account"
    MODIFY_ACCOUNT = "modify_account"
    CLOSE_ACCOUNT = "close_account"

    # Transaction permissions
    CREATE_TRANSACTION = "create_transaction"
    APPROVE_TRANSACTION = "approve_transaction"
    REVERSE_TRANSACTION = "reverse_transaction"
    VIEW_TRANSACTION = "view_transaction"

    # Loan permissions
    CREATE_LOAN = "create_loan"
    APPROVE_LOAN = "approve_loan"
    DISBURSE_LOAN = "disburse_loan"
    VIEW_LOAN = "view_loan"
    WRITE_OFF_LOAN = "write_off_loan"

    # Credit permissions
    CREATE_CREDIT_LINE = "create_credit_line"
    MODIFY_CREDIT_LIMIT = "modify_credit_limit"
    VIEW_CREDIT_LINE = "view_credit_line"

    # Customer permissions
    CREATE_CUSTOMER = "create_customer"
    VIEW_CUSTOMER = "view_customer"
    MODIFY_CUSTOMER = "modify_customer"
    DELETE_CUSTOMER = "delete_customer"

    # Product permissions
    CREATE_PRODUCT = "create_product"
    MODIFY_PRODUCT = "modify_product"
    ACTIVATE_PRODUCT = "activate_product"
    RETIRE_PRODUCT = "retire_product"

    # Report permissions
    VIEW_REPORTS = "view_reports"
    CREATE_REPORTS = "create_reports"
    EXPORT_REPORTS = "export_reports"

    # Workflow permissions
    START_WORKFLOW = "start_workflow"
    APPROVE_WORKFLOW_STEP = "approve_workflow_step"

    # Admin permissions
    MANAGE_USERS = "manage_users"
    MANAGE_ROLES = "manage_roles"
    VIEW_AUDIT_LOG = "view_audit_log"
    SYSTEM_CONFIG = "system_config"

    # Collection permissions
    VIEW_COLLECTIONS = "view_collections"
    MANAGE_COLLECTIONS = "manage_collections"
    ASSIGN_COLLECTORS = "assign_collectors"


@dataclass
class Role(StorageRecord):
    """Role with permissions and limits"""
    name: str
    description: str
    permissions: Set[Permission] = field(default_factory=set)
    is_system_role: bool = False
    max_transaction_amount: Optional[Money] = None
    max_approval_amount: Optional[Money] = None

    def has_permission(self, permission: Permission) -> bool:
        """Check if role has a specific permission"""
        return permission in self.permissions

    def has_any_permission(self, permissions: Set[Permission]) -> bool:
        """Check if role has any of the specified permissions"""
        return bool(self.permissions & permissions)

    def has_all_permissions(self, permissions: Set[Permission]) -> bool:
        """Check if role has all of the specified permissions"""
        return permissions.issubset(self.permissions)


@dataclass
class User(StorageRecord):
    """System user with roles and authentication info"""
    username: str
    email: str
    full_name: str
    roles: List[str] = field(default_factory=list)  # role IDs
    is_active: bool = True
    is_locked: bool = False
    failed_login_attempts: int = 0
    last_login: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None
    branch_id: Optional[str] = None
    created_by: str = ""
    mfa_enabled: bool = False
    mfa_secret: Optional[str] = None
    password_hash: Optional[str] = None
    password_salt: Optional[str] = None
    password_history: List[str] = field(default_factory=list)  # hash history

    @property
    def is_available(self) -> bool:
        """Check if user can authenticate (active and not locked)"""
        return self.is_active and not self.is_locked


@dataclass
class Session(StorageRecord):
    """User authentication session"""
    user_id: str
    expires_at: datetime
    is_active: bool = True
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if session is still valid"""
        return (self.is_active and
                self.expires_at > datetime.now(timezone.utc))


@dataclass
class PasswordPolicy:
    """Password policy configuration"""
    min_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True
    max_age_days: int = 90
    history_count: int = 5
    max_failed_attempts: int = 5
    lockout_duration_minutes: int = 30


class RBACManager:
    """Role-Based Access Control manager"""

    def __init__(self, storage: StorageInterface, audit_manager: Optional[AuditTrail] = None):
        self.storage = storage
        self.audit = audit_manager or AuditTrail(storage)
        self.password_policy = PasswordPolicy()
        self._create_system_roles()

    # Role Management

    def create_role(self, name: str, permissions: Set[Permission],
                   description: Optional[str] = None,
                   max_transaction_amount: Optional[Money] = None,
                   max_approval_amount: Optional[Money] = None) -> str:
        """Create a new role"""
        role_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        role = Role(
            id=role_id,
            created_at=now,
            updated_at=now,
            name=name,
            description=description or "",
            permissions=permissions,
            is_system_role=False,
            max_transaction_amount=max_transaction_amount,
            max_approval_amount=max_approval_amount
        )

        # Convert permissions to strings for storage
        data = role.to_dict()
        data['permissions'] = [p.value for p in permissions]
        if max_transaction_amount:
            data['max_transaction_amount'] = {
                'amount': str(max_transaction_amount.amount),
                'currency': max_transaction_amount.currency.value
            }
        if max_approval_amount:
            data['max_approval_amount'] = {
                'amount': str(max_approval_amount.amount),
                'currency': max_approval_amount.currency.value
            }

        self.storage.save('roles', role_id, data)

        if self.audit:
            self.audit.log_event(
                AuditEventType.SYSTEM_START,  # Using available event type
                'role',
                role_id,
                {'action': 'role_created', 'name': name, 'permissions': len(permissions)},
                'system'
            )

        return role_id

    def get_role(self, role_id: str) -> Optional[Role]:
        """Get role by ID"""
        data = self.storage.load('roles', role_id)
        if not data:
            return None

        # Convert permissions back from strings
        permissions = {Permission(p) for p in data.get('permissions', [])}
        data['permissions'] = permissions

        # Convert money amounts
        if data.get('max_transaction_amount'):
            from .currency import Currency
            amt_data = data['max_transaction_amount']
            # Handle both string and tuple formats for currency
            currency_value = amt_data['currency']
            if isinstance(currency_value, list):
                currency_code = currency_value[0]  # Take first element (code)
            else:
                currency_code = currency_value
            data['max_transaction_amount'] = Money(
                Decimal(amt_data['amount']),
                Currency[currency_code]  # Use bracket notation for enum lookup
            )

        if data.get('max_approval_amount'):
            from .currency import Currency
            amt_data = data['max_approval_amount']
            # Handle both string and tuple formats for currency
            currency_value = amt_data['currency']
            if isinstance(currency_value, list):
                currency_code = currency_value[0]  # Take first element (code)
            else:
                currency_code = currency_value
            data['max_approval_amount'] = Money(
                Decimal(amt_data['amount']),
                Currency[currency_code]  # Use bracket notation for enum lookup
            )

        # Convert dates
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])

        return Role(**data)

    def list_roles(self) -> List[Role]:
        """List all roles"""
        all_data = self.storage.load_all('roles')
        roles = []
        for data in all_data:
            role = self.get_role(data['id'])
            if role:
                roles.append(role)
        return sorted(roles, key=lambda r: r.name)

    def update_role(self, role_id: str, permissions: Optional[Set[Permission]] = None,
                   description: Optional[str] = None,
                   max_transaction_amount: Optional[Money] = None,
                   max_approval_amount: Optional[Money] = None) -> bool:
        """Update role properties"""
        role = self.get_role(role_id)
        if not role:
            return False

        if role.is_system_role:
            # System roles cannot be modified
            return False

        if permissions is not None:
            role.permissions = permissions
        if description is not None:
            role.description = description
        if max_transaction_amount is not None:
            role.max_transaction_amount = max_transaction_amount
        if max_approval_amount is not None:
            role.max_approval_amount = max_approval_amount

        role.updated_at = datetime.now(timezone.utc)

        # Save role
        data = role.to_dict()
        data['permissions'] = [p.value for p in role.permissions]
        if role.max_transaction_amount:
            data['max_transaction_amount'] = {
                'amount': str(role.max_transaction_amount.amount),
                'currency': role.max_transaction_amount.currency.value
            }
        if role.max_approval_amount:
            data['max_approval_amount'] = {
                'amount': str(role.max_approval_amount.amount),
                'currency': role.max_approval_amount.currency.value
            }

        self.storage.save('roles', role_id, data)

        if self.audit:
            self.audit.log_event(
                AuditEventType.SYSTEM_START,  # Using available event type
                'role',
                role_id,
                {'action': 'role_updated'},
                'system'
            )

        return True

    def delete_role(self, role_id: str) -> bool:
        """Delete a role (if not system role and no users assigned)"""
        role = self.get_role(role_id)
        if not role or role.is_system_role:
            return False

        # Check if any users have this role
        users_with_role = self.storage.find('users', {})
        for user_data in users_with_role:
            if role_id in user_data.get('roles', []):
                return False  # Cannot delete role with assigned users

        deleted = self.storage.delete('roles', role_id)

        if deleted and self.audit:
            self.audit.log_event(
                AuditEventType.SYSTEM_START,  # Using available event type
                'role',
                role_id,
                {'action': 'role_deleted', 'name': role.name},
                'system'
            )

        return deleted

    # User Management

    def create_user(self, username: str, email: str, full_name: str,
                   roles: List[str], created_by: str, password: Optional[str] = None) -> str:
        """Create a new user"""
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        user = User(
            id=user_id,
            created_at=now,
            updated_at=now,
            username=username,
            email=email,
            full_name=full_name,
            roles=roles,
            created_by=created_by
        )

        # Set password if provided
        if password:
            self._set_user_password(user, password)
            user.password_changed_at = now

        # Save user
        data = user.to_dict()
        self.storage.save('users', user_id, data)

        if self.audit:
            self.audit.log_event(
                AuditEventType.CUSTOMER_CREATED,  # Using available event type
                'user',
                user_id,
                {'username': username, 'email': email, 'roles': len(roles)},
                created_by
            )

        return user_id

    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        data = self.storage.load('users', user_id)
        if not data:
            return None

        # Convert dates
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if data.get('last_login'):
            data['last_login'] = datetime.fromisoformat(data['last_login'])
        if data.get('password_changed_at'):
            data['password_changed_at'] = datetime.fromisoformat(data['password_changed_at'])

        return User(**data)

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        users = self.storage.find('users', {'username': username})
        if not users:
            return None
        return self.get_user(users[0]['id'])

    def list_users(self, role: Optional[str] = None, is_active: Optional[bool] = None) -> List[User]:
        """List users with optional filters"""
        all_data = self.storage.load_all('users')
        users = []

        for data in all_data:
            user = self.get_user(data['id'])
            if not user:
                continue

            if role and role not in user.roles:
                continue
            if is_active is not None and user.is_active != is_active:
                continue

            users.append(user)

        return sorted(users, key=lambda u: u.username)

    def update_user(self, user_id: str, email: Optional[str] = None,
                   full_name: Optional[str] = None, branch_id: Optional[str] = None) -> bool:
        """Update user properties"""
        user = self.get_user(user_id)
        if not user:
            return False

        if email is not None:
            user.email = email
        if full_name is not None:
            user.full_name = full_name
        if branch_id is not None:
            user.branch_id = branch_id

        user.updated_at = datetime.now(timezone.utc)

        data = user.to_dict()
        self.storage.save('users', user_id, data)

        return True

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user"""
        user = self.get_user(user_id)
        if not user:
            return False

        user.is_active = False
        user.updated_at = datetime.now(timezone.utc)

        # Invalidate all user sessions
        self._invalidate_user_sessions(user_id)

        data = user.to_dict()
        self.storage.save('users', user_id, data)

        return True

    def activate_user(self, user_id: str) -> bool:
        """Activate a user"""
        user = self.get_user(user_id)
        if not user:
            return False

        user.is_active = True
        user.is_locked = False  # Also unlock when activating
        user.failed_login_attempts = 0
        user.updated_at = datetime.now(timezone.utc)

        data = user.to_dict()
        self.storage.save('users', user_id, data)

        return True

    def assign_role(self, user_id: str, role_id: str) -> bool:
        """Assign role to user"""
        user = self.get_user(user_id)
        role = self.get_role(role_id)

        if not user or not role:
            return False

        if role_id not in user.roles:
            user.roles.append(role_id)
            user.updated_at = datetime.now(timezone.utc)

            data = user.to_dict()
            self.storage.save('users', user_id, data)

        return True

    def remove_role(self, user_id: str, role_id: str) -> bool:
        """Remove role from user"""
        user = self.get_user(user_id)
        if not user:
            return False

        if role_id in user.roles:
            user.roles.remove(role_id)
            user.updated_at = datetime.now(timezone.utc)

            data = user.to_dict()
            self.storage.save('users', user_id, data)

        return True

    def lock_user(self, user_id: str) -> bool:
        """Lock user account"""
        user = self.get_user(user_id)
        if not user:
            return False

        user.is_locked = True
        user.updated_at = datetime.now(timezone.utc)

        # Invalidate all user sessions
        self._invalidate_user_sessions(user_id)

        data = user.to_dict()
        self.storage.save('users', user_id, data)

        return True

    def unlock_user(self, user_id: str) -> bool:
        """Unlock user account"""
        user = self.get_user(user_id)
        if not user:
            return False

        user.is_locked = False
        user.failed_login_attempts = 0
        user.updated_at = datetime.now(timezone.utc)

        data = user.to_dict()
        self.storage.save('users', user_id, data)

        return True

    # Authentication

    def authenticate(self, username: str, password: str, ip_address: Optional[str] = None,
                    user_agent: Optional[str] = None) -> Session:
        """Authenticate user and create session"""
        user = self.get_user_by_username(username)

        if not user:
            if self.audit:
                self.audit.log_event(
                    AuditEventType.SYSTEM_START,  # Using available event type
                    'authentication',
                    username,
                    {'action': 'login_failed', 'reason': 'user_not_found'},
                    username
                )
            raise ValueError("Invalid credentials")

        # Check if user can authenticate
        if not user.is_available:
            if self.audit:
                self.audit.log_event(
                    AuditEventType.SYSTEM_START,
                    'authentication',
                    user.id,
                    {'action': 'login_failed', 'reason': 'user_not_available'},
                    username
                )
            raise ValueError("Account is not available")

        # Verify password
        if not self._verify_password(user, password):
            # Increment failed attempts
            user.failed_login_attempts += 1

            # Lock account if too many failed attempts
            if user.failed_login_attempts >= self.password_policy.max_failed_attempts:
                user.is_locked = True

            user.updated_at = datetime.now(timezone.utc)
            data = user.to_dict()
            self.storage.save('users', user.id, data)

            if self.audit:
                self.audit.log_event(
                    AuditEventType.SYSTEM_START,
                    'authentication',
                    user.id,
                    {'action': 'login_failed', 'reason': 'invalid_password'},
                    username
                )
            raise ValueError("Invalid credentials")

        # Reset failed attempts on successful auth
        user.failed_login_attempts = 0
        user.last_login = datetime.now(timezone.utc)
        user.updated_at = user.last_login

        data = user.to_dict()
        self.storage.save('users', user.id, data)

        # Create session
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=8)  # 8-hour session

        session = Session(
            id=session_id,
            created_at=now,
            updated_at=now,
            user_id=user.id,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )

        data = session.to_dict()
        self.storage.save('sessions', session_id, data)

        if self.audit:
            self.audit.log_event(
                AuditEventType.SYSTEM_START,
                'authentication',
                user.id,
                {'action': 'login_success', 'session_id': session_id},
                username
            )

        return session

    def validate_session(self, session_id: str) -> Optional[User]:
        """Validate session and return user if valid"""
        session_data = self.storage.load('sessions', session_id)
        if not session_data:
            return None

        # Convert dates
        session_data['created_at'] = datetime.fromisoformat(session_data['created_at'])
        session_data['updated_at'] = datetime.fromisoformat(session_data['updated_at'])
        session_data['expires_at'] = datetime.fromisoformat(session_data['expires_at'])

        session = Session(**session_data)

        if not session.is_valid:
            return None

        user = self.get_user(session.user_id)
        if not user or not user.is_available:
            return None

        return user

    def logout(self, session_id: str) -> bool:
        """Logout user (invalidate session)"""
        session_data = self.storage.load('sessions', session_id)
        if not session_data:
            return False

        session_data['is_active'] = False
        session_data['updated_at'] = datetime.now(timezone.utc).isoformat()

        self.storage.save('sessions', session_id, session_data)

        if self.audit:
            self.audit.log_event(
                AuditEventType.SYSTEM_START,
                'authentication',
                session_data['user_id'],
                {'action': 'logout', 'session_id': session_id},
                session_data['user_id']
            )

        return True

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        """Change user password"""
        user = self.get_user(user_id)
        if not user:
            return False

        # Verify old password
        if not self._verify_password(user, old_password):
            return False

        # Validate new password
        is_valid, violations = self.validate_password(new_password)
        if not is_valid:
            raise ValueError(f"Password policy violations: {', '.join(violations)}")

        # Check password history (including current password)
        new_hash = self._hash_password(new_password, user.password_salt or self._generate_salt())
        if user.password_hash and new_hash == user.password_hash:
            raise ValueError("Cannot reuse recent passwords")
        if new_hash in user.password_history:
            raise ValueError("Cannot reuse recent passwords")

        # Add current password to history before changing it
        if user.password_hash and user.password_hash not in user.password_history:
            user.password_history.append(user.password_hash)

        # Keep only last N passwords in history
        if len(user.password_history) > self.password_policy.history_count:
            user.password_history = user.password_history[-self.password_policy.history_count:]

        # Update password
        self._set_user_password(user, new_password)
        user.password_changed_at = datetime.now(timezone.utc)
        user.updated_at = user.password_changed_at

        data = user.to_dict()
        self.storage.save('users', user_id, data)

        return True

    def reset_password(self, user_id: str, admin_user_id: str) -> str:
        """Reset user password (admin function) - returns temporary password"""
        user = self.get_user(user_id)
        if not user:
            raise ValueError("User not found")

        # Generate temporary password
        temp_password = self._generate_temp_password()

        # Set password
        self._set_user_password(user, temp_password)
        user.password_changed_at = datetime.now(timezone.utc)
        user.updated_at = user.password_changed_at

        data = user.to_dict()
        self.storage.save('users', user_id, data)

        if self.audit:
            self.audit.log_event(
                AuditEventType.SYSTEM_START,
                'user',
                user_id,
                {'action': 'password_reset'},
                admin_user_id
            )

        return temp_password

    # Authorization

    def check_permission(self, user_id: str, permission: Permission) -> bool:
        """Check if user has specific permission"""
        user = self.get_user(user_id)
        if not user or not user.is_available:
            return False

        user_permissions = self.get_user_permissions(user_id)
        return permission in user_permissions

    def check_permissions(self, user_id: str, permissions: Set[Permission]) -> bool:
        """Check if user has ALL specified permissions"""
        user_permissions = self.get_user_permissions(user_id)
        return permissions.issubset(user_permissions)

    def check_any_permission(self, user_id: str, permissions: Set[Permission]) -> bool:
        """Check if user has ANY of the specified permissions"""
        user_permissions = self.get_user_permissions(user_id)
        return bool(user_permissions & permissions)

    def get_user_permissions(self, user_id: str) -> Set[Permission]:
        """Get all permissions for user from all their roles"""
        user = self.get_user(user_id)
        if not user or not user.is_available:
            return set()

        all_permissions = set()

        for role_id in user.roles:
            role = self.get_role(role_id)
            if role:
                all_permissions.update(role.permissions)

        return all_permissions

    def check_amount_limit(self, user_id: str, amount: Money, limit_type: str = 'transaction') -> bool:
        """Check if amount is within user's limits"""
        user = self.get_user(user_id)
        if not user or not user.is_available:
            return False

        for role_id in user.roles:
            role = self.get_role(role_id)
            if not role:
                continue

            # Check appropriate limit
            if limit_type == 'transaction' and role.max_transaction_amount:
                if amount.amount > role.max_transaction_amount.amount:
                    return False
            elif limit_type == 'approval' and role.max_approval_amount:
                if amount.amount > role.max_approval_amount.amount:
                    return False

        return True

    # Password Policy

    def set_password_policy(self, policy: PasswordPolicy):
        """Set password policy"""
        self.password_policy = policy

    def validate_password(self, password: str) -> Tuple[bool, List[str]]:
        """Validate password against policy"""
        violations = []

        if len(password) < self.password_policy.min_length:
            violations.append(f"Minimum length {self.password_policy.min_length}")

        if self.password_policy.require_uppercase and not any(c.isupper() for c in password):
            violations.append("Must contain uppercase letter")

        if self.password_policy.require_lowercase and not any(c.islower() for c in password):
            violations.append("Must contain lowercase letter")

        if self.password_policy.require_digit and not any(c.isdigit() for c in password):
            violations.append("Must contain digit")

        if self.password_policy.require_special:
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if not any(c in special_chars for c in password):
                violations.append("Must contain special character")

        return len(violations) == 0, violations

    # Private helper methods

    def _create_system_roles(self):
        """Create built-in system roles"""
        system_roles = {
            "ADMIN": {
                "permissions": set(Permission),  # All permissions
                "description": "System administrator with full access"
            },
            "BRANCH_MANAGER": {
                "permissions": {
                    Permission.VIEW_ACCOUNT, Permission.MODIFY_ACCOUNT, Permission.CREATE_ACCOUNT,
                    Permission.VIEW_CUSTOMER, Permission.MODIFY_CUSTOMER, Permission.CREATE_CUSTOMER,
                    Permission.VIEW_TRANSACTION, Permission.CREATE_TRANSACTION, Permission.APPROVE_TRANSACTION,
                    Permission.VIEW_LOAN, Permission.CREATE_LOAN, Permission.APPROVE_LOAN,
                    Permission.VIEW_REPORTS, Permission.CREATE_REPORTS,
                    Permission.START_WORKFLOW, Permission.APPROVE_WORKFLOW_STEP
                },
                "description": "Branch manager with operational oversight"
            },
            "LOAN_OFFICER": {
                "permissions": {
                    Permission.VIEW_CUSTOMER, Permission.CREATE_CUSTOMER, Permission.MODIFY_CUSTOMER,
                    Permission.VIEW_LOAN, Permission.CREATE_LOAN,
                    Permission.VIEW_ACCOUNT, Permission.CREATE_ACCOUNT,
                    Permission.START_WORKFLOW
                },
                "description": "Loan officer for loan origination"
            },
            "TELLER": {
                "permissions": {
                    Permission.VIEW_ACCOUNT, Permission.VIEW_CUSTOMER,
                    Permission.CREATE_TRANSACTION, Permission.VIEW_TRANSACTION
                },
                "description": "Teller for basic transactions"
            },
            "AUDITOR": {
                "permissions": {
                    Permission.VIEW_ACCOUNT, Permission.VIEW_CUSTOMER, Permission.VIEW_TRANSACTION,
                    Permission.VIEW_LOAN, Permission.VIEW_CREDIT_LINE,
                    Permission.VIEW_REPORTS, Permission.VIEW_AUDIT_LOG
                },
                "description": "Auditor with read-only access"
            },
            "COMPLIANCE_OFFICER": {
                "permissions": {
                    Permission.VIEW_ACCOUNT, Permission.VIEW_CUSTOMER, Permission.VIEW_TRANSACTION,
                    Permission.VIEW_REPORTS, Permission.VIEW_AUDIT_LOG,
                    Permission.VIEW_COLLECTIONS, Permission.MANAGE_COLLECTIONS
                },
                "description": "Compliance officer for regulatory oversight"
            },
            "COLLECTOR": {
                "permissions": {
                    Permission.VIEW_COLLECTIONS, Permission.MANAGE_COLLECTIONS,
                    Permission.VIEW_LOAN, Permission.VIEW_CUSTOMER
                },
                "description": "Collections specialist"
            },
            "READ_ONLY": {
                "permissions": {
                    Permission.VIEW_ACCOUNT, Permission.VIEW_CUSTOMER, Permission.VIEW_TRANSACTION,
                    Permission.VIEW_LOAN, Permission.VIEW_CREDIT_LINE, Permission.VIEW_REPORTS
                },
                "description": "Read-only access for reporting"
            }
        }

        for role_name, role_config in system_roles.items():
            # Check if role already exists
            existing_roles = self.storage.find('roles', {'name': role_name})
            if existing_roles:
                continue

            role_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            role = Role(
                id=role_id,
                created_at=now,
                updated_at=now,
                name=role_name,
                description=role_config["description"],
                permissions=role_config["permissions"],
                is_system_role=True
            )

            # Save role
            data = role.to_dict()
            data['permissions'] = [p.value for p in role.permissions]

            self.storage.save('roles', role_id, data)

    def _generate_salt(self) -> str:
        """Generate random salt for password hashing"""
        return secrets.token_hex(16)

    def _hash_password(self, password: str, salt: str) -> str:
        """Hash password with salt using scrypt (more secure than SHA-256)"""
        # Use scrypt for stronger password hashing
        return hashlib.scrypt(
            password.encode(), 
            salt=salt.encode(), 
            n=16384, r=8, p=1
        ).hex()

    def _hash_password_legacy(self, password: str, salt: str) -> str:
        """Legacy SHA-256 password hashing for backward compatibility"""
        return hashlib.sha256((password + salt).encode()).hexdigest()

    def _set_user_password(self, user: User, password: str):
        """Set user password with proper hashing"""
        if not user.password_salt:
            user.password_salt = self._generate_salt()

        user.password_hash = self._hash_password(password, user.password_salt)

    def _verify_password(self, user: User, password: str) -> bool:
        """Verify password against stored hash with legacy support"""
        if not user.password_hash or not user.password_salt:
            return False

        # Try new scrypt hashing first
        expected_hash_new = self._hash_password(password, user.password_salt)
        if user.password_hash == expected_hash_new:
            return True
            
        # Fall back to legacy SHA-256 for existing passwords
        expected_hash_legacy = self._hash_password_legacy(password, user.password_salt)
        if user.password_hash == expected_hash_legacy:
            # Re-hash with scrypt for security upgrade
            self._set_user_password(user, password)
            self.save_user(user)
            return True
            
        return False

    def _generate_temp_password(self) -> str:
        """Generate temporary password"""
        return secrets.token_urlsafe(12)

    def _invalidate_user_sessions(self, user_id: str):
        """Invalidate all sessions for a user"""
        all_sessions = self.storage.load_all('sessions')
        for session_data in all_sessions:
            if session_data.get('user_id') == user_id and session_data.get('is_active'):
                session_data['is_active'] = False
                session_data['updated_at'] = datetime.now(timezone.utc).isoformat()
                self.storage.save('sessions', session_data['id'], session_data)