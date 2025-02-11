import os
import sys
import discord
from datetime import datetime
from discord.ui import View
from discord.errors import Forbidden

from bot.views.buttons import TerminateButton
from bot.views.reply_options import SingleReplyButtonView
from bot.config import config

async def handle_record_mission(client, user_id, mission_id):
    mission = await client.api_utils.get_mission_info(mission_id)
    mission['current_step'] = 1
    user = await client.fetch_user(user_id)

    # Set Mission start
    await client.api_utils.update_student_mission_status(user_id, mission_id, current_step=mission['current_step'])
    hello_message = (
        "親愛的家長，\n"
        "讓加一🐾幫你確認一下，這兩週您是否有定期在寶寶檔案室紀錄寶寶的日常呢？\n"
        "這樣我們可以更好地為您和寶寶提供貼心的支持喔💪"
    )
    await user.send(hello_message)
    await client.api_utils.store_message(str(user_id), 'assistant', hello_message)

    # class_state = `in_class`
    mission['current_step'] += 1
    await client.api_utils.update_student_mission_status(user_id, mission_id, current_step=mission['current_step'])

    await handle_check_baby_records(client, user, mission)

async def handle_check_baby_records(client, user, student_mission_info):
    user_id = str(user.id)
    exists_baby_records = await client.api_utils.check_baby_records_in_two_weeks(user_id)
    if exists_baby_records:
        view = View(timeout=None)
        view.add_item(
            TerminateButton(client, "結束課程", "結束課程，謝謝您的使用", student_mission_info)
        )
        msg = "很棒！過去兩週已有作息紀錄，繼續保持 !"
        await user.send(msg, view=view)
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
            timeout_msg = "操作逾時，請至補上紀錄以完成任務。補上紀錄以完成任務。"
            await user.send(timeout_msg)
            await client.api_utils.store_message(user_id, 'assistant', timeout_msg)

async def send_reply_with_single_button(user, msg, label="我完成了"):
    view = SingleReplyButtonView(label)
    await user.send(msg, view=view)
    await view.wait()
    return view.selected

async def handle_record_mission_dm(client, message, student_mission_info):
    user_id = str(message.author.id)
    await client.api_utils.store_message(user_id, 'user', message.content)

    await handle_check_baby_records(client, message.author, student_mission_info)

    student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)
    if bool(student_mission_info) == False:
        msg = "加一現在不方便回答問題喔，可以找 <@1287675308388126762>"
        await message.channel.send(msg)
        await client.api_utils.store_message(str(user_id), 'assistant', msg)

