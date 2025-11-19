import discord
from discord import app_commands
from collections import defaultdict
from datetime import datetime
import schedule
import asyncio
import json

from bot.config import config
from bot.logger import setup_logger
from bot.handlers.on_message import handle_background_message, handle_direct_message
from bot.handlers.utils import (
    run_scheduler,
    daily_job,
    monthly_print_reminder_job,
    load_task_entry_messages,
    load_growth_photo_messages,
    load_theme_book_edit_messages,
    load_questionnaire_messages,
    load_confirm_growth_album_messages
)
from bot.utils.message_tracker import (
    save_confirm_growth_albums_record
)
from bot.utils.api_utils import APIUtils
from bot.utils.openai_utils import OpenAIUtils
from bot.views.album_select_view import BookMenuView
from bot.views.menu_view import KnowledgeMenuView

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

        with open("bot/resource/mission_questionnaire.json", "r") as file:
            self.mission_questionnaire = json.load(file)

    async def query_knowledge_menu(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            message = await interaction.followup.send(
                "請先選擇想看的育兒知識",
                view=KnowledgeMenuView(self),
                ephemeral=True
            )
        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def query_bookcase_menu(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            message = await interaction.followup.send(
                "請先選擇製作的繪本：",
                view=BookMenuView(self),
                ephemeral=True
            )
        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def setup_hook(self):
        await load_task_entry_messages(self)
        self.logger.info("Finished loading task entry messages")

        await load_growth_photo_messages(self)
        self.logger.info("Finished loading growth photo messages")

        await load_theme_book_edit_messages(self)
        self.logger.info("Finished loading theme book edit messages")

        await load_questionnaire_messages(self)
        self.logger.info("Finished loading questionnaire messages")

        await load_confirm_growth_album_messages(self)
        self.logger.info("Finished loading confirm growth album messages")

        self.tree.add_command(
            app_commands.Command(
                name="科學育兒懶人包",
                description="從寶寶的發展、照護知識，到陪伴爸媽的 0–3 歲育兒專欄，讓育兒路上不孤單。",
                callback=self.query_knowledge_menu
            )
        )
        self.tree.add_command(
            app_commands.Command(
                name="我的書櫃",
                description="管理您的寶寶繪本：修改照片、繼續製作、查看進度，並完成送印📖",
                callback=self.query_bookcase_menu
            )
        )
        self.tree.copy_global_to(guild=discord.Object(id=self.guild_id))
        await self.tree.sync(guild=discord.Object(id=self.guild_id))
        await self.tree.sync()

    async def on_ready(self):
        self.loop.create_task(run_scheduler())
        self.logger.info(f'Logged in as {self.user.name} (ID: {self.user.id})')

    async def on_reaction_add(self, reaction, user):
        if isinstance(reaction.message.channel, discord.DMChannel) and reaction.message.author == self.user:
            self.logger.info(f"Your message received a reaction: {reaction.emoji} from {user.name}")
            await self.api_utils.store_reaction(str(user.id), reaction.emoji)

    async def on_message(self, message):
        if (
            message.author == self.user
            and message.channel.id != config.BACKGROUND_LOG_CHANNEL_ID
        ):
            return

        if message.channel.id == config.BACKGROUND_LOG_CHANNEL_ID:
            await handle_background_message(self, message)
        elif isinstance(message.channel, discord.channel.DMChannel):
            await handle_direct_message(self, message)

def run_bot():
    if not isinstance(config.DISCORD_TOKEN, str):
        raise Exception('DISCORD_TOKEN is required')

    client = MissionBot(config.MY_GUILD_ID)

    if not config.ENV:
        schedule.every().day.at("10:00").do(lambda: asyncio.create_task(daily_job(client)))
        schedule.every().day.at("12:30").do(lambda: asyncio.create_task(monthly_print_reminder_job(client)))

    client.run(config.DISCORD_TOKEN)
