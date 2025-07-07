import discord
from discord import app_commands
import schedule
import asyncio

from bot.config import config
from bot.logger import setup_logger
from bot.handlers.on_message import handle_dm
from bot.handlers.utils import job, run_scheduler, load_active_control_panel, load_control_panel_by_id, load_greeting_message
from bot.utils.api_utils import APIUtils
from bot.utils.openai_utils import OpenAIUtils
from bot.utils.s3_image_utils import S3ImageUtils
from bot.views.control_panel import ControlPanelView

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
        self.user_viewed_video = {}

        if not config.MISSION_BOT_ASSISTANT:
            config.MISSION_BOT_ASSISTANT = self.openai_utils.load_assistant('video_task')

        if not config.PHOTO_TASK_ASSISTANT:
            config.PHOTO_TASK_ASSISTANT = self.openai_utils.load_assistant('photo_task')

    async def whisper_comment(self, interaction: discord.Interaction, message: str):
        print(f"Interaction received: {interaction.channel}, {interaction.user.id}, {interaction.channel.id}")
        try:
            if isinstance(interaction.channel, discord.Thread):
                if str(interaction.channel.parent_id) not in config.channel_map:
                    return

                channel_id = str(interaction.channel.parent_id)
                await interaction.channel.send(message)
                await interaction.response.send_message(f"訊息已成功發送到貼文: {interaction.channel.name}", ephemeral=True)

            else: # TextChannel
                if str(interaction.channel.id) not in config.channel_map:
                    return

                channel_id = str(interaction.channel.id)
                await interaction.channel.send(message)
                await interaction.response.send_message(f"訊息已成功發送到頻道: {interaction.channel.name}", ephemeral=True)

            # Store message
            await self.api_utils.store_comment(str(interaction.user.id), config.channel_map[channel_id], str(interaction.channel.id), message)

        except Exception as e:
            print(f"Error while sending message: {e}")

    async def call_mission_start(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            is_in_mission_room = interaction.channel.id == config.MISSION_BOT_CHANNEL_ID

            if not is_in_mission_room:
                await interaction.followup.send(
                    "🚫 *請在 [任務佈告欄] 頻道使用此指令！*",
                    ephemeral=True
                )
                return

            target_channel = interaction.channel
            old_control_message, control_panel_view, control_panel_embed = await load_control_panel_by_id(self, str(interaction.user.id), target_channel)
            if old_control_message:
                await old_control_message.delete()
                self.logger.info(f"Remove out-dated control panel of user ({interaction.user.id}).")

            message = await interaction.followup.send(embed=control_panel_embed, view=control_panel_view)
            await self.api_utils.store_message(str(interaction.user.id), 'assistant', control_panel_view.embed_content, message_id=message.id)

        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def setup_hook(self):
        await load_active_control_panel(self)
        self.logger.info("Finished loading control panel")

        await load_greeting_message(self)
        self.logger.info("Finished loading greeting message")

        self.tree.add_command(
            app_commands.Command(
                name="加一說",
                description="將訊息以加一的身份發送到指定的貼文中",
                callback=self.whisper_comment
            ),
            guild=discord.Object(id=self.guild_id)
        )

        self.tree.add_command(
            app_commands.Command(
                name="照護課表",
                description="顯示照護課表",
                callback=self.call_mission_start
            )
        )
        self.tree.copy_global_to(guild=discord.Object(id=self.guild_id))
        await self.tree.sync(guild=discord.Object(id=self.guild_id))
        await self.tree.sync()

    async def on_ready(self):
        self.loop.create_task(run_scheduler())
        self.logger.info(f'Logged in as {self.user.name} (ID: {self.user.id})')
        #await job(self)

    async def on_reaction_add(self, reaction, user):
        if isinstance(reaction.message.channel, discord.DMChannel) and reaction.message.author == self.user:
            self.logger.info(f"Your message received a reaction: {reaction.emoji} from {user.name}")
            await self.api_utils.store_reaction(str(user.id), reaction.emoji)

    async def on_message(self, message):
        await handle_dm(self, message)

def run_bot():
    if not isinstance(config.DISCORD_TOKEN, str):
        raise Exception('DISCORD_TOKEN is required')

    client = MissionBot(config.MY_GUILD_ID)

    schedule.every().day.at("10:00").do(lambda: asyncio.create_task(job(client)))

    client.run(config.DISCORD_TOKEN)
