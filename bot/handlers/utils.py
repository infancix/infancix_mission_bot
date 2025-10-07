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
    load_growth_photo_records,
    load_theme_book_edit_records,
    load_questionnaire_records
)
from bot.views.task_select_view import TaskSelectView
from bot.views.growth_photo import GrowthPhotoView
from bot.views.theme_book_view import ThemeBookView
from bot.views.questionnaire import QuestionnaireView
from bot.views.confirm_growth_album_view import ConfirmGrowthAlbumView
from bot.views.quiz import QuizView

async def run_scheduler():
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

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
            await target_channel.send(f"START_MISSION_{mission_id} <@{user_id}>")
            await asyncio.sleep(2)
        except Exception as e:
            client.logger.error(f"Failed to send control panel to user: {user_id}, {str(e)}")

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

async def load_growth_photo_messages(client):
    records = load_growth_photo_records()
    for user_id in records:
        try:
            channel = await client.fetch_user(user_id)
            for mission_id, photo_status in records[user_id].items():
                message = await channel.fetch_message(int(photo_status['message_id']))
                view = GrowthPhotoView(client, user_id, int(mission_id), photo_status.get('result', {}))
                await message.edit(view=view)
            client.logger.info(f"✅ Restore growth photo for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore growth photo for {user_id}: {e}")

async def load_confirm_growth_album_records(client):
    records = load_growth_photo_records()
    for user_id in records:
        try:
            channel = await client.fetch_user(user_id)
            for mission_id, album_status in records[user_id].items():
                if album_status.get('result', {}):
                    message = await channel.fetch_message(int(album_status['message_id']))
                    view = ConfirmGrowthAlbumView(client, user_id, album_status.get('result', {}))
                    await message.edit(view=view)
            client.logger.info(f"✅ Restore confirmed growth album for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore confirmed growth album for {user_id}: {e}")

async def load_quiz_message(client):
    records = load_quiz_message_records()
    for user_id, (message_id, mission_id, current_round, correct_cnt) in records.items():
        try:
            channel = await client.fetch_user(user_id)
            student_mission_info = await client.api_utils.get_student_mission_status(user_id, int(mission_id))
            student_mission_info['user_id'] = user_id
            message = await channel.fetch_message(int(message_id))
            view = QuizView(client, int(mission_id), current_round, correct_cnt, student_mission_info)
            await message.edit(view=view)
            client.logger.info(f"✅ Restored quiz for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore quiz for {user_id}: {e}")

async def load_theme_book_edit_messages(client):
    records = load_theme_book_edit_records()
    for user_id in records:
        try:
            channel = await client.fetch_user(user_id)
            for mission_id, edit_status in records[user_id].items():
                message = await channel.fetch_message(int(edit_status['message_id']))
                result = edit_status.get('result', None)
                view = ThemeBookView(client, result)
                await message.edit(view=view)
            client.logger.info(f"✅ Restored theme book edits for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore theme book edits for {user_id}: {e}")

async def load_questionnaire_messages(client):
    records = load_questionnaire_records()
    for user_id in records:
        try:
            channel = await client.fetch_user(user_id)
            mission_id, entries = next(iter(records.get(str(user_id), {}).items()))
            student_mission_info = await client.api_utils.get_student_mission_status(user_id, int(mission_id))
            questionnaires = client.mission_questionnaire[str(mission_id)]
            entry = entries[-1]
            message = await channel.fetch_message(int(entry['message_id']))
            clicked_options = set(entry.get('clicked_options', []))
            student_mission_info['clicked_options'] = clicked_options
            view = QuestionnaireView(client, int(mission_id), len(entries)-1, student_mission_info)
            view.message = message
            await message.edit(view=view)
            client.logger.info(f"✅ Restored questionnaires for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore questionnaires for {user_id}: {e}")

def get_user_id(source: discord.Interaction | discord.Message) -> str:
    if isinstance(source, discord.Interaction):
        return str(source.user.id)
    else:
        return str(source.author.id)
