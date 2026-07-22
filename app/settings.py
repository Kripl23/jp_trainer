import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PORT = int(os.getenv("PORT", "8040"))
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "jp_trainer.db"))
NEW_WORDS_PER_DAY = int(os.getenv("NEW_WORDS_PER_DAY", "10"))
LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))
