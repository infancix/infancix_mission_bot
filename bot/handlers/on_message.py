import asyncio
import discord
import re

from bot.config import config
from bot.handlers.quiz_mission_handler import handle_quiz_mission_start, handle_class_question
from bot.handlers.photo_mission_handler import (
    handle_photo_mission_start,
    process_baby_registration_message,
    process_photo_mission_filling,
    process_add_on_photo_mission_filling
) 
from bot.handlers.pregnancy_mission_handler import (
    handle_pregnancy_mission_start,
    process_pregnancy_registration_message
)
from bot.handlers.utils import handle_greeting_job, handle_notify_photo_ready_job, handle_notify_album_ready_job

async def handle_background_message(client, message):
    client.logger.debug(f"Background message received: {message}")
    client.logger.debug(f"Message metions: {message.mentions}")

    if len(message.mentions) == 1 and message.mentions[0].id == config.MISSION_BOT and 'START_GREETING_ALL' in message.content:
        await handle_greeting_job(client)
    elif len(message.mentions) == 2 and message.mentions[0].id == config.MISSION_BOT and 'START_GREETING' in message.content:
        await handle_greeting_job(client, message.mentions[1].id)
    elif len(message.mentions) == 1:
        user_id = message.mentions[0].id
        mission_match = re.search(rf'START_MISSION_(\d+)', message.content)
        photo_match = re.search(rf'PHOTO_GENERATION_COMPLETED_(\d+)_(\d+)', message.content)
        album_match = re.search(rf'ALBUM_GENERATION_COMPLETED_(\d+)_(\d+)', message.content)
        if mission_match:
            mission_id = int(mission_match.group(1))
            await handle_start_mission(client, user_id, mission_id)
        elif photo_match:
            baby_id = int(photo_match.group(1))
            mission_id = int(photo_match.group(2))
            await handle_notify_photo_ready_job(client, user_id, baby_id, mission_id)
        elif album_match:
            baby_id = int(album_match.group(1))
            book_id = int(album_match.group(2))
            await handle_notify_album_ready_job(client, user_id, baby_id, book_id)
    return

async def handle_direct_message(client, message):
    client.logger.debug(f"Message received: {message}")
    user_id = str(message.author.id)
    student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)

    if not bool(student_mission_info):
        await client.api_utils.store_message(str(user_id), 'user', message.content)
        reply_msg = "點選 `指令` > `補上傳照片` 重新解任務喔！"
        await message.channel.send(reply_msg)
        await client.api_utils.store_message(str(user_id), 'assistant', reply_msg)
        return

    if message.stickers:
        message.content = "收到使用者的貼圖"

    # 語音訊息
    elif message.attachments and message.attachments[0].filename.endswith('ogg'):
        try:
            voice_message = await client.openai_utils.convert_audio_to_message(message)
            if not voice_message:
                client.logger.error(f"辨識語音失敗: {message}")
                await message.channel.send("辨識語音失敗，請再說一次")
                return
            else:
                message.content = voice_message['result']
        except Exception as e:
            client.logger.error(f"語音處理錯誤: {str(e)}")
            await message.channel.send("語音訊息處理時發生錯誤，請稍後再試")
            return

    # 照片
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.heic', '.heif')):
        is_valid = await client.s3_client.check_discord_attachment(message.attachments[0])
        if not is_valid:
            await message.channel.send("請上傳照片，並確保照片大小不超過 8MB，格式為 JPG、PNG、GIF、WEBP、HEIC 或 HEIF。")
            return
        message.content = "收到使用者的照片"

    # 影片
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
        await message.channel.send("請提供照片喔！")
        return
    else:
        if not message.content.strip():
            await message.channel.send(f"無法處理您上傳的檔案內容，請輸入文字訊息或確保檔案格式正確後再試一次。如需幫助，請聯絡客服。")
            return

    await client.api_utils.store_message(user_id, 'user', message.content)
    mission_id = int(student_mission_info['mission_id'])
    student_mission_info['user_id'] = user_id
    # dispatch question
    if mission_id == config.baby_register_mission:
        await process_baby_registration_message(client, message, student_mission_info)
    elif mission_id == config.pregnancy_register_mission:
        await process_pregnancy_registration_message(client, message, student_mission_info)
    elif mission_id in config.family_intro_mission:
        await process_photo_mission_filling(client, message, student_mission_info)
    elif mission_id in config.add_on_photo_mission:
        await process_add_on_photo_mission_filling(client, message, student_mission_info)
    elif mission_id in config.photo_mission_list:
        await process_photo_mission_filling(client, message, student_mission_info)
    elif mission_id < 65:
         await handle_class_question(client, message, student_mission_info)
    elif mission_id >= 102 and mission_id <= 135:
        msg = (
            "孕期如果有任何問題，可以找24小時AI育兒助手「喵喵 <@1287675308388126762>」\n"
            "或是聯絡社群客服「阿福 <@1272828469469904937>」。"
        )
        await message.channel.send(msg)
    else:
        msg = (
            "無法處理您的訊息，請確認任務是否正確\n"
            "若有育兒問題，請找24小時AI育兒助手「喵喵 <@1287675308388126762>」\n"
            "或是聯絡社群客服「阿福 <@1272828469469904937>」。"
        )
        await message.channel.send(msg)
    return

async def handle_start_mission(client, user_id, mission_id):
    mission_id = int(mission_id)
    if mission_id >= 101 and mission_id <= 135:
        await handle_pregnancy_mission_start(client, user_id, mission_id)
    elif mission_id in config.photo_mission_list:
        await handle_photo_mission_start(client, user_id, mission_id)
    elif mission_id < 100 and mission_id not in config.photo_mission_list:
        await handle_quiz_mission_start(client, user_id, mission_id)
    else:
        print(f"Unhandled mission ID: {mission_id}")
        return
