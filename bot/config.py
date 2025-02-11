import os

from dotenv import load_dotenv


class Config:
    def __init__(self):
        load_dotenv()

        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
        self.DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
        self.MY_GUILD_ID = int(os.getenv('MY_GUILD_ID'))
        self.BACKGROUND_LOG_CHANNEL_ID = int(os.getenv('BACKGROUND_LOG_CHANNEL_ID'))
        self.MISSION_BOT = int(os.getenv('MISSION_BOT_ID'))
        self.BABY_API_HOST = os.getenv('BABY_API_HOST')
        self.BABY_API_PORT = os.getenv('BABY_API_PORT')

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

        self.record_mission_list = [32, 39, 45, 54, 67]

        self.class_step = {
            0: '未發送',
            1: 'Hello 階段',
            2: '課程講解階段',
            3: '測驗階段',
            4: '照片分享階段',
            5: '課程後重點整理階段',
        }

config = Config()
