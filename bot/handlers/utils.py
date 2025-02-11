import discord
import os
import re
from pathlib import Path
from datetime import datetime
from loguru import logger
from discord.ui import View
from discord.errors import Forbidden
from types import SimpleNamespace
from bot.views.buttons import TerminateButton
from bot.views.quiz import QuizView
from bot.views.reply_options import ReplyOptionView
from bot.config import config

async def job(client):
    client.logger.debug('Running job now...')

    channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise Exception('Invalid channel')

    data = await client.api_utils.get_student_mission_notification_list()
    tasks_to_be_pushed = data.get('notification_list', [])
    tasks_to_be_notified = data.get('incomplete_mission_reminder_list', [])

    # Push tasks to students
    for mission in tasks_to_be_pushed:
        discord_id = mission['discord_id']
        mission_id = mission['mission_id']

        # Start task
        await channel.send(f'START_MISSION_{mission_id} <@{discord_id}>')

    # Notify the user if they haven't completed the previous task
    for mission in tasks_to_be_notified:
        discord_id = mission['discord_id']
        last_mission_title = task['mission_title']
        notify_msg = (
            "嗨，您好嗎？我知道您忙著照顧寶寶，任務還沒結束喔，若您有空上課時，請呼叫加一，我會隨時在這裡為您服務。"
        )
        user = await client.fetch_user(discord_id)
        await user.send(notify_msg)

def image_check(m):
    # Ensure the message is in the same DM and has an attachment
    return (
        m.author == message.author
        and m.channel == message.channel
        and m.attachments
        and any(m.attachments[0].filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif'])
    )

def convert_image_to_preview(google_drive_url):
    match = re.search(r"https://drive\.google\.com/file/d/([^/]+)/preview", google_drive_url)
    if match:
        file_id = match.group(1)
        direct_url = f"https://drive.google.com/uc?id={file_id}"
        return direct_url
    else:
        return google_drive_url

async def send_assistant_reply(client, message, student_mission_info, content):
    """
    Sends a reply from the assistant and stores the response.
    """
    client.logger.info("send_assistant_reply")
    thread_id = student_mission_info['thread_id']
    assistant_id = student_mission_info['assistant_id']
    class_state = student_mission_info.get('class_state', '階段未定義')
    client.logger.info(f"(Mission-{student_mission_info['mission_id']}/User-{message.author.id}): [{class_state}] {content}")
    try:
        async with message.channel.typing():
            response = await client.openai_utils.get_reply_message(assistant_id, thread_id, content)

        if 'class_state' in response:
            student_mission_info['class_state'] = response['class_state']

        if 'message' in response:
            await message.channel.send(response['message'])
            await client.api_utils.store_message(str(message.author.id), 'assistant', response['message'])
        else:
            await message.channel.send("加一不太懂，可以再試一次嗎？")

    except Exception as e:
        client.logger.error(f"Failed to get assistant reply: {str(e)}")
        await message.channel.send("加一不太懂，可以再試一次嗎？或是管理員協助處理。")

async def send_assistant_reply_with_button(client, message, student_mission_info, content, reply_options=['下一步', '不太懂欸？']):
    """
    Sends a reply from the assistant with interactive buttons and stores the response.
    """
    thread_id = student_mission_info['thread_id']
    assistant_id = student_mission_info['assistant_id']
    class_state = student_mission_info.get('class_state', '階段未定義')
    client.logger.info(f"(Mission-{student_mission_info['mission_id']}/User-{message.author.id}): [{class_state}] {content}")
    try:
        async with message.channel.typing():
            response = await client.openai_utils.get_reply_message(assistant_id, thread_id, content)
            client.logger.info(f"Assitant response: {response}")

        if 'reply_options' in response and len(response['reply_options']) > 0:
            reply_options = response['reply_options']

        if 'class_state' in response:
            student_mission_info['class_state'] = response['class_state']
            if response['class_state'] == 'quiz':
                reply_options = ['進入小測驗']

        if 'message' in response:
            view = ReplyOptionView(reply_options)
            await message.channel.send(response['message'], view=view)
            await client.api_utils.store_message(str(message.author.id), 'assistant', response['message'])

            # Wait for user interaction
            await view.wait()

            # Handle user selection
            if view.selected_option is not None:
                selected_option = reply_options[view.selected_option]
                return selected_option
            else:
                client.logger.info(f"User did not select any option: {message.author.id}")

        else:
            await message.channel.send("加一不太懂，可以再試一次嗎？或是管理員協助處理。")

    except Exception as e:
        client.logger.error(f"Failed to get assistant reply with button: {str(e)}")
        await message.channel.send("加一不太懂，可以再試一次嗎？或是管理員協助處理。")


