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
GROWTH_ALBUM_LOG_PATH = DATA_DIR / "growth_album_records.json"
CONFIRM_GROWTH_ALBUMS_LOG_PATH = DATA_DIR / "confirm_growth_albums_records.json"
THEME_BOOK_EDIT_LOG_PATH = DATA_DIR / "theme_book_edit_records.json"
CONVERSATION_LOG_PATH = DATA_DIR / "conversation_records.json"
QUESTIONNAIRE_LOG_PATH = DATA_DIR / "questionnaire_records.json"
MISSION_LOG_PATH = DATA_DIR / "mission_records.json"

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
    if user_id not in records or str(mission_id) not in records[user_id]:
        records[user_id] = {} # remove all the previous records for this user

    records[user_id][str(mission_id)] = {
        "message_id": message_id,
        "task_type": task_type,
        "result": result,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

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

def save_growth_photo_records(user_id: str, message_id: str, mission_id: int, result=None):
    records = load_growth_photo_records()
    if user_id not in records or str(mission_id) not in records[user_id]:
        records[user_id] = {} # remove all the previous records for this user

    records[user_id][str(mission_id)] = {
        "message_id": message_id,
        "result": result,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

def load_confirm_growth_albums_records() -> dict:
    if CONFIRM_GROWTH_ALBUMS_LOG_PATH.exists():
        with open(CONFIRM_GROWTH_ALBUMS_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_confirm_growth_albums_record(user_id: str, message_id: str, albums_info=None, incomplete_missions=None):
    records = load_confirm_growth_albums_records()
    records[user_id] = {
        "message_id": message_id,
        "albums_info": albums_info,
        "incomplete_missions": incomplete_missions,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(CONFIRM_GROWTH_ALBUMS_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_confirm_growth_albums_record(user_id: str):
    records = load_confirm_growth_albums_records()
    if user_id in records:
        del records[user_id]
        with open(CONFIRM_GROWTH_ALBUMS_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

def load_theme_book_edit_records() -> dict:
    if THEME_BOOK_EDIT_LOG_PATH.exists():
        with open(THEME_BOOK_EDIT_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_user_theme_book_edit_record(user_id: str, mission_id: int) -> dict:
    records = load_theme_book_edit_records()
    if user_id in records and str(mission_id) in records[user_id]:
        return records[user_id][str(mission_id)]
    return {}

def save_theme_book_edit_record(user_id: str, message_id: str, mission_id: int, result=None):
    records = load_theme_book_edit_records()
    if user_id not in records or str(mission_id) not in records[user_id]:
        records[user_id] = {}  # remove all the previous records for this user

    records[user_id][str(mission_id)] = {
        "message_id": message_id,
        "result": result,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(THEME_BOOK_EDIT_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_theme_book_edit_record(user_id: str, mission_id: int):
    records = load_theme_book_edit_records()
    if user_id in records and str(mission_id) in records[user_id]:
        del records[user_id][str(mission_id)]
        if not records[user_id]:  # Remove user entry if no missions left
            del records[user_id]
        with open(THEME_BOOK_EDIT_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

def load_questionnaire_records() -> dict:
    if QUESTIONNAIRE_LOG_PATH.exists():
        with open(QUESTIONNAIRE_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_questionnaire_record(user_id: str, message_id: str, mission_id: int, current_round: int, clicked_options: set):
    records = load_questionnaire_records()
    if user_id not in records or str(mission_id) not in records[user_id]:
        records[user_id] = defaultdict(list)  # remove all the previous records for this user

    mission_records = records[user_id][str(mission_id)]
    while len(mission_records) <= current_round:
        mission_records.append({
            "message_id": None,
            "current_round": len(mission_records)
        })

    mission_records[current_round] = {
        "message_id": message_id,
        "current_round": current_round,
        "clicked_options": list(clicked_options),
    }

    with open(QUESTIONNAIRE_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_questionnaire_record(user_id: str, mission_id: int):
    records = load_questionnaire_records()
    if user_id in records and str(mission_id) in records[user_id]:
        del records[user_id][str(mission_id)]
        if not records[user_id]:  # Remove user entry if no missions left
            del records[user_id]
        with open(QUESTIONNAIRE_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

def load_mission_records() -> dict:
    if MISSION_LOG_PATH.exists():
        with open(MISSION_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_mission_record(user_id: str, mission_id: int, result: dict):
    records = load_mission_records()
    # Only keep the latest record
    records[user_id] = {
        "mission_id": mission_id,
        "result": result,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(MISSION_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def get_mission_record(user_id: str, mission_id: int) -> dict:
    records = load_mission_records()
    user_record = records.get(user_id, {})
    if user_record.get("mission_id") == mission_id:
        return user_record.get("result", {})
    return {}

def delete_mission_record(user_id: str):
    records = load_mission_records()
    if user_id in records:
        del records[user_id]
        with open(MISSION_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)
