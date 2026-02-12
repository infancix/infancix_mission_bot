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

        self._load_mission_config()
        self.photo_mission_list = set(
            [self.baby_registration_mission] +
            self.photo_mission +
            self.relation_or_identity_mission +
            self.letter_mission +
            self.short_answer_mission +
            self.add_on_photo_mission
        )

        self.book_intro_mission_map.update({book_id: mission_ids[0] for book_id, mission_ids in self.theme_book_mission_map.items()})
        self.theme_mission_list = [7001, 7008, 7015, 7022, 7029, 7036]

    def get_required_attachment_count(self, mission_id, attachment_type='photo'):
        """
        Get the required number of attachments for a mission.

        Args:
            mission_id: The mission ID
            attachment_type: 'photo', 'video', or 'audio'

        Returns:
            int: Required number of attachments (default: 1)
        """
        mission_id_str = str(mission_id)

        # Try mission_requirements first (new unified format)
        requirements = self.mission_requirements.get(mission_id_str, {})
        if attachment_type in requirements:
            return int(requirements[attachment_type])
        else:
            return 0

    def get_required_aside_text_count(self, mission_id, mission_type='aside_text'):
        """
        Get the required number of aside_text for a mission.

        Args:
            mission_id: The mission ID
            mission_type: 'photo', 'video', or 'audio'

        Returns:
            int: Required number of aside_text (default: 0)
        """
        mission_id_str = str(mission_id)

        # Try mission_requirements first (new unified format)
        requirements = self.mission_requirements.get(mission_id_str, {})
        if 'aside_text' in requirements:
            return int(requirements[mission_type])
        else:
            return 0

    def get_prompt_file(self, mission_id):
        """
        Get the appropriate prompt file for a mission.
        Simplified to use mission type classification.
        Mission validation logic is determined by mission_requirements.
        """
        base_path = "bot/resource/prompts"

        # Registration missions
        if mission_id in self.baby_profile_registration_missions:
            return f"{base_path}/baby_intro_prompt.txt"

        # Pregnant registration missions
        elif mission_id == self.pregnant_registration_mission:
            return f"{base_path}/pregnant_registration_prompt.txt"

        # Relation/identity missions - use specific prompt with relationship term rules
        elif mission_id in self.relation_or_identity_mission:
            return f"{base_path}/relationship_identity_prompt.txt"

        # Letter missions
        elif mission_id in self.letter_mission:
            return f"{base_path}/letter_prompt.txt"

        # Add-on photo missions
        elif mission_id in self.add_on_photo_mission:
            return f"{base_path}/add_on_mission_prompt.txt"

        # General photo missions - simple aside_text with typo correction only
        elif mission_id in self.photo_mission:
            return f"{base_path}/aside_text_prompt.txt"

        # Questionnaire missions
        elif mission_id in self.questionnaire_mission or mission_id in self.short_answer_mission:
            return f"{base_path}/short_answer_prompt.txt"

        # Video missions
        elif mission_id in self.video_mission:
            return f"{base_path}/video_mission_prompt.txt"

        # Audio missions
        elif mission_id in self.audio_mission:
            return f"{base_path}/audio_mission_prompt.txt"

        # Theme missions
        elif mission_id >= 7001 and mission_id <= 7042:
            return f"{base_path}/short_answer_prompt.txt"

        # Default fallback
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
            theme_book_missions = mission_config.get('theme_book_missions', [])

            # book introduction mission
            self.book_intro_mission = [
                month_data['book_intro_mission'] for month_data in growth_book_missions
            ]

            self.book_intro_mission_map = {
                month_data['book_id']: month_data['book_intro_mission']
                for month_data in growth_book_missions
            }

            self.book_first_mission_map = {
                month_data['book_id']: month_data['book_first_mission']
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
            self.photo_mission = [item for month_data in growth_book_missions
                for item in month_data.get('photo_mission', [])
            ]
            self.add_on_photo_mission = [item for month_data in growth_book_missions
                for item in month_data.get('add_on_photo_mission', [])
            ]

            # Questionnaire missions (multiple choice / single choice)
            self.questionnaire_mission = [item for month_data in growth_book_missions
                for item in month_data.get('questionnaire_mission', [])
            ]

            # Letter missions (photo + long text for letter writing)
            self.letter_mission = [item for month_data in growth_book_missions
                for item in month_data.get('letter_mission', [])
            ]

            # Short answer missions (kind of photo mission)
            self.short_answer_mission = [item for month_data in growth_book_missions
                for item in month_data.get('short_answer_mission', [])
            ]

            self.audio_mission = [item for month_data in growth_book_missions
                for item in month_data.get('audio_mission', [])
            ]

            self.video_mission = [item for month_data in growth_book_missions
                for item in month_data.get('video_mission', [])
            ]

            # Load mission requirements (unified format)
            self.mission_requirements = {}
            for book_data in growth_book_missions:
                # Merge mission_requirements from all books
                if 'mission_requirements' in book_data:
                    self.mission_requirements.update(book_data['mission_requirements'])

            # Load mission requirements from theme books
            for book_data in theme_book_missions:
                if 'mission_requirements' in book_data:
                    self.mission_requirements.update(book_data['mission_requirements'])

            # final confirmation mission
            self.confirm_album_mission = [item for month_data in growth_book_missions
                for item in month_data.get('confirm_growth_album_mission', [])
            ]

            self.theme_book_mission_map = {item['book_id']: item['mission_ids'] for item in theme_book_missions}
            self.growth_book_mission_map = {item['book_id']: item['mission_ids'] for item in growth_book_missions}

config = Config()
