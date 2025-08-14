import discord
from discord import app_commands
from collections import defaultdict
import schedule
import asyncio
import json

from bot.config import config
from bot.logger import setup_logger
from bot.handlers.on_message import handle_background_message, handle_direct_message
from bot.handlers.utils import run_scheduler, scheduled_job, load_task_entry_messages, load_quiz_message, load_growth_photo_messages
from bot.utils.api_utils import APIUtils
from bot.utils.openai_utils import OpenAIUtils
from bot.utils.s3_image_utils import S3ImageUtils
from bot.views.mission import MilestoneSelectView
from bot.views.photo_mission import PhotoTaskSelectView
from bot.views.album_select_view import AlbumView

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
        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def call_photo_task(self, interaction: discord.Interaction):
        try:
            if not isinstance(interaction.channel, discord.channel.DMChannel):
                message = await interaction.response.send_message(
                    "嗨！請到「繪本工坊」查看製作繪本任務喔🧩",
                    ephemeral=True
                )
                return

            await interaction.response.defer(ephemeral=True)
            incomplete_missions = await self.api_utils.get_student_incomplete_photo_mission(str(interaction.user.id))
            if len(incomplete_missions) > 0:
                view = PhotoTaskSelectView(self, str(interaction.user.id), incomplete_missions)
                message = await interaction.followup.send(
                    "🧩 **以下是您未完成的照片任務，按下方按鈕開始製作繪本**",
                    view=view,
                    ephemeral=True
                )
            else:
                message = await interaction.followup.send(
                    "您目前沒有未完成的任務喔\n",
                    ephemeral=True
                )
        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def browse_growth_album(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            album_status = await self.api_utils.get_student_album_purchase_status(str(interaction.user.id))
            album_view = AlbumView(self, album_status)
            embed = album_view.get_current_embed()
            message = await interaction.followup.send(
                "📖 **以下是您的成長書櫃**\n點擊 ▶️ 查看下一本 | ◀️ 返回上一本",
                embed=embed,
                view=album_view,
                ephemeral=True
            )
            album_view.message = message
        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def setup_hook(self):
        await load_task_entry_messages(self)
        self.logger.info("Finished loading task entry messages")

        await load_quiz_message(self)
        self.logger.info("Finished loading quiz messages")

        await load_growth_photo_messages(self)
        self.logger.info("Finished loading growth photo messages")

        self.tree.add_command(
            app_commands.Command(
                name="查看育兒里程碑",
                description="查看五大照護育兒里程碑",
                callback=self.call_mission_start
            )
        )
        self.tree.add_command(
            app_commands.Command(
                name="補上傳照片",
                description="查看未完成繪本任務🧩",
                callback=self.call_photo_task
            )
        )
        self.tree.add_command(
            app_commands.Command(
                name="瀏覽繪本進度",
                description="查看繪本進度📖",
                callback=self.browse_growth_album
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
