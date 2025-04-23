import json
from pathlib import Path

GREETING_MESSAGE_LOG_PATH = Path("bot/data/greeting_message_records.json")
CONTROL_PANEL_LOG_PATH = Path("bot/data/control_panel_records.json")
QUIZ_MESSAGE_LOG_PATH = Path("bot/data/quiz_message_records.json")
REPLY_OPTION_LOG_PATH = Path("bot/data/reply_option_records.json")

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

def load_quiz_message_records() -> dict:
    if QUIZ_MESSAGE_LOG_PATH.exists():
        with open(QUIZ_MESSAGE_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_quiz_message_record(user_id: str, message_id: str, quiz_options, quiz_answer):
    records = load_quiz_message_records()
    records[user_id] = (message_id, quiz_options, quiz_answer)
    with open(QUIZ_MESSAGE_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)

def load_reply_option_records() -> dict:
    if REPLY_OPTION_LOG_PATH.exists():
        with open(REPLY_OPTION_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_reply_option_record(user_id: str, message_id: str, options: list):
    records = load_reply_option_records()
    records[user_id] = (message_id, options)
    with open(REPLY_OPTION_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4, ensure_ascii=False)
