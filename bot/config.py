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

config = Config()
