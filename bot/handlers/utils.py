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
    load_task_entry_records,
    load_photo_view_records,
    save_photo_view_record,
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
    for user_id in student_list:
        try:
            couser_info = student_list[user_id].get('todays_course', {})
            if couser_info and couser_info['mission_status'] != 'Completed':
                mission_id = couser_info['mission_id']
                await target_channel.send(f"START_MISSION_{mission_id} <@{user_id}>")
            await asyncio.sleep(2)
        except Exception as e:
            client.logger.error(f"Failed to send control panel to user: {user_id}, {str(e)}")

async def handle_greeting_job(client, user_id = None):
    hello_message = (
        "哈囉～新手爸媽們！歡迎來到繪本工坊\n"
        "我會自動發送照片任務給你\n"
        "請參考以下說明來完成任務喔！\n\n"
    )
    embed = discord.Embed(
        title="操作說明",
        description="說明圖片",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="📝 指令說明",
        value="❔輸入「 / 」 __補上傳照片__、__查看育兒里程碑__、__瀏覽繪本進度__",
        inline=False
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

async def load_photo_view_messages(client):
    records = load_photo_view_records()
    for user_id, record in records.items():
        try:
            message_id, mission_id = record
            channel = await client.fetch_user(user_id)
            message = await channel.fetch_message(int(message_id))
            view = GrowthPhotoView(client, user_id, mission_id)
            await message.edit(view=view)
            client.logger.info(f"✅ Restored photo view for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore photo view for {user_id}: {e}")

async def handle_notify_photo_ready_job(client, user_id, baby_id, mission_id):
    view = GrowthPhotoView(client, user_id, mission_id)
    embed = view.generate_embed(baby_id, mission_id)

    try:
        # Send the photo message to the user    
        user = await client.fetch_user(user_id)
        message = await user.send(embed=embed, view=view)

        # Save the message ID and mission ID for tracking
        save_photo_view_record(user_id, str(message.id), mission_id)

        # Log the successful message send
        client.logger.info(f"Send photo message to user {user_id}")

    except Exception as e:
        client.logger.error(f"Failed to send photo message to user {user_id}: {e}")

    return

async def handle_notify_album_ready_job(client, user_id, baby_id, book_id):
    album = await client.api_utils.get_student_album_purchase_status(user_id, book_id)
    albums = [{
        'baby_id': baby_id,
        'book_id': book_id,
        **album
    }]
    view = AlbumView(client, albums)
    embed = view.get_current_embed()
    embed.description += "\n\n繪本將於 10 個工作天寄出，請耐心等待！\n如果需要修改繪本內容，請聯絡客服(將酌收工本費200)。"
    try:
        # Send the album preview to the user
        user = await client.fetch_user(user_id)
        await user.send(embed=embed)

        # Log the successful message send
        client.logger.info(f"Send album message to user {user_id}")

    except Exception as e:
        client.logger.error(f"Failed to send album message to user {user_id}: {e}")

    return

def get_user_id(source: discord.Interaction | discord.Message) -> str:
    if isinstance(source, discord.Interaction):
        return str(source.user.id)
    else:
        return str(source.author.id)
