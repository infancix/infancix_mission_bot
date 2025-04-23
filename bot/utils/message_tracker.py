import json
from pathlib import Path

GREETING_MESSAGE_LOG_PATH = Path("bot/data/greeting_message_records.json")
CONTROL_PANEL_LOG_PATH = Path("bot/data/control_panel_records.json")
QUIZ_MESSAGE_LOG_PATH = Path("bot/data/quiz_message_records.json")
TASK_ENTRY_LOG_PATH = Path("bot/data/task_entry_records.json")

def load_greeting_message_records() -> dict:
    if GREETING_MESSAGE_LOG_PATH.exists():
        with open(GREETING_MESSAGE_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_greeting_message_record(user_id: str, message_id: str):
    records = load_greeting_message_records()
    records[user_id] = message_id
    with open(GREETING_MESSAGE_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_greeting_message_record(user_id: str):
    records = load_greeting_message_records()
    if user_id in records:
        del records[user_id]
        with open(GREETING_MESSAGE_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

def load_control_panel_records() -> dict:
    if CONTROL_PANEL_LOG_PATH.exists():
        with open(CONTROL_PANEL_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_control_panel_record(user_id: str, message_id: str):
    records = load_control_panel_records()
    records[user_id] = message_id
    with open(CONTROL_PANEL_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_control_panel_record(user_id: str):
    records = load_control_panel_records()
    if user_id in records:
        del records[user_id]
        with open(CONTROL_PANEL_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

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

def save_task_entry_record(user_id: str, message_id: str, task_type:str, mission_id:int):
    records = load_task_entry_records()
    records[user_id] = (message_id, task_type, mission_id)
    with open(TASK_ENTRY_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def delete_task_entry_record(user_id: str):
    records = load_task_entry_records()
    if user_id in records:
        del records[user_id]
        with open(TASK_ENTRY_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)

