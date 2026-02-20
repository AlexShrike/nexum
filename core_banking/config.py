"""
Configuration Management Module

Provides centralized configuration using pydantic-settings for environment-based configuration.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class NexumConfig(BaseSettings):
    """Nexum core banking system configuration"""
    
    # Database configuration
    database_url: str = "sqlite:///nexum.db"  # Default SQLite
    database_pool_size: int = 5
    database_pool_overflow: int = 10
    database_pool_timeout: int = 30
    database_echo: bool = False  # Set to True for SQL logging
    
    # Kafka configuration
    kafka_bootstrap_servers: str = ""
    kafka_topic_prefix: str = "nexum"
    kafka_consumer_group: str = "nexum-core"
    kafka_batch_size: int = 100
    
    # API configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8090
    api_workers: int = 1
    api_timeout: int = 60
    api_max_request_size: int = 16 * 1024 * 1024  # 16MB
    
    # Security configuration
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_hours: int = 24
    jwt_algorithm: str = "HS256"
    password_min_length: int = 8
    session_timeout_minutes: int = 30
    
    # Logging configuration
    log_level: str = "INFO"
    log_format: str = "json"  # json or text
    log_file: Optional[str] = None  # If None, logs to stdout
    
    # Business rules configuration
    min_account_balance: str = "0.00"  # Default minimum balance
    max_daily_transaction_limit: str = "10000.00"
    max_transaction_amount: str = "100000.00"
    interest_calculation_precision: int = 4
    
    # Encryption configuration
    encryption_enabled: bool = False  # Must opt-in
    encryption_master_key: str = ""  # NEXUM_ENCRYPTION_MASTER_KEY env var
    encryption_provider: str = "fernet"  # fernet, aesgcm, noop
    
    # Bastion fraud detection configuration
    bastion_url: str = ""  # Empty = disabled. Set to http://localhost:8080
    bastion_timeout: float = 2.0
    bastion_api_key: str = ""
    bastion_fallback: str = "APPROVE"  # What to do if Bastion is down
    
    # Feature flags
    enable_audit_logging: bool = True
    enable_kafka_events: bool = False
    enable_metrics: bool = True
    enable_tracing: bool = False
    enable_rate_limiting: bool = True
    
    # Performance configuration
    cache_ttl_seconds: int = 300  # 5 minutes default
    batch_processing_size: int = 1000
    connection_pool_size: int = 20
    
    # Migration configuration
    auto_migrate: bool = True
    migration_timeout_seconds: int = 300
    
    class Config:
        env_prefix = "NEXUM_"
        env_file = ".env"
        case_sensitive = False


# Global configuration instance
config = NexumConfig()


def get_config() -> NexumConfig:
    """Get global configuration instance"""
    return config


def reload_config() -> NexumConfig:
    """Reload configuration from environment"""
    global config
    config = NexumConfig()
    return config