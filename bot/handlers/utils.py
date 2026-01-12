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
    load_task_entry_records,
    load_growth_photo_records,
    load_theme_book_edit_records,
    load_questionnaire_records,
    load_confirm_growth_albums_records,
    delete_task_entry_record,
    delete_growth_photo_record,
    delete_questionnaire_record
)
from bot.views.task_select_view import TaskSelectView
from bot.views.growth_photo import GrowthPhotoView
from bot.views.theme_book_view import EditThemeBookView
from bot.views.questionnaire import QuestionnaireView
from bot.views.confirm_growth_album_view import ConfirmGrowthAlbumView

async def run_scheduler():
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

async def daily_job(client):
    if config.ENV:
        return

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

async def monthly_print_reminder_job(client):
    if config.ENV:
        return

    today = date.today()
    # check if today is the 1st of the month
    if today.day != 1 and today.day != 15:
        return

    client.logger.debug('Running monthly print reminder job now...')
    target_channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if target_channel is None or not isinstance(target_channel, discord.TextChannel):
        raise Exception('Invalid channel')

    reminder_list = await client.api_utils.get_purchase_students_reminder_list()
    for reminder in reminder_list:
        try:
            user_id = reminder['discord_id']
            await target_channel.send(f"MONTHLY_PRINT_REMINDER <@{user_id}>")
            await asyncio.sleep(10)
        except Exception as e:
            client.logger.error(f"Failed to send monthly print reminder to user: {user_id}, {str(e)}")

def reset_user_state(client, user_id, mission_id=0):
    # Delete the message records
    delete_task_entry_record(user_id, str(mission_id))
    delete_questionnaire_record(user_id, str(mission_id))
    delete_growth_photo_record(user_id, str(mission_id))
    if user_id in client.photo_mission_replace_index:
        del client.photo_mission_replace_index[user_id]
    if user_id in client.reset_baby_profile:
        del client.reset_baby_profile[user_id]
    if user_id in client.skip_aside_text:
        del client.skip_aside_text[user_id]
    if user_id in client.skip_growth_info:
        del client.skip_growth_info[user_id]

async def load_task_entry_messages(client):
    records = load_task_entry_records()
    for user_id in records:
        try:
            channel = await client.fetch_user(user_id)
            for mission_id, task_status in records[user_id].items():
                message = await channel.fetch_message(int(task_status['message_id']))
                result = task_status.get('result', {})
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

async def load_confirm_growth_album_messages(client):
    records = load_confirm_growth_albums_records()
    for user_id in records:
        try:
            channel = await client.fetch_user(user_id)
            message_id = records[user_id]['message_id']
            albums_info = records[user_id].get('albums_info', {})
            incomplete_missions = records[user_id].get('incomplete_missions', [])
            message = await channel.fetch_message(int(message_id))
            view = ConfirmGrowthAlbumView(client, user_id, albums_info, incomplete_missions)
            embed = view.preview_embed()
            await message.edit(embed=embed, view=view)
            client.logger.info(f"✅ Restore confirmed growth album for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore confirmed growth album for {user_id}: {e}")

async def load_theme_book_edit_messages(client):
    records = load_theme_book_edit_records()
    for user_id in records:
        try:
            channel = await client.fetch_user(user_id)
            for book_id, edit_status in records[user_id].items():
                message = await channel.fetch_message(int(edit_status['message_id']))
                result = edit_status.get('result', None)
                view = EditThemeBookView(client, result)
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

async def start_mission_by_id(client, user_id: str, mission_id: int, send_weekly_report: int = 1):
    """
    Route and start a mission based on its ID.

    Args:
        client: The Discord client
        user_id: User ID as string
        mission_id: Mission ID to start
        send_weekly_report: Whether to send weekly report (default: 1)
    """
    if mission_id in config.theme_mission_list:
        from bot.handlers.theme_mission_handler import handle_theme_mission_start
        await handle_theme_mission_start(client, user_id, mission_id)
    elif mission_id in config.audio_mission:
        from bot.handlers.audio_mission_handler import handle_audio_mission_start
        await handle_audio_mission_start(client, user_id, mission_id)
    elif mission_id in config.video_mission:
        from bot.handlers.video_mission_handler import handle_video_mission_start
        await handle_video_mission_start(client, user_id, mission_id)
    elif mission_id in config.questionnaire_mission:
        from bot.handlers.questionnaire_mission_handler import handle_questionnaire_mission_start
        await handle_questionnaire_mission_start(client, user_id, mission_id)
    elif mission_id in config.baby_profile_registration_missions:
        from bot.handlers.profile_handler import handle_registration_mission_start
        await handle_registration_mission_start(client, user_id, mission_id)
    elif mission_id in config.relation_or_identity_mission:
        from bot.handlers.relation_or_identity_handler import handle_relation_identity_mission_start
        await handle_relation_identity_mission_start(client, user_id, mission_id)
    elif mission_id in config.add_on_photo_mission:
        from bot.handlers.add_on_mission_handler import handle_add_on_mission_start
        await handle_add_on_mission_start(client, user_id, mission_id)
    else:
        # Default to photo mission
        from bot.handlers.photo_mission_handler import handle_photo_mission_start
        await handle_photo_mission_start(client, user_id, mission_id, send_weekly_report=send_weekly_report)
