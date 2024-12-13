import re

import discord

from bot.config import config
from bot.handlers.utils import handle_start_mission, handle_dm

async def dispatch_message(client, message):
    if (
        message.author == client.user
        and message.channel.id != config.BACKGROUND_LOG_CHANNEL_ID
    ):
        return

    if message.channel.id == config.BACKGROUND_LOG_CHANNEL_ID:
        if len(message.mentions) != 1:
            return
        user_id = message.mentions[0].id
        match = re.search(r'START_MISSION_(\d+)', message.content)
        if match:
            mission_id = int(match.group(1))
            await handle_start_mission(client, user_id, mission_id)
        return

    if isinstance(message.channel, discord.channel.DMChannel):
        await handle_dm(client, message)
