import discord
import os
import re
import schedule
import asyncio
from pathlib import Path
from collections import deque
from loguru import logger
from discord.ui import View
from discord.errors import Forbidden
from bot.views.control_panel import ControlPanelView
from bot.config import config

async def run_scheduler():
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

async def job(client):
    client.logger.debug('Running job now...')

    channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise Exception('Invalid channel')

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
            client.logger.error("Failed to send control panel to user: {user_id}, {str(e)}")

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



