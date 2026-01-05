import logging
import logging.handlers
import sys
import os
from app.core.config import settings

def setup_logging():
    """Configure logging for the application."""
    
    # Create logs directory if it doesn't exist
    os.makedirs(os.path.dirname(settings.LOG_FILE), exist_ok=True)
    
    # Create formatter
    formatter = logging.Formatter(settings.LOG_FORMAT)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # File handler for production
    if not settings.DEBUG:
        file_handler = logging.handlers.RotatingFileHandler(
            settings.LOG_FILE,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))
        root_logger.addHandler(file_handler)
    
    # Set specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
    logging.getLogger("passlib").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Suppress HTTP request logs from httpx
    
    # Add request ID to logs
    class RequestIDFilter(logging.Filter):
        def filter(self, record):
            record.request_id = getattr(record, 'request_id', 'N/A')
            return True
    
    request_id_filter = RequestIDFilter()
    for handler in root_logger.handlers:
        handler.addFilter(request_id_filter)
    
    return root_logger

# Initialize logging
logger = setup_logging()
