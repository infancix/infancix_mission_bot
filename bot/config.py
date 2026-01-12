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

        self.book_intro_mission_map.update({book_id: mission_ids[0] for book_id, mission_ids in self.theme_book_mission_map.items()})
        self.theme_mission_list = [7001, 7008, 7015, 7022, 7029, 7036]

    def get_required_attachment_count(self, mission_id, attachment_type='photo'):
        """
        Get the required number of attachments for a mission.

        Args:
            mission_id: The mission ID
            attachment_type: 'photo', 'video', 'audio', or 'questionnaire'

        Returns:
            int: Required number of attachments (default: 1)
        """
        mission_id_str = str(mission_id)

        if attachment_type == 'photo':
            return int(self.photo_mission_required_count.get(mission_id_str, 1))
        elif attachment_type == 'video':
            return int(self.video_mission_required_count.get(mission_id_str, 1))
        elif attachment_type == 'audio':
            return int(self.audio_mission_required_count.get(mission_id_str, 1))
        elif attachment_type == 'questionnaire':
            return int(self.questionnaire_required_images.get(mission_id_str, 0))
        else:
            return 1

    def get_required_aside_text_count(self, mission_id, mission_type='photo'):
        """
        Get the required number of aside_text for a mission.

        Args:
            mission_id: The mission ID
            mission_type: 'photo', 'video', 'audio', or 'questionnaire'

        Returns:
            int: Required number of aside_text (default: 0 for photo/video/audio, 1 for questionnaire)
        """
        mission_id_str = str(mission_id)

        if mission_type == 'photo':
            return int(self.photo_aside_text_required_count.get(mission_id_str, 0))
        elif mission_type == 'video':
            return int(self.video_aside_text_required_count.get(mission_id_str, 0))
        elif mission_type == 'audio':
            return int(self.audio_aside_text_required_count.get(mission_id_str, 0))
        elif mission_type == 'questionnaire':
            return int(self.questionnaire_aside_text_required_count.get(mission_id_str, 1))
        else:
            return 0

    def get_prompt_file(self, mission_id):
        base_path = "bot/resource/prompts"
        if mission_id in self.baby_profile_registration_missions:
            return f"{base_path}/baby_intro_prompt.txt"
        elif mission_id == self.pregnant_registration_mission:
            return f"{base_path}/pregnant_registration_prompt.txt"
        elif mission_id in self.photo_mission_without_aside_text or mission_id in self.questionnaire_with_image_mission:
            return f"{base_path}/image_prompt.txt"
        elif mission_id in self.photo_mission_with_aside_text:
            return f"{base_path}/image_with_aside_text.txt"
        elif mission_id in self.relation_or_identity_mission:
            return f"{base_path}/relationship_identity_mission.txt"
        elif mission_id in self.photo_mission_with_title_and_content:
            return f"{base_path}/image_with_content.txt"
        elif mission_id in self.add_on_photo_mission:
            return f"{base_path}/add_on_mission_prompt.txt"
        elif mission_id in self.video_mission:
            return f"{base_path}/video_mission_prompt.txt"
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
            self.questionnaire_without_image_mission = [item for month_data in growth_book_missions
                for item in month_data.get('questionnaire_without_image_mission', [])
            ]
            self.questionnaire_with_image_mission = [item for month_data in growth_book_missions
                for item in month_data.get('questionnaire_with_image_mission', [])
            ]
            self.questionnaire_mission = self.questionnaire_without_image_mission + self.questionnaire_with_image_mission

            self.audio_mission = [item for month_data in growth_book_missions
                for item in month_data.get('audio_mission', [])
            ]

            self.video_mission = [item for month_data in growth_book_missions
                for item in month_data.get('video_mission', [])
            ]

            # Load required attachment counts for missions
            self.photo_mission_required_count = {}
            self.video_mission_required_count = {}
            self.audio_mission_required_count = {}
            self.questionnaire_required_images = {}

            # Load required aside_text counts for missions
            self.photo_aside_text_required_count = {}
            self.video_aside_text_required_count = {}
            self.audio_aside_text_required_count = {}
            self.questionnaire_aside_text_required_count = {}

            for book_data in growth_book_missions:
                # Merge photo mission required counts from all books
                if 'photo_mission_required_count' in book_data:
                    self.photo_mission_required_count.update(book_data['photo_mission_required_count'])
                # Merge video mission required counts from all books
                if 'video_mission_required_count' in book_data:
                    self.video_mission_required_count.update(book_data['video_mission_required_count'])
                # Merge audio mission required counts from all books
                if 'audio_mission_required_count' in book_data:
                    self.audio_mission_required_count.update(book_data['audio_mission_required_count'])
                # Merge questionnaire required images from all books
                if 'questionnaire_required_images' in book_data:
                    self.questionnaire_required_images.update(book_data['questionnaire_required_images'])

                # Merge aside_text required counts from all books
                if 'photo_aside_text_required_count' in book_data:
                    self.photo_aside_text_required_count.update(book_data['photo_aside_text_required_count'])
                if 'video_aside_text_required_count' in book_data:
                    self.video_aside_text_required_count.update(book_data['video_aside_text_required_count'])
                if 'audio_aside_text_required_count' in book_data:
                    self.audio_aside_text_required_count.update(book_data['audio_aside_text_required_count'])
                if 'questionnaire_aside_text_required_count' in book_data:
                    self.questionnaire_aside_text_required_count.update(book_data['questionnaire_aside_text_required_count'])

            # final confirmation mission
            self.confirm_album_mission = [item for month_data in growth_book_missions
                for item in month_data.get('confirm_growth_album_mission', [])
            ]

            self.theme_book_mission_map = {item['book_id']: item['mission_ids'] for item in theme_book_missions}
            self.growth_book_mission_map = {item['book_id']: item['mission_ids'] for item in growth_book_missions}

config = Config()
