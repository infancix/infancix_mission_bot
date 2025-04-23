import discord
from discord import app_commands
import schedule
import asyncio

from bot.config import config
from bot.logger import setup_logger
from bot.handlers.on_message import handle_background_message, handle_direct_message
from bot.handlers.utils import run_scheduler, scheduled_job, load_messages
from bot.utils.message_tracker import save_control_panel_record
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

    async def call_mission_start(self, interaction: discord.Interaction):
        try:
            is_in_mission_room = str(interaction.channel.id) in [config.MISSION_BOT]

            if not is_in_mission_room:
                target_channel = await self.fetch_user(interaction.user.id)
                await interaction.response.send_message(
                    f"📢 *你的任務儀表板已更新，請到 <@{interaction.channel.id}> 查看！*",
                    ephemeral=True
                )
            else:
                target_channel = interaction.channel

            course_info = await self.api_utils.get_student_mission_notifications_by_id(interaction.user.id)
            view = ControlPanelView(self, str(interaction.user.id), course_info)
            embed = discord.Embed(
                title=f"📅 任務佈告欄",
                description=view.embed_content,
                color=discord.Color.blue()
            )
            if is_in_mission_room:
                await interaction.response.send_message(embed=embed, view=view)
                message = await interaction.original_response()
            else:
                message = await target_channel.send(embed=embed, view=view)

            # Store the message ID in the database
            await self.api_utils.store_message(str(interaction.user.id), 'assistant', view.embed_content)
            save_control_panel_record(str(interaction.user.id), str(message.id))

        except Exception as e:
            print(f"Error while sending message: {str(e)}")

    async def setup_hook(self):
        await load_messages(self)
        self.logger.info("Finished loading all messages")

        self.tree.add_command(
            app_commands.Command(
                name="任務佈告欄",
                description="顯示任務佈告欄",
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
        if (
            message.author == self.user
            and message.channel.id != config.BACKGROUND_LOG_CHANNEL_ID
        ):
            return

        if message.channel.id == config.BACKGROUND_LOG_CHANNEL_ID:
            await handle_background_message(self, message)
        elif isinstance(message.channel, discord.channel.DMChannel):
            if str(message.author.id) != '1281121934536605739':
                return
            await handle_direct_message(self, message)

def run_bot():
    if not isinstance(config.DISCORD_TOKEN, str):
        raise Exception('DISCORD_TOKEN is required')

    client = MissionBot(config.MY_GUILD_ID)

    #schedule.every().day.at("10:00").do(lambda: asyncio.create_task(scheduled_job(client)))

    client.run(config.DISCORD_DEV_TOKEN)
