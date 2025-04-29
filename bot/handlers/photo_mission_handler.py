import traceback
import discord
import os
import re
from types import SimpleNamespace
from datetime import datetime

from bot.views.task_select_view import TaskSelectView
from bot.handlers.utils import get_user_id, send_reward_and_log
from bot.utils.message_tracker import save_task_entry_record
from bot.utils.decorator import exception_handler
from bot.views.growth_photo import GrowthPhotoView
from bot.config import config

async def handle_photo_mission_start(client, message, mission_id):
    user_id = get_user_id(message)
    mission = await client.api_utils.get_mission_info(mission_id)
    mission_status = await client.api_utils.get_student_mission_status(user_id, mission_id)

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'assistant_id': config.get_assistant_id(mission_id),
        'thread_id': mission_status.get('thread_id', client.openai_utils.load_thread()),
        'current_step': 1
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    embed = discord.Embed(
        title=mission['mission_title'],
        color=discord.Color.blue()
    )

    task_instructions = ""
    if mission['notification_content'].strip():
        task_instructions += mission['notification_content'].strip() + "\n\n"
    if mission['mission_video_contents'].strip():
        task_instructions += f"🎥 影片教學\n▶️ [{mission['mission_title']}]({mission['mission_video_contents']})\n\n"
    if mission['mission_image_contents'] and mission['mission_image_contents'].strip():
        if mission_id > 100:
            embed.set_image(url=mission['mission_image_contents'].strip())
        else:
            task_instructions += f"📖 圖文懶人包\n ▶️"
            for url in mission['mission_image_contents'].strip().split(','):
                task_instructions += f" [點擊]({url})"
    
    if task_instructions:
        embed.description = task_instructions

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()
    view = TaskSelectView(client, "go_photo", mission_id)
    view.message = await user.send(embed=embed, view=view)
    save_task_entry_record(user_id, str(view.message.id), "go_photo", mission_id)

async def send_photo_mission_instruction(client, message, student_mission_info):
    user_id = get_user_id(message)

    photo_task_request = (
        f"📸 請上傳「**{student_mission_info['photo_mission']}**」的照片！\n\n"
        f"🧩 這張回憶將化作【回憶碎片】，拼入寶寶的成長相冊 📖  \n"
    )

    embed = discord.Embed(
        title=student_mission_info['mission_title'],
        description=photo_task_request,
        color=discord.Color.orange()
    )
    message = await message.channel.send(embed=embed)
    await client.api_utils.store_message(user_id, 'assistant', photo_task_request)

    student_mission_info['current_step'] = 2
    await client.api_utils.update_student_mission_status(**student_mission_info)

    return

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試一次喔！")
async def process_photo_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    photo_url = await client.s3_client.process_discord_attachment(message.attachments[0].url)

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = student_mission_info['assistant_id']
        thread_id = student_mission_info['thread_id']
        bot_response = client.openai_utils.get_reply_message(assistant_id, thread_id, message.content)
        
    if bot_response.get('is_ready'):
        content = bot_response.get('content') or bot_response.get('aside_text')
        view = GrowthPhotoView(client, user_id, bot_response)
        embed = discord.Embed(
            title=bot_response['photo_mission'],
            description=content,
        )
        embed.set_image(url=bot_response['image'])
        message = await message.channel.send(content=bot_response['message'], embed=embed, view=view)
    else:
        await message.channel.send(bot_response['message'])

    return

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試一次喔！")
async def process_photo_upload_and_summary(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    photo_url = await client.s3_client.process_discord_attachment(message.attachments[0].url)

    await client.api_utils.upload_baby_image(user_id, mission_id, student_mission_info['mission_title'], photo_url)
    await client.api_utils.store_message(user_id, 'user', f"收到任務照片: {photo_url}")

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = student_mission_info['assistant_id']
        thread_id = student_mission_info['thread_id']
        bot_response = client.openai_utils.get_reply_message(assistant_id, thread_id, message.content)

    await message.channel.send(bot_response['message'])
    await client.api_utils.store_message(user_id, assistant_id, bot_response['message'])
    client.logger.info(f"Assitant response: {bot_response}")

    # Mission Completed
    student_mission_info['current_step'] = 4
    student_mission_info['score'] = 1
    await client.api_utils.update_student_mission_status(**student_mission_info)
    await send_reward_and_log(client, user_id, mission_id, 100)
