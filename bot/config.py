import os

from dotenv import load_dotenv

class Config:
    def __init__(self):
        load_dotenv()

        self.ENV = True if os.getenv('ENV') == 'dev' else False
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DISCORD_DEV_TOKEN = os.getenv('DISCORD_DEV_TOKEN')
        self.MY_GUILD_ID = int(os.getenv('MY_GUILD_ID'))
        self.BACKGROUND_LOG_CHANNEL_ID = int(os.getenv('BACKGROUND_LOG_CHANNEL_ID'))
        self.MISSION_BOT_CHANNEL_ID = int(os.getenv('MISSION_BOT_CHANNEL_ID'))
        self.MISSION_BOT = int(os.getenv('MISSION_BOT_ID'))
        self.BABY_API_HOST = os.getenv('BABY_API_HOST')
        self.BABY_API_PORT = os.getenv('BABY_API_PORT')

        self.MISSION_BOT = int(os.getenv('MISSION_BOT_ID'))
        self.DEV_BOT_ID = int(os.getenv('DEV_BOT_ID'))
        if self.ENV:
            self.MISSION_BOT = self.DEV_BOT_ID
            self.DISCORD_TOKEN = self.DISCORD_DEV_TOKEN

        self.pregnancy_register_mission = 101
        self.baby_register_mission = 1001
        self.photo_mission_with_aside_text = [2, 3, 5, 6, 1004, 1006, 1007]
        self.photo_mission_without_aside_text = [1005]
        self.family_intro_mission = [1002, 1003]
        self.photo_mission_with_title_and_content = [1008]
        self.add_on_photo_mission = [1009]
        self.photo_mission_list = set(
            [self.baby_register_mission] +
            self.photo_mission_with_aside_text +
            self.photo_mission_without_aside_text +
            self.family_intro_mission +
            self.photo_mission_with_title_and_content +
            self.add_on_photo_mission
        )
        self.first_mission_per_book = [1004]

    def get_prompt_file(self, mission_id, current_step=1):
        base_path = "bot/resource/prompts"
        if mission_id == self.baby_register_mission:
            if current_step == 1:
                return f"{base_path}/baby_intro_prompt.txt"
            else:
                return f"{base_path}/image_prompt.txt"
        elif mission_id == self.pregnancy_register_mission:
            return f"{base_path}/pregnancy_register_prompt.txt"
        elif mission_id in self.photo_mission_without_aside_text:
            return f"{base_path}/image_prompt.txt"
        elif mission_id in self.photo_mission_with_aside_text:
            return f"{base_path}/image_with_aside_text.txt"
        elif mission_id in self.family_intro_mission:
            return f"{base_path}/family_relationship.txt"
        elif mission_id in self.photo_mission_with_title_and_content:
            return f"{base_path}/image_with_content.txt"
        elif mission_id in self.add_on_photo_mission:
            return f"{base_path}/add_on_mission_prompt.txt"
        else:
            return f"{base_path}/class_question.txt"

config = Config()
