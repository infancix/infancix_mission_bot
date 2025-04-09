import re
import discord
import asyncio
from discord.ui import View

from bot.config import config
from bot.handlers.record_mission_handler import handle_record_mission_start, handle_record_mission_dm
from bot.handlers.video_mission_handler import handle_video_mission_start, handle_video_mission_dm
from bot.handlers.utils import handle_greeting_job

async def handle_dm(client, message):
    if (
        message.author == client.user
        and message.channel.id != config.BACKGROUND_LOG_CHANNEL_ID
    ):
        return

    if message.channel.id == config.BACKGROUND_LOG_CHANNEL_ID:
        if len(message.mentions) == 1 and message.mentions[0].id == config.MISSION_BOT and 'START_GREETING_ALL' in message.content:
            await handle_greeting_job(client)
            return
        elif len(message.mentions) == 2 and message.mentions[0].id == config.MISSION_BOT and 'START_GREETING' in message.content:
            await handle_greeting_job(client, message.mentions[1].id)
            return
        elif len(message.mentions) == 1:
            user_id = message.mentions[0].id
            match = re.search(r'START_MISSION_(\d+)', message.content)
            if match:
                mission_id = int(match.group(1))
                await handle_start_mission(client, user_id, mission_id)
            return
        else:
            return

    if isinstance(message.channel, discord.channel.DMChannel):
        user_id = str(message.author.id)
        student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)
        if not bool(student_mission_info):
            client.api_utils.store_message(str(user_id), 'user', message.content)
            reply_msg = "加一現在不在喔，有問題可以找 <@1287675308388126762>"
            await message.channel.send(reply_msg)
            client.api_utils.store_message(str(user_id), 'assistant', reply_msg)
        else:
            student_mission_info['mission_id'] = int(student_mission_info['mission_id'])
            if student_mission_info['mission_id'] in config.record_mission_list:
                await handle_record_mission_dm(client, message, student_mission_info)
            else:
                await handle_video_mission_dm(client, message, student_mission_info)
        return

async def handle_start_mission(client, user_id, mission_id):
    mission_id = int(mission_id)
    if mission_id in config.record_mission_list:
        await handle_record_mission_start(client, user_id, mission_id)
    else:
        await handle_video_mission_start(client, user_id, mission_id)


