"""
Structured Logging Configuration Module

Provides JSON-formatted structured logging for all core banking operations.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional
import os


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.module if hasattr(record, 'module') else record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, 'correlation_id', None),
            "user_id": getattr(record, 'user_id', None),
            "action": getattr(record, 'action', None),
            "resource": getattr(record, 'resource', None),
            "extra": getattr(record, 'extra', None)
        }
        
        # Remove None values
        log_entry = {k: v for k, v in log_entry.items() if v is not None}
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO", logger_name: str = "nexum") -> logging.Logger:
    """
    Setup structured JSON logging for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        logger_name: Name of the logger
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(logger_name)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    
    # Add handler to logger
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Prevent propagation to avoid duplicate logs
    logger.propagate = False
    
    return logger


def get_logger(name: str = "nexum") -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)


def log_action(logger: logging.Logger, level: str, message: str, 
               user_id: Optional[str] = None, action: Optional[str] = None,
               resource: Optional[str] = None, correlation_id: Optional[str] = None,
               extra: Optional[dict] = None):
    """
    Log an action with structured data.
    
    Args:
        logger: Logger instance
        level: Log level (info, warning, error, etc.)
        message: Log message
        user_id: ID of the user performing the action
        action: Action being performed
        resource: Resource being acted upon
        correlation_id: Correlation ID for request tracing
        extra: Additional structured data
    """
    log_func = getattr(logger, level.lower())
    
    # Create a LogRecord with extra fields
    record = logger.makeRecord(
        logger.name, getattr(logging, level.upper()), 
        __name__, 0, message, (), None
    )
    
    # Add custom fields
    if user_id:
        record.user_id = user_id
    if action:
        record.action = action
    if resource:
        record.resource = resource
    if correlation_id:
        record.correlation_id = correlation_id
    if extra:
        record.extra = extra
        
    logger.handle(record)