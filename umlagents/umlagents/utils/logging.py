"""
Structured logging for UMLAgents.
Provides JSON-formatted logs with consistent fields for audit trail integration.
"""
import json
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union
import sys


class JSONFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Convert log record to JSON string."""
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra'):
            log_data.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logging(
    log_level: Union[int, str] = logging.INFO,
    log_file: Optional[Path] = None,
    console_output: bool = True,
    json_format: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> None:
    """
    Configure logging for UMLAgents.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        console_output: Whether to log to console
        json_format: Use JSON formatting (True) or plain text (False)
        max_bytes: Maximum log file size before rotation
        backup_count: Number of backup files to keep
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatters
    if json_format:
        formatter = JSONFormatter()
        console_formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_formatter = logging.Formatter(
            '%(levelname)s - %(message)s'
        )
    
    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    
    # File handler (if log_file specified)
    if log_file:
        # Create parent directory if needed
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Use rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            filename=log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Log startup message
    root_logger.info("Logging configured", extra={
        "log_level": logging.getLevelName(log_level),
        "log_file": str(log_file) if log_file else None,
        "json_format": json_format,
    })


def get_logger(name: str) -> logging.Logger:
    """Get a named logger with consistent configuration."""
    return logging.getLogger(name)


def log_agent_activity(
    logger: logging.Logger,
    agent_name: str,
    activity: str,
    project_id: Optional[int] = None,
    artifact_id: Optional[int] = None,
    details: Optional[Dict[str, Any]] = None,
    level: str = "INFO"
) -> None:
    """
    Log agent activity with structured fields.
    
    Args:
        logger: Logger instance
        agent_name: Name of the agent (e.g., "BAAgent")
        activity: Activity description (e.g., "api_call_start", "artifact_generated")
        project_id: Project ID (optional)
        artifact_id: Artifact ID (optional)
        details: Additional details (optional)
        level: Log level (INFO, DEBUG, WARNING, ERROR)
    """
    extra = {
        "agent": agent_name,
        "activity": activity,
    }
    
    if project_id is not None:
        extra["project_id"] = project_id
    
    if artifact_id is not None:
        extra["artifact_id"] = artifact_id
    
    if details:
        extra["details"] = details
    
    log_method = getattr(logger, level.lower(), logger.info)
    log_method(f"[{agent_name}] {activity}", extra=extra)


def log_api_call(
    logger: logging.Logger,
    agent_name: str,
    endpoint: str,
    status: str,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
    project_id: Optional[int] = None,
) -> None:
    """
    Log API call with structured fields.
    
    Args:
        logger: Logger instance
        agent_name: Name of the agent
        endpoint: API endpoint called
        status: Call status ("started", "success", "failed")
        duration_ms: Duration in milliseconds (for completed calls)
        error: Error message (for failed calls)
        project_id: Project ID (optional)
    """
    extra = {
        "agent": agent_name,
        "api_endpoint": endpoint,
        "api_status": status,
    }
    
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    
    if error is not None:
        extra["error"] = error
    
    if project_id is not None:
        extra["project_id"] = project_id
    
    level = "ERROR" if status == "failed" else "INFO"
    log_method = getattr(logger, level.lower())
    
    message = f"[{agent_name}] API call {status}: {endpoint}"
    if duration_ms:
        message += f" ({duration_ms:.0f}ms)"
    if error:
        message += f" - {error}"
    
    log_method(message, extra=extra)


def log_artifact_creation(
    logger: logging.Logger,
    agent_name: str,
    artifact_type: str,
    filename: str,
    project_id: Optional[int] = None,
    artifact_id: Optional[int] = None,
    size_bytes: Optional[int] = None,
) -> None:
    """
    Log artifact creation with structured fields.
    
    Args:
        logger: Logger instance
        agent_name: Name of the agent
        artifact_type: Type of artifact (e.g., "diagram", "code", "test")
        filename: Filename of the artifact
        project_id: Project ID (optional)
        artifact_id: Artifact ID (optional)
        size_bytes: Size in bytes (optional)
    """
    extra = {
        "agent": agent_name,
        "artifact_type": artifact_type,
        "filename": filename,
    }
    
    if project_id is not None:
        extra["project_id"] = project_id
    
    if artifact_id is not None:
        extra["artifact_id"] = artifact_id
    
    if size_bytes is not None:
        extra["size_bytes"] = size_bytes
    
    logger.info(
        f"[{agent_name}] Created {artifact_type}: {filename}",
        extra=extra
    )


# Default configuration
def configure_default_logging() -> None:
    """Configure default logging for UMLAgents."""
    # By default, log to console with JSON format
    setup_logging(
        log_level=logging.INFO,
        log_file=None,  # No file logging by default
        console_output=True,
        json_format=True,
    )