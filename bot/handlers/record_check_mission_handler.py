import os
import sys
import discord
from datetime import datetime
from discord.ui import View
from discord.errors import Forbidden
from types import SimpleNamespace

from bot.config import config
from bot.handlers.utils import send_reward_and_log

async def handle_record_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': 1
    }

    # Mission start
    await client.api_utils.update_student_mission_status(**student_mission_info)

    hello_message = (
        "親愛的家長，\n"
        "讓加一🐾幫你確認一下，這兩週您是否有定期在寶寶檔案室紀錄寶寶的日常呢？\n"
        "這樣我們可以更好地為您和寶寶提供貼心的支持喔💪"
    )
    embed = discord.Embed(
        title="確實紀錄寶寶數據",
        description=hello_message,
        color=discord.Color.blue()
    )
    user = await client.fetch_user(user_id)
    await user.send(embed=embed)
    await client.api_utils.store_message(str(user_id), 'assistant', hello_message)

    # class_state = `in_class`
    student_mission_info['current_step'] += 1
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Next step
    message = SimpleNamespace(author=user, channel=user.dm_channel, content=None)
    await handle_check_baby_records(client, message, student_mission_info)

async def handle_check_baby_records(client, message, student_mission_info):
    user_id = str(message.author.id)
    exists_baby_records = await client.api_utils.check_baby_records_in_two_weeks(user_id)
    if exists_baby_records:
        # Mission Completed
        student_mission_info.update({
            'current_step': 4,
            'score': 1
        })
        await client.api_utils.update_student_mission_status(**student_mission_info)
        ending_msg = f"很棒！過去兩週已有作息紀錄，繼續保持 !"
        await message.channel.send(ending_msg)
        await client.api_utils.store_message(user_id, 'assistant', ending_msg)

        # Send reward
        await send_reward_and_log(client, user_id, student_mission_info['mission_id'], 20)
        return

    else:
        msg = "過去兩週未見寶寶作息紀錄，請至<@!1165875139553021995> 補上紀錄以完成任務。"
        await message.channel.send(msg)
        return
