import json
from pathlib import Path
from bot.config import config

DATA_DIR = Path("bot/data")
if config.ENV:
    DATA_DIR = DATA_DIR / "dev"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

QUIZ_MESSAGE_LOG_PATH =  DATA_DIR / "quiz_message_records.json"
TASK_ENTRY_LOG_PATH =  DATA_DIR / "task_entry_records.json"
PHOTO_VIEW_LOG_PATH = DATA_DIR / "photo_view_records.json"
PHOTO_MISSION_STATUS_LOG_PATH = DATA_DIR / "photo_mission_status.json"

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

def save_task_entry_record(user_id: str, message_id: str, task_type:str, mission_id:int, max_records=5):
    records = load_task_entry_records()
    if user_id not in records:
        records[user_id] = []
    
    records[user_id] = [record for record in records[user_id] if record['mission_id'] != mission_id]
    records[user_id].append({
        'message_id': message_id,
        'task_type': task_type,
        'mission_id': mission_id,
    })

    if len(records[user_id]) > max_records:
        records[user_id].pop(0)

    with open(TASK_ENTRY_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def load_photo_view_records() -> dict:
    if PHOTO_VIEW_LOG_PATH.exists():
        with open(PHOTO_VIEW_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_photo_view_record(user_id: str, message_id: str, mission_id: str, book_id: int = None, image: str = None, aside_text: str = None, content: str = None):
    records = load_photo_view_records()
    photo_info = {
        'mission_id': mission_id,
        'book_number': book_id,
        'image': image,
        'aside_text': aside_text,
        'content': content
    }
    records[user_id] = (message_id, mission_id, photo_info)
    with open(PHOTO_VIEW_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_photo_view_record(user_id: str):
    records = load_photo_view_records()
    if user_id in records:
        del records[user_id]
        with open(PHOTO_VIEW_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

def load_photo_mission_status() -> dict:
    if PHOTO_MISSION_STATUS_LOG_PATH.exists():
        with open(PHOTO_MISSION_STATUS_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_photo_mission_status(user_id: str, mission_id: int):
    records = load_photo_mission_status()    
    records[user_id] = mission_id

    with open(PHOTO_MISSION_STATUS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_photo_mission_status(user_id: str):
    records = load_photo_mission_status()
    if user_id in records:
        del records[user_id]
        with open(PHOTO_MISSION_STATUS_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)
