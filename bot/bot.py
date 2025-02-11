import discord
from discord import app_commands
import schedule
import asyncio

from bot.config import config
from bot.logger import setup_logger
from bot.handlers.on_message import handle_dm
from bot.handlers.utils import job
from bot.utils.api_utils import APIUtils
from bot.utils.openai_utils import OpenAIUtils
from bot.utils.s3_image_utils import S3ImageUtils

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

    async def setup_hook(self):
        self.tree.add_command(
            app_commands.Command(
                name="加一說",
                description="將訊息以加一的身份發送到指定的貼文中",
                callback=self.whisper_comment
            ),
            guild=discord.Object(id=self.guild_id)
        )
        self.tree.copy_global_to(guild=discord.Object(id=self.guild_id))
        await self.tree.sync(guild=discord.Object(id=self.guild_id))

    async def on_ready(self):
        self.logger.info(f'Logged in as {self.user.name} (ID: {self.user.id})')

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

    #schedule.every().day.at("10:00").do(lambda: asyncio.create_task(job(client)))

    client.run(config.DISCORD_TOKEN)
