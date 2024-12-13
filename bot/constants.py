import json

TASK_MEDAL = {}

with open("bot/data/mission_transcriptions.json", "r") as file:
    transcriptions = json.load(file)

MISSIONS = {obj['mission_id']: obj for obj in transcriptions}
