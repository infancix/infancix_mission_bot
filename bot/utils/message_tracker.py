import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from bot.config import config

DATA_DIR = Path("bot/data")
if config.ENV:
    DATA_DIR = DATA_DIR / "dev"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

QUIZ_MESSAGE_LOG_PATH =  DATA_DIR / "quiz_message_records.json"
TASK_ENTRY_LOG_PATH =  DATA_DIR / "task_entry_records.json"
PHOTO_VIEW_LOG_PATH = DATA_DIR / "photo_view_records.json"

def load_quiz_message_records() -> dict:
    if QUIZ_MESSAGE_LOG_PATH.exists():
        with open(QUIZ_MESSAGE_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_quiz_message_record(user_id: str, message_id: str, mission_id: int, current_round: int, score: int):
    records = load_quiz_message_records()
    records[user_id] = (message_id, mission_id, current_round, score)
    with open(QUIZ_MESSAGE_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_quiz_message_record(user_id: str):
    records = load_quiz_message_records()
    if user_id in records:
        del records[user_id]
        with open(QUIZ_MESSAGE_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

def load_task_entry_records() -> dict:
    if TASK_ENTRY_LOG_PATH.exists():
        with open(TASK_ENTRY_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_task_entry_record(user_id: str, message_id: str, task_type:str, mission_id:int, book_data=None, baby_data=None, max_records=10):
    records = load_task_entry_records()
    if user_id not in records:
        records[user_id] = defaultdict(dict)
    
    records[user_id][str(mission_id)] = {
        "message_id": message_id,
        "task_type": task_type,
        "book_data": book_data,
        "baby_data": book_data,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if len(records[user_id]) > max_records:
        records[user_id] = dict(sorted(records[user_id].items(), key=lambda x: x[1]['date'], reverse=True)[:max_records])

    with open(TASK_ENTRY_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def load_photo_view_records() -> dict:
    if PHOTO_VIEW_LOG_PATH.exists():
        with open(PHOTO_VIEW_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_photo_view_record(user_id: str, message_id: str, mission_id: str):
    records = load_photo_view_records()
    records[user_id] = (message_id, mission_id)
    with open(PHOTO_VIEW_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_photo_view_record(user_id: str):
    records = load_photo_view_records()
    if user_id in records:
        del records[user_id]
        with open(PHOTO_VIEW_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)
