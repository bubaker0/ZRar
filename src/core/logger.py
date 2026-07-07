import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Singleton logger instance
_logger = None

def setup_logger() -> logging.Logger:
    """
    Sets up a global RotatingFileHandler logger for ZRar.
    Restricts file size to 2MB and keeps up to 3 backup logs.
    """
    global _logger
    if _logger is not None:
        return _logger

    _logger = logging.getLogger("ZRar")
    _logger.setLevel(logging.DEBUG)
    
    # Avoid duplicate handlers if setup is called multiple times
    if not _logger.handlers:
        # Save log file in the workspace directory (or app data directory)
        log_file = Path(__file__).parent.parent.parent / "zrar.log"
        
        # 2MB maximum per file, keep 3 backup logs
        handler = RotatingFileHandler(
            str(log_file), 
            maxBytes=2 * 1024 * 1024, 
            backupCount=3, 
            encoding="utf-8"
        )
        
        # Standard logging format: Timestamp - Log Level - Message
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
        handler.setFormatter(formatter)
        
        _logger.addHandler(handler)
        
    return _logger

def get_logger() -> logging.Logger:
    """Helper function to fetch the configured logger."""
    return setup_logger()
