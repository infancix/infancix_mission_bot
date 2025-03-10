import os
import sys
import discord
from datetime import datetime
from discord.ui import View
from discord.errors import Forbidden

from bot.views.terminate_class import TerminateClassView
from bot.views.reply_options import ReplyOptionView
from bot.config import config

async def handle_record_mission_dm(client, message, student_mission_info):
    user_id = str(message.author.id)
    student_mission_info['user_id'] = user_id
    await client.api_utils.store_message(user_id, 'user', message.content)

    await handle_check_baby_records(client, message.author, student_mission_info)

    student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)
    if bool(student_mission_info) == False:
        msg = "加一現在不方便回答問題喔，可以找 <@1287675308388126762>"
        await message.channel.send(msg)
        await client.api_utils.store_message(str(user_id), 'assistant', msg)

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
    user = await client.fetch_user(user_id)
    await user.send(hello_message)
    await client.api_utils.store_message(str(user_id), 'assistant', hello_message)

    # class_state = `in_class`
    student_mission_info['current_step'] += 1
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Next step
    await handle_check_baby_records(client, user, student_mission_info)

async def handle_check_baby_records(client, user, student_mission_info):
    user_id = str(user.id)
    exists_baby_records = await client.api_utils.check_baby_records_in_two_weeks(user_id)
    if exists_baby_records:
        # Mission Completed
        student_mission_info.update({
            'current_step': 4
        })
        await client.api_utils.update_student_mission_status(**student_mission_info)
        view = TerminateClassView(client, student_mission_info)
        msg = "很棒！過去兩週已有作息紀錄，繼續保持 !"
        view.message = await user.send(msg, view=view)
        await client.api_utils.store_message(user_id, 'assistant', msg)
        return
    else:
        msg = "過去兩週未見寶寶作息紀錄，請至<@!1165875139553021995> 補上紀錄以完成任務。"
        selected_option = await send_reply_with_single_button(user, msg, label="我完成了")
        if selected_option:
            # Recursively check again
            await handle_check_baby_records(client, user, student_mission_info)
        else:
            # Handle case where no button was clicked (e.g., timeout)
            student_mission_info['is_paused'] = True
            timeout_msg = "操作逾時，請至補上紀錄以完成任務。補上紀錄以完成任務。"
            await user.send(timeout_msg)
            await client.api_utils.store_message(user_id, 'assistant', timeout_msg)
            await client.api_utils.update_student_mission_status(**student_mission_info)

async def send_reply_with_single_button(user, msg, label="我完成了"):
    view = ReplyOptionView([label])
    view.message = await user.send(msg, view=view)
    await view.wait()
    if view.selected_option:
        return view.selected_option
    else:
        return None

