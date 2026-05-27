"""
Log Manager - Handles logging with rotation for Meraki Backup & Restore
RSITServices
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
import threading


class LogManager:
    """Centralized logging manager with rotating file handler"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(self.log_dir, exist_ok=True)
        
        self.main_log_path = os.path.join(self.log_dir, 'meraki_backup.log')
        self.debug_log_path = os.path.join(self.log_dir, 'meraki_backup_debug.log')
        
        self._setup_loggers()
    
    def _setup_loggers(self):
        """Setup all loggers with rotating handlers"""
        
        # Main application logger
        self.app_logger = logging.getLogger('meraki_backup')
        self.app_logger.setLevel(logging.DEBUG)
        self.app_logger.handlers = []
        
        # Debug logger for detailed API calls
        self.debug_logger = logging.getLogger('meraki_backup_debug')
        self.debug_logger.setLevel(logging.DEBUG)
        self.debug_logger.handlers = []
        
        # File formatter with timestamps
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console formatter
        console_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # Rotating file handler for main log (10MB, 5 backups)
        main_handler = RotatingFileHandler(
            self.main_log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.INFO)
        main_handler.setFormatter(file_formatter)
        
        # Rotating file handler for debug log (10MB, 5 backups)
        debug_handler = RotatingFileHandler(
            self.debug_log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(file_formatter)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(console_formatter)
        
        # Add handlers to main logger
        self.app_logger.addHandler(main_handler)
        self.app_logger.addHandler(console_handler)
        
        # Add handlers to debug logger
        self.debug_logger.addHandler(debug_handler)
        self.debug_logger.addHandler(console_handler)
    
    def log(self, level, message, logger='app'):
        """Log a message at the specified level"""
        log_obj = self.debug_logger if logger == 'debug' else self.app_logger
        
        if level == 'DEBUG':
            log_obj.debug(message)
        elif level == 'INFO':
            log_obj.info(message)
        elif level == 'WARNING':
            log_obj.warning(message)
        elif level == 'ERROR':
            log_obj.error(message)
        elif level == 'CRITICAL':
            log_obj.critical(message)
    
    def info(self, message, logger='app'):
        self.log('INFO', message, logger)
    
    def warning(self, message, logger='app'):
        self.log('WARNING', message, logger)
    
    def error(self, message, logger='app'):
        self.log('ERROR', message, logger)
    
    def debug(self, message, logger='debug'):
        self.log('DEBUG', message, logger)
    
    def critical(self, message, logger='app'):
        self.log('CRITICAL', message, logger)
    
    def log_api_call(self, method, endpoint, response_status=None, response_body=None, error=None):
        """Log API call details for debugging"""
        if error:
            self.debug_logger.debug(f"API CALL FAILED | {method} {endpoint} | Error: {error}")
        else:
            self.debug_logger.debug(f"API CALL | {method} {endpoint} | Status: {response_status}")
            if response_body:
                # Truncate long responses for logging
                body_str = str(response_body)
                if len(body_str) > 1000:
                    body_str = body_str[:1000] + '... [truncated]'
                self.debug_logger.debug(f"API RESPONSE | {body_str}")
    
    def log_exception(self, message, exc):
        """Log exception with full traceback"""
        self.debug_logger.exception(f"{message} | Exception: {exc}")
        self.app_logger.error(f"{message} | {type(exc).__name__}: {exc}")
    
    def get_log_path(self):
        """Return path to main log file"""
        return self.main_log_path
    
    def get_debug_log_path(self):
        """Return path to debug log file"""
        return self.debug_log_path
    
    def clear_logs(self):
        """Clear all log handlers and reinitialize"""
        for handler in self.app_logger.handlers[:]:
            handler.close()
            self.app_logger.removeHandler(handler)
        
        for handler in self.debug_logger.handlers[:]:
            handler.close()
            self.debug_logger.removeHandler(handler)
        
        self._setup_loggers()


# Global log manager instance
log_manager = LogManager()
