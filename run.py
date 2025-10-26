#!/usr/bin/env python3
"""
Production startup script for DonorIQ API
"""
import uvicorn
import os
import sys
from app.core.config import settings
from app.core.logging import logger

def main():
    """Start the FastAPI application."""
    
    # Create necessary directories
    os.makedirs("logs", exist_ok=True)
    os.makedirs(settings.UPLOAD_DIRECTORY, exist_ok=True)
    
    logger.info(f"Starting {settings.APP_NAME} Server")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG}")
    logger.info(f"Database: Connected to PostgreSQL")
    
    # Configure uvicorn
    config = {
        "app": "app.main:app",
        "host": settings.HOST,
        "port": settings.PORT,
        "reload": settings.DEBUG,
        "log_level": settings.LOG_LEVEL.lower(),
        "access_log": True,
        "use_colors": settings.DEBUG,
    }
    
    if not settings.DEBUG:
        # Production settings
        config.update({
            "workers": settings.WORKERS,
            "loop": "uvloop",
            "http": "httptools",
            "lifespan": "on",
        })
    
    logger.info(f"Starting server on {config['host']}:{config['port']}")
    
    try:
        uvicorn.run(**config)
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
