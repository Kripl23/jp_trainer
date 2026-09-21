import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

PORT = int(os.getenv("PORT", "8040"))
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "jp_trainer.db"))
QUIZ_QUESTIONS = int(os.getenv("QUIZ_QUESTIONS", "15"))
LOG_DIR = os.getenv("LOG_DIR", str(BASE_DIR / "logs"))
