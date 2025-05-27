import traceback
import discord
import os
import re
from types import SimpleNamespace
from datetime import datetime

from bot.views.task_select_view import TaskSelectView
from bot.handlers.utils import get_user_id, send_reward_and_log, convert_image_to_preview
from bot.utils.message_tracker import save_task_entry_record, save_photo_view_record
from bot.utils.decorator import exception_handler
from bot.views.growth_photo import GrowthPhotoView
from bot.config import config

async def handle_photo_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    mission_status = await client.api_utils.get_student_mission_status(user_id, mission_id)

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'assistant_id': config.get_assistant_id(mission_id),
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
            embed.set_image(url=convert_image_to_preview(mission['mission_image_contents']))
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
    if message.attachments:
        photo_url = await client.s3_client.process_discord_attachment(message.attachments[0].url)
        user_message = f"[mission_id: {mission_id}]: 收到使用者的照片: {photo_url}"
    else:
        user_message = message.content

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = client.openai_utils.load_thread()
            student_mission_info['thread_id'] = thread_id
            await client.api_utils.update_student_mission_status(**student_mission_info)
            # Add task instructions to the assistant's thread
            task_request = (
                f"這是這次的任務說明：\n"
                f"- mission_id: {mission_id}\n"
                f"- 照片任務: {student_mission_info['photo_mission']}\n"
            )
            default_content = await client.api_utils.get_mission_default_content_by_id(user_id, mission_id)
            if default_content:
                task_request += f"草稿：\n{default_content}"
            if mission_id in config.baby_intro_mission:
                get_baby_additional_info = await client.api_utils.get_baby_additional_info(user_id)
                task_request += get_baby_additional_info
            client.openai_utils.add_task_instruction(thread_id, task_request)

        # add user message
        bot_response = client.openai_utils.get_reply_message(assistant_id, thread_id, user_message)
        
    if bot_response.get('is_ready'):
        # Handle mission status update
        student_mission_info['mission_id'] = mission_id
        baby_data = {}
        if int(mission_id) in config.baby_intro_mission:
            baby_data.update({
                'baby_name': bot_response.get('baby_name'),
                'gender': bot_response.get('gender'),
                'birthday': bot_response.get('birthday'),
                'height': bot_response.get('height'),
                'weight': bot_response.get('weight'),
                'head_circumference': bot_response.get('head_circumference'),
            })

        if baby_data:
            await client.api_utils.update_student_baby_profile(user_id, **baby_data)

        content = bot_response.get('content') or bot_response.get('aside_text')
        if bot_response.get('image') and content:
            photo_url = await client.s3_client.process_discord_attachment(bot_response.get('image'))
            update_status = await client.api_utils.update_mission_image_content(
                user_id, mission_id, image_url=photo_url, aside_text=bot_response.get('aside_text'), content=bot_response.get('content')
            )

            if bool(update_status):
                await client.api_utils.submit_generate_photo_request(user_id, mission_id)
                msg = "製作繪本內頁預覽會需要一點時間喔，請耐心等候一下！\nhttps://tenor.com/view/hammy-ham-gif-9441822720620805227"
                await message.channel.send(msg)
                await client.api_utils.store_message(user_id, 'assistant', msg)

    else:
        await message.channel.send(bot_response['message'])

    return

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試一次喔！")
async def process_photo_upload_and_summary(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    photo_url = await client.s3_client.process_discord_attachment(message.attachments[0].url)
    user_message = f"[mission_id: {mission_id}]: 收到使用者的照片: {photo_url}"

    await client.api_utils.upload_baby_image(user_id, mission_id, student_mission_info['mission_title'], photo_url)
    await client.api_utils.store_message(user_id, 'user', f"收到任務照片: {photo_url}")

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = client.openai_utils.load_thread()
            student_mission_info['thread_id'] = thread_id
            await client.api_utils.update_student_mission_status(**student_mission_info)
        bot_response = client.openai_utils.get_reply_message(assistant_id, thread_id, user_message)

    await message.channel.send(bot_response['message'])
    await client.api_utils.store_message(user_id, assistant_id, bot_response['message'])
    client.logger.info(f"Assitant response: {bot_response}")

    # Mission Completed
    student_mission_info['current_step'] = 4
    student_mission_info['score'] = 1
    await client.api_utils.update_student_mission_status(**student_mission_info)
    await send_reward_and_log(client, user_id, mission_id, 100)
