import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from config import (LOG_FILE, LOG_CONSOLE_LEVEL, LOG_FILE_LEVEL, LOG_CONSOLE_FORMAT, LOG_DATE_FORMAT)

def setup_logger(name: str = "PublishAI"):
    """Configure logger with console handler and optional file handler."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Console handler (INFO and above)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_CONSOLE_FORMAT, datefmt=LOG_DATE_FORMAT))
    logger.addHandler(console)

    # File handler (DEBUG and above) – with automatic folder creation
    if LOG_FILE:
        log_path = Path(LOG_FILE)
        log_path.parent.mkdir(parents=True, exist_ok=True)   # ✅ creates logs/ if needed
        # file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter( LOG_CONSOLE_FORMAT, datefmt=LOG_DATE_FORMAT))
        logger.addHandler(file_handler)

    return logger