import os
import json
from dotenv import load_dotenv

class Config:
    def __init__(self):
        load_dotenv()

        self.ENV = True if os.getenv('ENV') == 'dev' else False
        self.ADMIN_USER_IDS = os.getenv('ADMIN_USER_ID_LIST').split('_')
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.DISCORD_DEV_TOKEN = os.getenv('DISCORD_DEV_TOKEN')
        self.MY_GUILD_ID = int(os.getenv('MY_GUILD_ID'))
        self.BACKGROUND_LOG_CHANNEL_ID = int(os.getenv('BACKGROUND_LOG_CHANNEL_ID'))
        self.FILE_UPLOAD_CHANNEL_ID = int(os.getenv('FILE_UPLOAD_CHANNEL_ID'))
        self.MISSION_BOT_CHANNEL_ID = int(os.getenv('MISSION_BOT_CHANNEL_ID'))
        self.MISSION_BOT = int(os.getenv('MISSION_BOT_ID'))
        self.BABY_API_HOST = os.getenv('BABY_API_HOST')
        self.BABY_API_PORT = os.getenv('BABY_API_PORT')

        self.MISSION_BOT = int(os.getenv('MISSION_BOT_ID'))
        self.DEV_BOT_ID = int(os.getenv('DEV_BOT_ID'))
        if self.ENV:
            self.MISSION_BOT = self.DEV_BOT_ID
            self.DISCORD_TOKEN = self.DISCORD_DEV_TOKEN

        self.IMAGE_ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.heic', '.heif']

        self.available_books = [1, 2, 3]
        self._load_mission_config()
        self.photo_mission_list = set(
            [self.baby_registration_mission] +
            self.relation_or_identity_mission +
            self.photo_mission_with_aside_text +
            self.photo_mission_without_aside_text +
            self.photo_mission_with_title_and_content +
            self.add_on_photo_mission
        )

        # theme story book
        self.theme_book_map = {
            13: 7001,
            14: 7008,
            15: 7015,
            16: 7022,
            17: 7029,
            18: 7036
        }
        self.theme_mission_list = [7001, 7008, 7015, 7022, 7029, 7036]

    def get_prompt_file(self, mission_id):
        base_path = "bot/resource/prompts"
        if mission_id in self.baby_profile_registration_missions:
            return f"{base_path}/baby_intro_prompt.txt"
        elif mission_id == self.pregnant_registration_mission:
            return f"{base_path}/pregnant_registration_prompt.txt"
        elif mission_id in self.photo_mission_without_aside_text:
            return f"{base_path}/image_prompt.txt"
        elif mission_id in self.photo_mission_with_aside_text:
            return f"{base_path}/image_with_aside_text.txt"
        elif mission_id in self.relation_or_identity_mission:
            return f"{base_path}/relationship_identity_mission.txt"
        elif mission_id in self.photo_mission_with_title_and_content:
            return f"{base_path}/image_with_content.txt"
        elif mission_id in self.add_on_photo_mission:
            return f"{base_path}/add_on_mission_prompt.txt"
        elif mission_id in self.audio_mission:
            return f"{base_path}/audio_mission_prompt.txt"
        elif mission_id >= 7001 and mission_id <= 7042:
            return f"{base_path}/theme_mission_prompt.txt"
        else:
            return f"{base_path}/class_question.txt"

    def _load_mission_config(self):
        with open("bot/resource/mission_config.json", "r") as f:
            mission_config = json.load(f)

            self.pregnant_registration_mission = mission_config['pregnant_registration_mission']
            self.baby_pre_registration_mission = mission_config['baby_pre_registration_mission']
            self.baby_registration_mission = mission_config['baby_registration_mission']
            self.baby_name_en_registration_missions = mission_config.get('baby_name_en_registration_missions', [])
            self.baby_profile_registration_missions = [self.baby_registration_mission] + self.baby_pre_registration_mission + self.baby_name_en_registration_missions

            # growth book missions
            growth_book_missions = mission_config['growth_book_missions']

            # book introduction mission
            self.book_intro_mission = [
                month_data['book_intro_mission'] for month_data in growth_book_missions
            ]
            self.book_first_mission = {
                month_data['month']: month_data['book_first_mission']
                for month_data in growth_book_missions
            }

            # relation and identity missions
            self.relation_mission = [item for month_data in growth_book_missions
                for item in month_data.get('relation_mission', [])
            ]
            self.identity_mission = [item for month_data in growth_book_missions
                for item in month_data.get('identity_mission', [])
            ]
            self.relation_or_identity_mission = self.relation_mission + self.identity_mission

            # photo missions
            self.photo_mission_with_aside_text = [item for month_data in growth_book_missions
                for item in month_data.get('photo_mission_with_aside_text', [])
            ]
            self.photo_mission_without_aside_text = [item for month_data in growth_book_missions
                for item in month_data.get('photo_mission_without_aside_text', [])
            ]
            self.photo_mission_with_title_and_content = [item for month_data in growth_book_missions
                for item in month_data.get('photo_mission_with_title_and_content', [])
            ]
            self.add_on_photo_mission = [item for month_data in growth_book_missions
                for item in month_data.get('add_on_photo_mission', [])
            ]

            # other missions
            self.questionnaire_mission = [item for month_data in growth_book_missions
                for item in month_data.get('questionnaire_mission', [])
            ]
            self.audio_mission = [item for month_data in growth_book_missions
                for item in month_data.get('audio_mission', [])
            ]

            # final confirmation mission
            self.confirm_album_mission = [item for month_data in growth_book_missions
                for item in month_data.get('confirm_growth_album_mission', [])
            ]

config = Config()
