import discord
from discord import app_commands
from collections import defaultdict
import schedule
import asyncio
import json

from bot.config import config
from bot.logger import setup_logger
from bot.handlers.on_message import handle_background_message, handle_direct_message
from bot.handlers.utils import run_scheduler, scheduled_job, load_task_entry_messages, load_quiz_message, load_photo_view_messages
from bot.utils.api_utils import APIUtils
from bot.utils.openai_utils import OpenAIUtils
from bot.utils.s3_image_utils import S3ImageUtils
from bot.views.mission import MilestoneSelectView
from bot.views.photo_mission import PhotoTaskSelectView

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
        self.s3_client = S3ImageUtils("infancix-app-storage-jp")
        self.growth_album = defaultdict(list)

        with open("bot/resource/mission_quiz.json", "r") as file:
            self.mission_quiz = json.load(file)

    async def call_mission_start(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            student_milestones = await self.api_utils.get_student_milestones(str(interaction.user.id))
            milestone_view = MilestoneSelectView(self, str(interaction.user.id), student_milestones)
            message = await interaction.followup.send(
                "🏆 ** 以下是您的任務進度，按下方按鈕開始任務**",
                view=milestone_view,
                ephemeral=True
            )
            #save_control_panel_record(str(interaction.user.id), str(message.id))
        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def call_photo_task(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            student_albums = await self.api_utils.get_student_growthalbums(str(interaction.user.id))
            view = PhotoTaskSelectView(self, str(interaction.user.id), student_albums)
            message = await interaction.followup.send(
                "🧩 ** 以下是您的回憶碎片，按下方按鈕開始製作繪本**",
                view=view,
                ephemeral=True
            )
        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def setup_hook(self):
        await load_task_entry_messages(self)
        self.logger.info("Finished loading task entry messages")

        await load_quiz_message(self)
        self.logger.info("Finished loading quiz messages")

        await load_photo_view_messages(self)
        self.logger.info("Finished loading photo view messages")

        self.tree.add_command(
            app_commands.Command(
                name="任務佈告欄",
                description="查看任務里程碑進度🏆",
                callback=self.call_mission_start
            )
        )
        self.tree.add_command(
            app_commands.Command(
                name="回憶寶箱",
                description="查看回憶碎片🧩",
                callback=self.call_photo_task
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

    #schedule.every().day.at("10:00").do(lambda: asyncio.create_task(scheduled_job(client)))

    client.run(config.DISCORD_TOKEN)
