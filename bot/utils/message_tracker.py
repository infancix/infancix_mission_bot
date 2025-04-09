import json
from pathlib import Path

MESSAGE_LOG_PATH = Path("bot/data/greeting_message_records.json")

def load_message_records() -> dict:
    if MESSAGE_LOG_PATH.exists():
        with open(MESSAGE_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_message_record(user_id: str, message_id: str):
    records = load_message_records()
    records[user_id] = message_id
    with open(MESSAGE_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)
