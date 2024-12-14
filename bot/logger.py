import logging
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
log_file_path = base_dir / 'logs' / 'bot.log'

def setup_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file_path, mode='a', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(name)
    return logger

