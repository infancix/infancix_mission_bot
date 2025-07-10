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
        self.MISSION_BOT_ASSISTANT = 'asst_DlqSJaUKd9K118tbYvB4EbfD'
        self.PHOTO_TASK_ASSISTANT = 'asst_NKABptwzFlKB9kZnm2f8QbAa'
        self.ASIDE_TEXT_ASSISTANT = 'asst_kWEM7k1s3S6670Vk7qVPKd9h'
        self.CONTENT_ASSISTANT = 'asst_ytMVwKFd6ik2rKpHOqepqohe'
        self.BABY_INTRO_ASSISTANT = 'asst_Cgeuvc8kSBtgqSlFY51QKTPZ'
        self.FAMILY_INTRO_ASSISTANT = 'asst_50zwOomgzQuwQvqPkKzeNfIj'
        self.PRENGNANCY_TASK_ASSISTANT = 'asst_hP8Ist5VpL0XxxLfE8kvEHEo'

        self.MISSION_BOT = int(os.getenv('MISSION_BOT_ID'))
        self.DEV_BOT_ID = int(os.getenv('DEV_BOT_ID'))
        if self.ENV:
            self.MISSION_BOT = self.DEV_BOT_ID
            self.DISCORD_TOKEN = self.DISCORD_DEV_TOKEN

        self.channel_map = {
            '1166487593492418594': '社團大廳',
            '1331493631076335668': '🤰孕期聊天室',
            '1331493915622375458': '👼小寶聊天室',
            '1331494007532027964': '🧒大寶聊天室',
            '1319684958897569913': '匿名討論區',
            '1271005966439026750': '🐛問題回報',
            '1271006617797791806': '⛲功能許願池',
            '1326726788054913066': '放電地圖',
            '1326776591333724242': '🌏放電地球儀',
            '1329006192797814886': '🥄寶寶副食品',
            '1338714450047533066': '💸好物排行榜',
            '1330108728904781895': '寶寶知識便利貼',
            '1327103002728726640': '新手指南',
            '1271101330852937890': '無毒認證標籤商店',
            '1271002121508229221': '👾discord官方專屬(測試頻道)',
        }

        self.service_role = [
            '1281121934536605739',
            '719770422542860359',
            '456342016276693022',
            '680406577420697768',
            '1290138246273306755'
        ]

        self.pregnancy_register_mission = 101
        self.baby_register_mission = 1001
        self.quiz_mission_with_photo_tasks = [2, 6, 16, 20, 30, 38, 44, 50, 58, 65]
        self.photo_mission_with_aside_text = [3, 4, 5, 15, 1004, 1005, 1006, 1007]
        self.family_intro_mission = [1002, 1003]
        self.photo_mission_with_title_and_content = [1008]
        self.photo_mission_list = set(
            [self.baby_register_mission] +
            self.quiz_mission_with_photo_tasks +
            self.photo_mission_with_aside_text +
            self.family_intro_mission +
            self.photo_mission_with_title_and_content
        )
        self.first_mission_per_book = [1001]
    
    def get_assistant_id(self, mission_id):
        if mission_id == self.baby_register_mission:
            return self.BABY_INTRO_ASSISTANT
        elif mission_id == self.pregnancy_register_mission:
            return self.PRENGNANCY_TASK_ASSISTANT
        elif mission_id in self.quiz_mission_with_photo_tasks:
            return self.PHOTO_TASK_ASSISTANT
        elif mission_id in self.photo_mission_with_aside_text:
            return self.ASIDE_TEXT_ASSISTANT
        elif mission_id in self.family_intro_mission:
            return self.FAMILY_INTRO_ASSISTANT
        elif mission_id in self.photo_mission_with_title_and_content:
            return self.CONTENT_ASSISTANT
        elif mission_id < 100:
            return self.MISSION_BOT_ASSISTANT
        else:
            return None

config = Config()
