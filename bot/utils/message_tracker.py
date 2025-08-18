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
GROWTH_PHOTO_LOG_PATH = DATA_DIR / "growth_photo_records.json"
CONVERSATION_LOG_PATH = DATA_DIR / "conversation_records.json"

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

def save_task_entry_record(user_id: str, message_id: str, task_type:str, mission_id:int, result=None):
    records = load_task_entry_records()
    if user_id not in records:
        records[user_id] = {}

    if str(mission_id) not in records[user_id]:
        records[user_id] = {} # remove all the previous records for this user

    records[user_id][str(mission_id)] = {
        "message_id": message_id,
        "task_type": task_type,
        "result": result,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if len(records[user_id]) > max_records:
        records[user_id] = dict(sorted(records[user_id].items(), key=lambda x: x[1]['date'], reverse=True)[:max_records])

    with open(TASK_ENTRY_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_task_entry_record(user_id: str, mission_id: int):
    records = load_task_entry_records()
    if user_id in records and str(mission_id) in records[user_id]:
        del records[user_id][str(mission_id)]
        if not records[user_id]:  # Remove user entry if no missions left
            del records[user_id]
        with open(TASK_ENTRY_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

def load_growth_photo_records() -> dict:
    if GROWTH_PHOTO_LOG_PATH.exists():
        with open(GROWTH_PHOTO_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_growth_photo_records(user_id: str, message_id: str, mission_id: int):
    records = load_growth_photo_records()
    if user_id not in records:
        records[user_id] = {}

    records[user_id][str(mission_id)] = {
        "message_id": message_id,
    }

    with open(GROWTH_PHOTO_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_growth_photo_record(user_id: str, mission_id: int):
    records = load_growth_photo_records()
    if user_id in records and str(mission_id) in records[user_id]:
        del records[user_id][str(mission_id)]
        if not records[user_id]:  # Remove user entry if no missions left
            del records[user_id]
        with open(GROWTH_PHOTO_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

def load_conversations_records() -> dict:
    if CONVERSATION_LOG_PATH.exists():
        with open(CONVERSATION_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_conversations_record(user_id: str, mission_id: int, role: str, message: str):
    records = load_conversations_records()
    if str(user_id) not in records:
        records[str(user_id)] = {}

    if str(mission_id) not in records[str(user_id)]:
        records[str(user_id)] = {} # remove all the previous records for this user
        records[str(user_id)][str(mission_id)] = []

    records[str(user_id)][str(mission_id)].append({
        "role": role,
        "message": message,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    with open(CONVERSATION_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_conversations_record(user_id: str, mission_id: int):
    records = load_conversations_records()
    if user_id in records and str(mission_id) in records[user_id]:
        del records[user_id][str(mission_id)]
        if not records[user_id]:  # Remove user entry if no missions left
            del records[user_id]
        with open(CONVERSATION_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)
