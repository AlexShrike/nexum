# RBAC (Role-Based Access Control)

The RBAC module provides comprehensive authentication, authorization, and user management capabilities for the banking system. It implements enterprise-grade security controls with role-based permissions, session management, and audit logging.

## Overview

The RBAC system manages:

- **User Management**: Create and manage user accounts with full lifecycle support
- **Role-Based Access**: Define roles with granular permissions
- **Session Management**: Secure session handling with timeout and validation
- **Password Security**: Strong password policies and secure storage
- **Audit Logging**: Complete audit trail of all security events

## Key Concepts

### Roles
Predefined roles with specific permission sets:
- **SUPER_ADMIN**: Full system access
- **ADMIN**: Administrative operations
- **MANAGER**: Department management
- **OFFICER**: Daily operations
- **TELLER**: Basic transactions
- **COMPLIANCE**: Compliance operations
- **AUDITOR**: Read-only access
- **GUEST**: Limited read access

### Permissions
Granular permissions controlling access to specific operations:
- CREATE, READ, UPDATE, DELETE operations
- Module-specific permissions
- Transaction limits and restrictions
- Administrative functions

### Sessions
Secure session management with:
- JWT tokens with configurable expiration (default: 24 hours)
- Session validation and renewal
- Concurrent session limits  
- Automatic timeout handling
- Bearer token authentication for API access

## Core Classes

### User

Represents a system user with authentication credentials:

```python
from core_banking.rbac import User, UserStatus
from datetime import datetime, timezone
from typing import List, Optional

@dataclass
class User(StorageRecord):
    username: str
    email: str
    first_name: str
    last_name: str
    
    # Authentication
    password_hash: str
    salt: str
    
    # Status and security
    status: UserStatus = UserStatus.ACTIVE
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    last_login: Optional[datetime] = None
    password_expires: Optional[datetime] = None
    
    # Role assignments
    roles: List[str] = field(default_factory=list)
    
    # Security settings
    require_password_change: bool = False
    two_factor_enabled: bool = False
    two_factor_secret: Optional[str] = None
    
    # Audit fields
    created_by: Optional[str] = None
    last_modified_by: Optional[str] = None
    
    def __post_init__(self):
        super().__post_init__()
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc)
    
    @property
    def is_locked(self) -> bool:
        """Check if user account is locked"""
        if self.status == UserStatus.LOCKED:
            return True
        
        if self.locked_until and datetime.now(timezone.utc) < self.locked_until:
            return True
        
        return False
    
    @property
    def is_password_expired(self) -> bool:
        """Check if password has expired"""
        if not self.password_expires:
            return False
        
        return datetime.now(timezone.utc) > self.password_expires
    
    @property
    def full_name(self) -> str:
        """Get user's full name"""
        return f"{self.first_name} {self.last_name}"

# Example user creation
user = User(
    username="john.officer",
    email="john.officer@nexumbank.com",
    first_name="John",
    last_name="Officer",
    password_hash="hashed_password_here",
    salt="random_salt_here",
    roles=["OFFICER"],
    created_by="admin"
)
```

### Role

Defines a role with associated permissions:

```python
from core_banking.rbac import Role, Permission

@dataclass
class Role(StorageRecord):
    name: str
    display_name: str
    description: str
    
    # Permissions
    permissions: List[str] = field(default_factory=list)
    
    # Role hierarchy
    parent_roles: List[str] = field(default_factory=list)  # Inherit from parent roles
    
    # Configuration
    is_system_role: bool = False  # Cannot be deleted if True
    max_sessions: int = 5  # Maximum concurrent sessions
    session_timeout_minutes: int = 480  # 8 hours
    
    # Transaction limits (optional)
    daily_transaction_limit: Optional[Money] = None
    single_transaction_limit: Optional[Money] = None
    
    def get_effective_permissions(self, role_manager) -> List[str]:
        """Get all permissions including inherited from parent roles"""
        
        effective_permissions = set(self.permissions)
        
        # Add permissions from parent roles
        for parent_role_name in self.parent_roles:
            parent_role = role_manager.get_role_by_name(parent_role_name)
            if parent_role:
                parent_permissions = parent_role.get_effective_permissions(role_manager)
                effective_permissions.update(parent_permissions)
        
        return list(effective_permissions)

# Example role definition
officer_role = Role(
    name="OFFICER",
    display_name="Banking Officer",
    description="Daily banking operations with customer service capabilities",
    permissions=[
        "customer.read", "customer.update", "customer.kyc.update",
        "account.read", "account.create", "account.update",
        "transaction.read", "transaction.deposit", "transaction.withdraw", "transaction.transfer",
        "loan.read", "loan.payment",
        "credit.read", "credit.payment",
        "report.account_statement", "report.transaction_history"
    ],
    parent_roles=["TELLER"],  # Inherits teller permissions
    max_sessions=3,
    session_timeout_minutes=480,
    single_transaction_limit=Money(Decimal("25000.00"), Currency.USD),
    daily_transaction_limit=Money(Decimal("100000.00"), Currency.USD)
)
```

### Session

Tracks active user sessions:

```python
from core_banking.rbac import Session, SessionStatus

@dataclass
class Session(StorageRecord):
    user_id: str
    session_token: str  # JWT token
    
    # Session details
    ip_address: str
    user_agent: str
    login_time: datetime
    last_activity: datetime
    expires_at: datetime
    
    # Status
    status: SessionStatus = SessionStatus.ACTIVE
    
    # Security tracking
    authentication_method: str = "password"  # password, two_factor, etc.
    login_location: Optional[str] = None
    
    def __post_init__(self):
        super().__post_init__()
        self.login_time = datetime.now(timezone.utc)
        self.last_activity = self.login_time
    
    @property
    def is_expired(self) -> bool:
        """Check if session has expired"""
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def time_remaining(self) -> int:
        """Get remaining session time in seconds"""
        if self.is_expired:
            return 0
        
        remaining = self.expires_at - datetime.now(timezone.utc)
        return int(remaining.total_seconds())
    
    def extend_session(self, minutes: int = 480) -> None:
        """Extend session expiration"""
        self.expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        self.last_activity = datetime.now(timezone.utc)
```

## User Management

### UserManager

Core user management operations:

```python
from core_banking.rbac import UserManager, PasswordPolicy
import hashlib
import secrets
import jwt

class UserManager:
    def __init__(self, storage: StorageInterface, audit_trail: AuditTrail):
        self.storage = storage
        self.audit_trail = audit_trail
        self.password_policy = PasswordPolicy()
    
    def create_user(
        self,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
        password: str,
        roles: List[str],
        created_by: str
    ) -> User:
        """Create new user account"""
        
        # Validate username uniqueness
        if self.get_user_by_username(username):
            raise ValueError(f"Username '{username}' already exists")
        
        # Validate email uniqueness
        if self.get_user_by_email(email):
            raise ValueError(f"Email '{email}' already in use")
        
        # Validate password policy
        policy_result = self.password_policy.validate_password(password)
        if not policy_result.is_valid:
            raise ValueError(f"Password policy violation: {', '.join(policy_result.violations)}")
        
        # Hash password
        salt = secrets.token_hex(16)
        password_hash = self.hash_password(password, salt)
        
        # Set password expiration
        password_expires = datetime.now(timezone.utc) + timedelta(days=90)
        
        user = User(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            password_hash=password_hash,
            salt=salt,
            roles=roles,
            password_expires=password_expires,
            require_password_change=False,
            created_by=created_by
        )
        
        self.storage.store(user)
        
        # Log user creation
        self.audit_trail.log_event(
            AuditEventType.USER_CREATED,
            entity_id=user.id,
            user_id=created_by,
            details={
                "username": username,
                "email": email,
                "roles": roles
            }
        )
        
        return user
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user credentials"""
        
        user = self.get_user_by_username(username)
        if not user:
            self.audit_trail.log_event(
                AuditEventType.LOGIN_FAILED,
                details={"username": username, "reason": "user_not_found"}
            )
            return None
        
        # Check if account is locked
        if user.is_locked:
            self.audit_trail.log_event(
                AuditEventType.LOGIN_FAILED,
                entity_id=user.id,
                user_id=user.id,
                details={"username": username, "reason": "account_locked"}
            )
            return None
        
        # Verify password
        if not self.verify_password(password, user.password_hash, user.salt):
            user.failed_login_attempts += 1
            
            # Lock account after too many failed attempts
            if user.failed_login_attempts >= 5:
                user.status = UserStatus.LOCKED
                user.locked_until = datetime.now(timezone.utc) + timedelta(hours=1)
                
                self.audit_trail.log_event(
                    AuditEventType.USER_LOCKED,
                    entity_id=user.id,
                    details={"reason": "failed_login_attempts"}
                )
            
            self.storage.update(user.id, user)
            
            self.audit_trail.log_event(
                AuditEventType.LOGIN_FAILED,
                entity_id=user.id,
                details={
                    "username": username,
                    "reason": "invalid_password",
                    "failed_attempts": user.failed_login_attempts
                }
            )
            
            return None
        
        # Reset failed login attempts on successful authentication
        user.failed_login_attempts = 0
        user.last_login = datetime.now(timezone.utc)
        self.storage.update(user.id, user)
        
        self.audit_trail.log_event(
            AuditEventType.LOGIN_SUCCESS,
            entity_id=user.id,
            user_id=user.id,
            details={"username": username}
        )
        
        return user
    
    def hash_password(self, password: str, salt: str) -> str:
        """Hash password with salt using scrypt (more secure than SHA-256)"""
        # Use scrypt for stronger password hashing with memory-hard properties
        return hashlib.scrypt(
            password.encode(), 
            salt=salt.encode(), 
            n=16384, r=8, p=1  # Standard scrypt parameters for strong security
        ).hex()
    
    def hash_password_legacy(self, password: str, salt: str) -> str:
        """Legacy SHA-256 password hashing for backward compatibility"""
        return hashlib.sha256((password + salt).encode()).hexdigest()
    
    def verify_password(self, password: str, hash: str, salt: str) -> bool:
        """Verify password against stored hash with legacy support"""
        # Try new scrypt hashing first
        expected_hash_new = self.hash_password(password, salt)
        if hash == expected_hash_new:
            return True
            
        # Fall back to legacy SHA-256 for existing passwords
        expected_hash_legacy = self.hash_password_legacy(password, salt)
        if hash == expected_hash_legacy:
            # Consider re-hashing with scrypt for security upgrade
            return True
            
        return False
```

### Password Policy

Enforce strong password requirements:

```python
from core_banking.rbac import PasswordPolicy, PasswordValidationResult

class PasswordPolicy:
    """Enforce password security requirements"""
    
    def __init__(self):
        self.min_length = 12
        self.max_length = 128
        self.require_uppercase = True
        self.require_lowercase = True
        self.require_numbers = True
        self.require_special_chars = True
        self.special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        self.max_repeated_chars = 2
        self.password_history_count = 12  # Remember last 12 passwords
    
    def validate_password(self, password: str, user: Optional[User] = None) -> PasswordValidationResult:
        """Validate password against policy requirements"""
        
        violations = []
        
        # Length requirements
        if len(password) < self.min_length:
            violations.append(f"Password must be at least {self.min_length} characters")
        
        if len(password) > self.max_length:
            violations.append(f"Password must not exceed {self.max_length} characters")
        
        # Character requirements
        if self.require_uppercase and not any(c.isupper() for c in password):
            violations.append("Password must contain at least one uppercase letter")
        
        if self.require_lowercase and not any(c.islower() for c in password):
            violations.append("Password must contain at least one lowercase letter")
        
        if self.require_numbers and not any(c.isdigit() for c in password):
            violations.append("Password must contain at least one number")
        
        if self.require_special_chars and not any(c in self.special_chars for c in password):
            violations.append("Password must contain at least one special character")
        
        # Repeated character check
        if self.has_too_many_repeated_chars(password):
            violations.append(f"Password cannot have more than {self.max_repeated_chars} consecutive repeated characters")
        
        # Common password check
        if self.is_common_password(password):
            violations.append("Password is too common")
        
        # Password history check (if user provided)
        if user and self.is_password_reused(password, user):
            violations.append("Password cannot be one of the last 12 passwords used")
        
        return PasswordValidationResult(
            is_valid=len(violations) == 0,
            violations=violations
        )
    
    def has_too_many_repeated_chars(self, password: str) -> bool:
        """Check for excessive repeated characters"""
        for i in range(len(password) - self.max_repeated_chars):
            if all(password[i] == password[i + j] for j in range(self.max_repeated_chars + 1)):
                return True
        return False
    
    def is_common_password(self, password: str) -> bool:
        """Check against common password list"""
        common_passwords = {
            "password123", "123456789", "qwertyuiop", "admin123456",
            "letmein123", "welcome123", "password1234", "123456781"
        }
        return password.lower() in common_passwords
    
    def is_password_reused(self, password: str, user: User) -> bool:
        """Check if password was recently used"""
        # In real implementation, would check password history
        # For now, just check against current password
        return self.verify_password(password, user.password_hash, user.salt)
```

## Role and Permission Management

### RoleManager

Manage roles and permissions:

```python
from core_banking.rbac import RoleManager, Permission

class RoleManager:
    def __init__(self, storage: StorageInterface):
        self.storage = storage
        self.system_roles = self.initialize_system_roles()
    
    def initialize_system_roles(self) -> Dict[str, Role]:
        """Initialize system-defined roles"""
        
        roles = {}
        
        # Super Admin - Full system access
        roles["SUPER_ADMIN"] = Role(
            name="SUPER_ADMIN",
            display_name="Super Administrator",
            description="Full system access and administration",
            permissions=["*"],  # All permissions
            is_system_role=True,
            max_sessions=2,
            session_timeout_minutes=240  # 4 hours
        )
        
        # Admin - Administrative operations
        roles["ADMIN"] = Role(
            name="ADMIN",
            display_name="Administrator",
            description="System administration and configuration",
            permissions=[
                "user.*", "role.*", "system.*", "config.*",
                "customer.*", "account.*", "transaction.*",
                "loan.*", "credit.*", "report.*", "audit.read"
            ],
            is_system_role=True,
            max_sessions=3,
            session_timeout_minutes=480
        )
        
        # Manager - Department management
        roles["MANAGER"] = Role(
            name="MANAGER",
            display_name="Banking Manager",
            description="Department management and oversight",
            permissions=[
                "customer.*", "account.*", "transaction.*",
                "loan.read", "loan.approve", "loan.payment",
                "credit.*", "collection.*", "report.*",
                "workflow.approve"
            ],
            parent_roles=["OFFICER"],
            is_system_role=True,
            single_transaction_limit=Money(Decimal("100000.00"), Currency.USD),
            daily_transaction_limit=Money(Decimal("500000.00"), Currency.USD)
        )
        
        # Officer - Daily operations
        roles["OFFICER"] = Role(
            name="OFFICER",
            display_name="Banking Officer",
            description="Daily banking operations",
            permissions=[
                "customer.read", "customer.update", "customer.kyc.update",
                "account.read", "account.create", "account.update",
                "transaction.*",
                "loan.read", "loan.payment",
                "credit.read", "credit.payment",
                "report.account", "report.transaction"
            ],
            parent_roles=["TELLER"],
            is_system_role=True,
            single_transaction_limit=Money(Decimal("25000.00"), Currency.USD),
            daily_transaction_limit=Money(Decimal("100000.00"), Currency.USD)
        )
        
        # Teller - Basic transactions
        roles["TELLER"] = Role(
            name="TELLER",
            display_name="Bank Teller",
            description="Basic transaction processing",
            permissions=[
                "customer.read",
                "account.read",
                "transaction.deposit", "transaction.withdraw", "transaction.transfer",
                "transaction.read",
                "report.account_balance"
            ],
            is_system_role=True,
            single_transaction_limit=Money(Decimal("5000.00"), Currency.USD),
            daily_transaction_limit=Money(Decimal("25000.00"), Currency.USD)
        )
        
        # Compliance Officer
        roles["COMPLIANCE"] = Role(
            name="COMPLIANCE",
            display_name="Compliance Officer",
            description="Compliance monitoring and reporting",
            permissions=[
                "customer.read", "customer.kyc.*",
                "account.read",
                "transaction.read",
                "compliance.*", "audit.read",
                "report.compliance", "report.aml", "report.kyc"
            ],
            is_system_role=True
        )
        
        # Auditor - Read-only access
        roles["AUDITOR"] = Role(
            name="AUDITOR",
            display_name="Auditor",
            description="Read-only access for auditing",
            permissions=[
                "*.read", "audit.read", "report.read"
            ],
            is_system_role=True
        )
        
        return roles
    
    def check_permission(self, user: User, permission: str) -> bool:
        """Check if user has specific permission"""
        
        user_permissions = self.get_user_permissions(user)
        
        # Check for wildcard permissions
        if "*" in user_permissions:
            return True
        
        # Check for exact match
        if permission in user_permissions:
            return True
        
        # Check for wildcard module permissions (e.g., "customer.*")
        module = permission.split('.')[0]
        if f"{module}.*" in user_permissions:
            return True
        
        return False
    
    def get_user_permissions(self, user: User) -> List[str]:
        """Get all permissions for a user"""
        
        all_permissions = set()
        
        for role_name in user.roles:
            role = self.get_role_by_name(role_name)
            if role:
                effective_permissions = role.get_effective_permissions(self)
                all_permissions.update(effective_permissions)
        
        return list(all_permissions)
    
    def can_user_perform_transaction(
        self,
        user: User,
        transaction_amount: Money,
        daily_total: Money
    ) -> Tuple[bool, str]:
        """Check if user can perform transaction based on role limits"""
        
        for role_name in user.roles:
            role = self.get_role_by_name(role_name)
            if not role:
                continue
            
            # Check single transaction limit
            if (role.single_transaction_limit and 
                transaction_amount > role.single_transaction_limit):
                return False, f"Transaction exceeds single transaction limit of {role.single_transaction_limit}"
            
            # Check daily limit
            if (role.daily_transaction_limit and 
                daily_total + transaction_amount > role.daily_transaction_limit):
                return False, f"Transaction would exceed daily limit of {role.daily_transaction_limit}"
        
        return True, "Approved"
```

## Session Management

### SessionManager

Handle user sessions and JWT tokens:

```python
from core_banking.rbac import SessionManager
import jwt
import secrets
from datetime import datetime, timezone, timedelta

class SessionManager:
    def __init__(self, storage: StorageInterface, config):
        self.storage = storage
        self.jwt_secret = config.jwt_secret
        self.jwt_expiry_hours = config.jwt_expiry_hours
        self.jwt_algorithm = config.jwt_algorithm  # Default: "HS256"
    
    def create_session(
        self,
        user: User,
        ip_address: str,
        user_agent: str,
        authentication_method: str = "password"
    ) -> Session:
        """Create new user session"""
        
        # Check concurrent session limits
        active_sessions = self.get_active_sessions(user.id)
        role = self.role_manager.get_primary_role(user)
        
        if len(active_sessions) >= role.max_sessions:
            # Close oldest session
            oldest_session = min(active_sessions, key=lambda s: s.login_time)
            self.end_session(oldest_session.id, "concurrent_limit_exceeded")
        
        # Generate session token
        # Create JWT token
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=self.jwt_expiry_hours)
        
        token_payload = {
            "sub": user.id,                     # Subject (user ID) 
            "username": user.username,          # Username
            "roles": user.roles,                # User roles for authorization
            "session_id": session_id,           # Session identifier
            "iat": int(now.timestamp()),        # Issued at
            "exp": int(expires_at.timestamp())  # Expiration time
        }
        
        session_token = jwt.encode(token_payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        
        # Create session record
        session = Session(
            user_id=user.id,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=self.token_expiry_hours),
            authentication_method=authentication_method
        )
        
        self.storage.store(session)
        
        # Log session creation
        self.audit_trail.log_event(
            AuditEventType.SESSION_STARTED,
            entity_id=session.id,
            user_id=user.id,
            details={
                "ip_address": ip_address,
                "user_agent": user_agent,
                "authentication_method": authentication_method
            }
        )
        
        return session
    
    def validate_session(self, token: str) -> Optional[Session]:
        """Validate session token and return session info"""
        
        try:
            # Decode JWT token
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            
            # Find session in storage
            sessions = self.storage.query({"session_token": token})
            if not sessions:
                return None
            
            session = sessions[0]
            
            # Check if session is still active
            if session.status != SessionStatus.ACTIVE or session.is_expired:
                return None
            
            # Update last activity
            session.last_activity = datetime.now(timezone.utc)
            self.storage.update(session.id, session)
            
            return session
            
        except jwt.ExpiredSignatureError:
            # Token has expired
            return None
        except jwt.InvalidTokenError:
            # Invalid token
            return None
    
    def refresh_session(self, session_id: str) -> Optional[Session]:
        """Refresh session expiration"""
        
        session = self.storage.retrieve(session_id)
        if not session or session.status != SessionStatus.ACTIVE:
            return None
        
        # Extend session
        role = self.role_manager.get_primary_role_by_user_id(session.user_id)
        session.extend_session(role.session_timeout_minutes)
        
        # Generate new token
        user = self.user_manager.get_user(session.user_id)
        token_payload = {
            "user_id": user.id,
            "username": user.username,
            "roles": user.roles,
            "iat": datetime.now(timezone.utc).timestamp(),
            "exp": session.expires_at.timestamp()
        }
        
        session.session_token = jwt.encode(token_payload, self.secret_key, algorithm="HS256")
        
        self.storage.update(session_id, session)
        
        return session
    
    def end_session(self, session_id: str, reason: str = "user_logout") -> None:
        """End user session"""
        
        session = self.storage.retrieve(session_id)
        if session:
            session.status = SessionStatus.ENDED
            self.storage.update(session_id, session)
            
            self.audit_trail.log_event(
                AuditEventType.SESSION_ENDED,
                entity_id=session_id,
                user_id=session.user_id,
                details={"reason": reason}
            )
```

## Authorization Middleware

### Permission Decorator

Decorator for protecting endpoints:

```python
from functools import wraps
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer

security = HTTPBearer()

def require_permission(permission: str):
    """Decorator to require specific permission for endpoint access"""
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get session from JWT token (simplified)
            token = kwargs.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
            
            session = session_manager.validate_session(token)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired session"
                )
            
            user = user_manager.get_user(session.user_id)
            
            # Check permission
            if not role_manager.check_permission(user, permission):
                audit_trail.log_event(
                    AuditEventType.PERMISSION_DENIED,
                    entity_id=session.id,
                    user_id=user.id,
                    details={
                        "permission": permission,
                        "endpoint": func.__name__
                    }
                )
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission}"
                )
            
            # Add user context to request
            kwargs['current_user'] = user
            kwargs['current_session'] = session
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator

## Permission Enforcement on API Endpoints

All API endpoints are protected using JWT authentication middleware and role-based permission checks:

### Authentication Middleware

```python
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Extract and validate JWT token from Authorization header"""
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Validate user exists and is active
        rbac_manager = get_rbac_manager()
        user = rbac_manager.get_user(user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User inactive")
        
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### Permission Decorators

```python
from functools import wraps
from fastapi import HTTPException

def require_permission(permission: str):
    """Decorator to require specific permission for endpoint access"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current user from dependency injection
            current_user = kwargs.get('current_user')
            
            rbac_manager = get_rbac_manager()
            if not rbac_manager.user_has_permission(current_user, permission):
                raise HTTPException(
                    status_code=403, 
                    detail=f"Permission required: {permission}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
```

### Protected Endpoint Examples

```python
# Customer management endpoints
@app.get("/customers/{customer_id}")
@require_permission("VIEW_CUSTOMER")
async def get_customer(
    customer_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get customer details - requires VIEW_CUSTOMER permission"""
    pass

@app.post("/customers")
@require_permission("CREATE_CUSTOMER") 
async def create_customer(
    customer_data: CustomerCreate,
    current_user: User = Depends(get_current_user)
):
    """Create new customer - requires CREATE_CUSTOMER permission"""
    pass

# Transaction endpoints
@app.post("/transactions/deposit")
@require_permission("CREATE_TRANSACTION")
async def deposit_transaction(
    deposit_data: DepositRequest,
    current_user: User = Depends(get_current_user)
):
    """Process deposit - requires CREATE_TRANSACTION permission"""
    pass

@app.post("/transactions/transfer")
@require_permission("CREATE_TRANSACTION")
async def transfer_transaction(
    transfer_data: TransferRequest,
    current_user: User = Depends(get_current_user)
):
    """Process transfer - requires CREATE_TRANSACTION permission"""
    pass

# Administrative endpoints
@app.get("/admin/users")
@require_permission("MANAGE_USERS")
async def list_users(
    current_user: User = Depends(get_current_user)
):
    """List all users - requires MANAGE_USERS permission"""
    pass

@app.post("/admin/users/{user_id}/roles")
@require_permission("ASSIGN_ROLES")
async def assign_role(
    user_id: str,
    role_data: RoleAssignment,
    current_user: User = Depends(get_current_user)
):
    """Assign role to user - requires ASSIGN_ROLES permission"""
    pass
```

### Role-Based Access Control Matrix

| Endpoint | TELLER | OFFICER | MANAGER | ADMIN | AUDITOR |
|----------|---------|---------|---------|-------|---------|
| GET /customers/{id} | ✓ | ✓ | ✓ | ✓ | ✓ |
| POST /customers | ✗ | ✓ | ✓ | ✓ | ✗ |
| POST /transactions/deposit | ✓ | ✓ | ✓ | ✓ | ✗ |
| POST /transactions/transfer | ✗ | ✓ | ✓ | ✓ | ✗ |
| POST /loans | ✗ | ✓ | ✓ | ✓ | ✗ |
| PUT /loans/{id}/approve | ✗ | ✗ | ✓ | ✓ | ✗ |
| GET /admin/users | ✗ | ✗ | ✗ | ✓ | ✓ |
| POST /admin/users | ✗ | ✗ | ✗ | ✓ | ✗ |

@app.post("/transactions/transfer")
@require_permission("transaction.transfer")
async def transfer_funds(
    transfer_request: TransferRequest,
    current_user: User = Depends(),
    current_session: Session = Depends()
):
    # Check transaction limits
    daily_total = get_user_daily_transaction_total(current_user.id)
    can_perform, message = role_manager.can_user_perform_transaction(
        current_user,
        transfer_request.amount.to_money(),
        daily_total
    )
    
    if not can_perform:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=message
        )
    
    # Process transfer
    pass
```

## Two-Factor Authentication

### 2FA Implementation

```python
import pyotp
import qrcode

class TwoFactorAuthManager:
    """Manage two-factor authentication"""
    
    def enable_2fa(self, user_id: str) -> str:
        """Enable 2FA for user and return setup secret"""
        
        user = self.user_manager.get_user(user_id)
        
        # Generate secret
        secret = pyotp.random_base32()
        user.two_factor_secret = secret
        user.two_factor_enabled = True
        
        self.storage.update(user_id, user)
        
        # Generate QR code for easy setup
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name="Nexum Banking"
        )
        
        self.audit_trail.log_event(
            AuditEventType.TWO_FACTOR_ENABLED,
            entity_id=user_id,
            user_id=user_id
        )
        
        return totp_uri
    
    def verify_2fa_code(self, user: User, code: str) -> bool:
        """Verify 2FA code"""
        
        if not user.two_factor_enabled or not user.two_factor_secret:
            return False
        
        totp = pyotp.TOTP(user.two_factor_secret)
        is_valid = totp.verify(code, valid_window=1)  # Allow 30 second window
        
        self.audit_trail.log_event(
            AuditEventType.TWO_FACTOR_VERIFIED,
            entity_id=user.id,
            user_id=user.id,
            details={"success": is_valid}
        )
        
        return is_valid
    
    def generate_backup_codes(self, user_id: str) -> List[str]:
        """Generate one-time backup codes for 2FA"""
        
        backup_codes = []
        for _ in range(10):
            code = secrets.token_hex(4).upper()  # 8 character codes
            backup_codes.append(code)
        
        # Store hashed backup codes
        hashed_codes = [hashlib.sha256(code.encode()).hexdigest() for code in backup_codes]
        
        # Store in user record or separate table
        user = self.user_manager.get_user(user_id)
        user.backup_codes = hashed_codes
        self.storage.update(user_id, user)
        
        return backup_codes
```

## Testing RBAC Functions

```python
def test_user_authentication():
    """Test user authentication process"""
    
    # Create test user
    user = user_manager.create_user(
        username="test.user",
        email="test@nexumbank.com",
        first_name="Test",
        last_name="User",
        password="SecureP@ssw0rd123",
        roles=["OFFICER"],
        created_by="admin"
    )
    
    # Test successful authentication
    authenticated_user = user_manager.authenticate_user("test.user", "SecureP@ssw0rd123")
    assert authenticated_user is not None
    assert authenticated_user.id == user.id
    
    # Test failed authentication
    failed_auth = user_manager.authenticate_user("test.user", "wrong_password")
    assert failed_auth is None

def test_permission_checking():
    """Test role-based permission checking"""
    
    user = create_test_user(roles=["OFFICER"])
    
    # Officer should have transaction permissions
    assert role_manager.check_permission(user, "transaction.deposit")
    assert role_manager.check_permission(user, "transaction.transfer")
    
    # Officer should not have admin permissions
    assert not role_manager.check_permission(user, "user.create")
    assert not role_manager.check_permission(user, "system.config")

def test_session_management():
    """Test session creation and validation"""
    
    user = create_test_user()
    
    # Create session
    session = session_manager.create_session(
        user=user,
        ip_address="192.168.1.100",
        user_agent="Test Browser"
    )
    
    assert session.user_id == user.id
    assert session.status == SessionStatus.ACTIVE
    
    # Validate session
    valid_session = session_manager.validate_session(session.session_token)
    assert valid_session is not None
    assert valid_session.id == session.id
    
    # End session
    session_manager.end_session(session.id, "test_logout")
    
    # Should no longer be valid
    invalid_session = session_manager.validate_session(session.session_token)
    assert invalid_session is None

def test_transaction_limits():
    """Test role-based transaction limits"""
    
    teller = create_test_user(roles=["TELLER"])
    officer = create_test_user(roles=["OFFICER"])
    
    large_amount = Money(Decimal("10000.00"), Currency.USD)
    daily_total = Money(Decimal("5000.00"), Currency.USD)
    
    # Teller should be blocked for large transaction
    can_perform, message = role_manager.can_user_perform_transaction(
        teller, large_amount, daily_total
    )
    assert not can_perform
    assert "exceeds single transaction limit" in message
    
    # Officer should be allowed
    can_perform, message = role_manager.can_user_perform_transaction(
        officer, large_amount, daily_total
    )
    assert can_perform
```

The RBAC module provides enterprise-grade security controls with comprehensive user management, role-based permissions, secure session handling, and complete audit logging for banking operations.