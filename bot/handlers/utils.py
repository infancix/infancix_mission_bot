import discord
import os
import re
import schedule
import asyncio
import time
from pathlib import Path
from collections import deque
from loguru import logger
from discord.ui import View
from discord.errors import Forbidden

from bot.config import config
from bot.utils.message_tracker import load_message_records, save_message_record
from bot.views.control_panel import ControlPanelView
from bot.views.optin_class import OptinClassView

async def run_scheduler():
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

async def job(client):
    client.logger.debug('Running job now...')

    channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise Exception('Invalid channel')

    # Remove message
    control_info = await client.api_utils.get_active_control_panel()
    for message in control_info:
        try:
            user_id = message['discord_id']
            user = await client.fetch_user(int(user_id))
            message_id = message['message_id']
            message = await user.fetch_message(message_id)
            await message.delete()
            client.logger.info(f"Remove out-dated control panel of user ({user_id}).")
        except Exception as e:
            client.logger.error(f"Failed to remove out-dated control panel: {str(e)}")

    student_list = await client.api_utils.get_all_students_mission_notifications()
    for user_id in student_list:
        try:
            user = await client.fetch_user(int(user_id))
            if user.dm_channel is None:
                await user.create_dm()
            couser_info = student_list[user_id]
            view = ControlPanelView(client, user_id, couser_info)
            embed = discord.Embed(
                title=f"📅 照護課表",
                description=view.embed_content,
                color=discord.Color.blue()
            )
            message = await user.send(embed=embed, view=view)
            await client.api_utils.store_message(user_id, 'assistant', view.embed_content, message_id=message.id)
            client.logger.info(f"Send hello message to user {user_id}")
            time.sleep(5)

        except Exception as e:
            client.logger.error(f"Failed to send control panel to user: {user_id}, {str(e)}")

async def load_active_control_panel(client):
    try:
        control_info = await client.api_utils.get_active_control_panel()
        student_mission_info = await client.api_utils.get_all_students_mission_notifications()
        for message in control_info:
            user_id = message['discord_id']
            user = await client.fetch_user(int(user_id))
            message_id = message['message_id']
            if student_mission_info.get(user_id):
                view = ControlPanelView(client, user_id, student_mission_info[user_id])
                embed = discord.Embed(
                    title=f"📅 照護課表",
                    description=view.embed_content,
                    color=discord.Color.blue()
                )
                message = await user.fetch_message(message_id)
                await message.edit(embed=embed, view=view)
                await client.api_utils.store_message(user_id, 'assistant', view.embed_content, message_id=message.id)
    except Exception as e:
        client.logger.error(f"Error loading active control panel: {e}")

async def load_control_panel_by_id(client, user_id, target_channel):
    try:
        ative_control_panel = await client.api_utils.get_active_control_panel()
        for message in ative_control_panel:
            if message['discord_id'] == user_id:
                message_id = message['message_id']
                message = await target_channel.fetch_message(message_id)
                break

        course_info = await client.api_utils.get_student_mission_notifications_by_id(user_id)
        view = ControlPanelView(client, user_id, course_info)
        embed = discord.Embed(
            title=f"📅 照護課表",
            description=view.embed_content,
            color=discord.Color.blue()
        )
        return message, view, embed

    except Exception as e:
        client.logger.error(f"Error loading control panel: {e}")

async def handle_greeting_job(client, user_id = None):
    hello_message = (
        "🐾 欸～新手爸媽們！我是加一，你的「寶寶照護教室」導師！\n\n"
        "照顧寶寶是不是覺得像進入新手村？\n"
        "別怕，有我罩你！💪 交給我，穩穩的！😆 \n"
        "奶瓶怎麼選？尿布怎麼換？寶寶半夜哭鬧怎麼辦？\n"
        "專屬課程手把手帶你\n"
        "讓你穩穩當當晉升帶娃高手！🍼\n\n"
        "📣 有問題？盡管問！ 課堂直接解答，別再半夜上網查到懷疑人生～📲\n"
        "新手爸媽，不用怕，你肯定行！ 加一帶你穩穩走～💪\n"
        "📌 快來看看課程重點，直接登記加入！ 🌟\n"
        "四個月大以上的寶寶也可以登記喔！"
    )

    if user_id == None:
        student_list = await client.api_utils.fetch_student_list()
    else:
        student_list = [{'discord_id': user_id}]

    # start greeting
    client.logger.info(f"Start greeting job: {len(student_list)} student")
    for user in student_list:
        files = [
            discord.File("bot/resource/mission_bot_1.png"),
            discord.File("bot/resource/mission_bot_2.png"),
            discord.File("bot/resource/mission_bot_3.png"),
            discord.File("bot/resource/mission_bot_4.png")
        ]
        user_id = user['discord_id']
        user = await client.fetch_user(user_id)
        view = OptinClassView(client, user_id)
        view.message = await user.send(hello_message, view=view, files=files)
        client.logger.info(f"Send hello message to user {user_id}")

        save_message_record(str(user_id), str(view.message.id))
        await client.api_utils.store_message(user_id, 'assistant', hello_message)

        await asyncio.sleep(10)

    return

async def load_greeting_message(client):
    records = load_message_records()
    for user_id, message_id in records.items():
        try:
            channel = await client.fetch_user(user_id)
            message = await channel.fetch_message(int(message_id))
            view = OptinClassView(client, user_id)
            await message.edit(view=view)
            client.logger.info(f"✅ Restored view for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore for {user_id}: {e}")

def convert_image_to_preview(google_drive_url):
    match = re.search(r"https://drive\.google\.com/file/d/([^/]+)/preview", google_drive_url)
    if match:
        file_id = match.group(1)
        direct_url = f"https://drive.google.com/uc?id={file_id}"
        return direct_url
    else:
        return google_drive_url



