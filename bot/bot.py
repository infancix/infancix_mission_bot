import discord
from discord import app_commands
from collections import defaultdict
from datetime import datetime
import json

from bot.config import config
from bot.logger import setup_logger
from bot.handlers.on_message import handle_direct_message
from bot.utils.api_utils import APIUtils
from bot.utils.openai_utils import OpenAIUtils

class MissionBot(discord.Client):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        intents.reactions = True
        intents.guilds = True
        intents.members = True

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        self.logger = setup_logger('MissionBot')
        self.openai_utils = OpenAIUtils(api_key=config.OPENAI_API_KEY)
        self.api_utils = APIUtils(api_host=config.BABY_API_HOST, api_port=config.BABY_API_PORT)

        # variables to track user states
        self.photo_mission_replace_index = defaultdict(int)
        self.reset_baby_profile = defaultdict(int)
        self.skip_aside_text = defaultdict(int)
        self.skip_growth_info = defaultdict(int)
        self.submit_deadline = 5 # Default to 5th of each month

        with open("bot/resource/mission_instruction.json", "r") as file:
            mission_instruction = json.load(file)
            self.mission_questionnaire = {k: v['questionnaire_instruction'] for k, v in mission_instruction.items() if 'questionnaire_instruction' in v}

    async def setup_hook(self):
        # 繪本工坊服務已停止：移除所有 slash 指令
        self.tree.clear_commands(guild=None)
        self.tree.clear_commands(guild=discord.Object(id=self.guild_id))
        await self.tree.sync(guild=discord.Object(id=self.guild_id))
        await self.tree.sync()

    async def on_ready(self):
        # 繪本工坊服務已停止：不再啟動排程任務
        self.logger.info(f'Logged in as {self.user.name} (ID: {self.user.id})')

    async def on_reaction_add(self, reaction, user):
        if isinstance(reaction.message.channel, discord.DMChannel) and reaction.message.author == self.user:
            self.logger.info(f"Your message received a reaction: {reaction.emoji} from {user.name}")
            await self.api_utils.store_reaction(str(user.id), reaction.emoji)

    async def on_message(self, message):
        if message.author == self.user:
            return

        # 繪本工坊服務已停止：不再監聽背景頻道，僅回覆 DM 停止通知
        if isinstance(message.channel, discord.channel.DMChannel):
            await handle_direct_message(self, message)

def run_bot():
    if not isinstance(config.DISCORD_TOKEN, str):
        raise Exception('DISCORD_TOKEN is required')

    client = MissionBot(config.MY_GUILD_ID)

    # 繪本工坊服務已停止：不再註冊每日/每月排程任務

    client.run(config.DISCORD_TOKEN)
