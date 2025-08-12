import re
import discord
import schedule
import asyncio
from datetime import datetime, date
import functools
import traceback
from discord.ui import View, Button

from bot.config import config
from bot.utils.message_tracker import (
    load_quiz_message_records,
    load_task_entry_records
)
from bot.views.task_select_view import TaskSelectView
from bot.views.growth_photo import GrowthPhotoView
from bot.views.quiz import QuizView
from bot.views.album_select_view import AlbumView

async def run_scheduler():
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

def scheduled_job(client):
    today = datetime.datetime.now()

    # Daily job
    asyncio.create_task(daily_job(client))

async def daily_job(client):
    client.logger.debug('Running job now...')

    target_channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if target_channel is None or not isinstance(target_channel, discord.TextChannel):
        raise Exception('Invalid channel')

    student_list = await client.api_utils.get_all_students_mission_notifications()
    for mission in student_list:
        try:
            user_id = mission['discord_id']
            mission_id = mission['mission_id']
            await target_channel.send(f"START_DEV_MISSION_{mission_id} <@{user_id}>")
            await asyncio.sleep(2)
        except Exception as e:
            client.logger.error(f"Failed to send control panel to user: {user_id}, {str(e)}")

async def handle_greeting_job(client, user_id = None):
    embed = discord.Embed(
        title="歡迎來到繪本工坊",
        color=0xeeb2da,
    )

    embed.set_footer(
        url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )

    if user_id == None:
        student_list = await client.api_utils.fetch_student_list()
    else:
        student_list = [{'discord_id': user_id}]

    # start greeting
    client.logger.info(f"Start greeting job: {len(student_list)} student")
    for user in student_list:
        user_id = user['discord_id']
        user = await client.fetch_user(user_id)
        await user.send(hello_message, embed=embed)
        client.logger.info(f"Send hello message to user {user_id}")
        await asyncio.sleep(3)

    return

async def load_task_entry_messages(client):
    records = load_task_entry_records()
    for user_id in records:
        try:
            channel = await client.fetch_user(user_id)
            for mission_id, task_status in records[user_id].items():
                message = await channel.fetch_message(int(task_status['message_id']))
                result = task_status.get('result', None)
                view = TaskSelectView(client, task_status['task_type'], int(mission_id), result)
                await message.edit(view=view)
            client.logger.info(f"✅ Restore task-entry for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore task entry for {user_id}: {e}")

async def load_quiz_message(client):
    records = load_quiz_message_records()
    for user_id, (message_id, mission_id, current_round, correct_cnt) in records.items():
        try:
            channel = await client.fetch_user(user_id)
            student_mission_info = await client.api_utils.get_student_mission_status(user_id, mission_id)
            student_mission_info['user_id'] = user_id
            message = await channel.fetch_message(int(message_id))
            view = QuizView(client, mission_id, current_round, correct_cnt, student_mission_info)
            await message.edit(view=view)
            client.logger.info(f"✅ Restored quiz for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore quiz for {user_id}: {e}")

async def handle_notify_photo_ready_job(client, user_id, baby_id, mission_id):
    try:
        # Send the photo message to the user    
        user = await client.fetch_user(user_id)
        view = GrowthPhotoView(client, user_id, mission_id)
        embed = view.generate_embed(baby_id, mission_id)
        message = await user.send(embed=embed, view=view)
        # Log the successful message send
        client.logger.info(f"Send photo message to user {user_id}, mission {mission_id}")
    except Exception as e:
        client.logger.error(f"Failed to send photo message to user {user_id}: {e}")

    return

async def handle_notify_album_ready_job(client, user_id, baby_id, book_id):
    album = await client.api_utils.get_student_album_purchase_status(user_id, book_id)
    if album is None:
        client.logger.error(f"Album not found for user {user_id}, book {book_id}")
        return

    albums = [{
        'baby_id': baby_id,
        'book_id': book_id,
        **album
    }]
    view = AlbumView(client, albums)
    embed = view.get_current_embed()

    incomplete_missions = await client.api_utils.get_student_incomplete_photo_mission(user_id, book_id)
    if len(incomplete_missions) > 0:
        embed.description += "\n\n你已完成第一步，太棒了！🌟\n繼續努力，完成所有任務就能收集一整本屬於你們的成長繪本📘"
    else:
        embed.description += (
            "\n\n📦 Baby120 寄件說明\n"
            "書籍每 90 天統一寄送一次，未完成的任務將自動順延。\n"
            "收檔後 15 個工作天內出貨。\n"
            "所有寄送進度、任務狀態請以官網「會員中心 → 我的書櫃」公告為主。"
        )

    try:
        # Send the album preview to the user
        user = await client.fetch_user(user_id)
        await user.send(embed=embed)

        # Log the successful message send
        client.logger.info(f"Send album message to user {user_id}, book {book_id}")

    except Exception as e:
        client.logger.error(f"Failed to send album message to user {user_id}: {e}")

    return

def get_user_id(source: discord.Interaction | discord.Message) -> str:
    if isinstance(source, discord.Interaction):
        return str(source.user.id)
    else:
        return str(source.author.id)
