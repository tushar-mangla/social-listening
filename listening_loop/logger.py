import logging
import os

def setup_logging():
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    info_log_path = os.path.join(log_dir, "info.log")
    error_log_path = os.path.join(log_dir, "error.log")
    
    logger = logging.getLogger("listening_loop")
    logger.setLevel(logging.INFO)
    
    # Avoid adding handlers multiple times if imported multiple times
    if not logger.handlers:
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Info handler
        info_handler = logging.FileHandler(info_log_path)
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(formatter)
        logger.addHandler(info_handler)
        
        # Error handler
        error_handler = logging.FileHandler(error_log_path)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger

logger = setup_logging()
