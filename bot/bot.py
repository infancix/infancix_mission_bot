import discord
from discord import app_commands
import schedule
import asyncio

from bot.handlers.on_message import dispatch_message
from bot.config import config
from bot.utils.openai_utils import OpenAIUtils
from bot.utils.s3_image_utils import S3ImageUtils
from bot.utils.utils import job
from bot.logger import setup_logger

class MissionBot(discord.Client):
    def __init__(self, guild_id):
        self.guild_id = guild_id
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True

        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        self.gpt_client = OpenAIUtils(api_key=config.OPENAI_API_KEY)
        self.s3_client = S3ImageUtils("infancix-app-storage-jp")
        self.logger = setup_logger('MissionBot')

    async def setup_hook(self):
        self.tree.copy_global_to(guild=discord.Object(id=self.guild_id))
        await self.tree.sync(guild=discord.Object(id=self.guild_id))

    async def on_ready(self):
        self.logger.info(f'Logged in as {self.user.name} (ID: {self.user.id})')

    async def on_message(self, message):
        await dispatch_message(self, message)

def run_bot():
    if not isinstance(config.DISCORD_TOKEN, str):
        raise Exception('DISCORD_TOKEN is required')

    client = MissionBot(config.MY_GUILD_ID)

    #schedule.every().day.at("10:00").do(lambda: asyncio.create_task(job(client)))

    client.run(config.DISCORD_TOKEN)
