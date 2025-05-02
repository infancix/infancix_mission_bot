import asyncio
import discord
import re

from bot.config import config
from bot.handlers.record_check_mission_handler import handle_record_mission_start, handle_check_baby_records
from bot.handlers.quiz_mission_handler import handle_quiz_mission_start, handle_class_question
from bot.handlers.photo_mission_handler import handle_photo_mission_start, process_photo_mission_filling, process_photo_upload_and_summary
from bot.handlers.utils import handle_greeting_job, handle_add_photo_job

async def handle_background_message(client, message):
    client.logger.debug(f"Background message received: {message}")
    client.logger.debug(f"Message metions: {message.mentions}")

    if len(message.mentions) == 1 and message.mentions[0].id == config.MISSION_BOT and 'START_GREETING_ALL' in message.content:
        await handle_greeting_job(client)
        return
    elif len(message.mentions) == 2 and message.mentions[0].id == config.MISSION_BOT and 'START_GREETING' in message.content:
        await handle_greeting_job(client, message.mentions[1].id)
        return
    elif len(message.mentions) == 1:
        user_id = message.mentions[0].id
        mission_match = re.search(rf'START_DEV_MISSION_(\d+)', message.content)
        photo_match = re.search(rf'PHOTO_GENERATION_COMPLETED_(\d+)', message.content)
        album_match = re.search(rf'GROWTH_ALBUM_GENERATION_(\d+)', message.content)
        if mission_match:
            mission_id = int(mission_match.group(1))
            await handle_start_mission(client, user_id, mission_id)
        elif photo_match:
            mission_id = int(photo_match.group(1))
            await handle_add_photo_job(client, user_id, mission_id)
        elif album_match:
            book_id = int(album_match.group(1))
            pass
        return
    else:
        return

async def handle_direct_message(client, message):
    client.logger.debug(f"Message received: {message}")
    user_id = str(message.author.id)
    student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)

    if not bool(student_mission_info):
        client.api_utils.store_message(str(user_id), 'user', message.content)
        reply_msg = "輸入\"/任務佈告欄\" 即可透過儀表板重新解任務喔！"
        await message.channel.send(reply_msg)
        client.api_utils.store_message(str(user_id), 'assistant', reply_msg)
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
        await message.channel.send("汪～影片太重啦～ 加一沒法幫你處理喔！")
        return
    else:
        if not message.content.strip():
            await message.channel.send(f"無法處理您上傳的檔案內容，請輸入文字訊息或確保檔案格式正確後再試一次。如需幫助，請聯絡客服。")
            return

    await client.api_utils.store_message(user_id, 'user', message.content)
    mission_id = int(student_mission_info['mission_id'])
    student_mission_info['user_id'] = user_id
    # dispatch question
    if mission_id in config.record_mission_list:
        await handle_check_baby_records(client, message, student_mission_info)
    elif mission_id in config.photo_mission_list:
        await process_photo_upload_and_summary(client, message, student_mission_info)
    elif (mission_id in config.photo_mission_with_aside_text
          or mission_id in config.photo_mission_with_title_and_content
          or mission_id in config.baby_intro_mission):
        await process_photo_mission_filling(client, message, student_mission_info)
    else:
         await handle_class_question(client, message, student_mission_info)

async def handle_start_mission(client, user_id, mission_id):
    mission_id = int(mission_id)
    if mission_id in config.record_mission_list:
        await handle_record_mission_start(client, user_id, mission_id)
    elif mission_id < 100 and mission_id not in config.photo_mission_with_aside_text:
        await handle_quiz_mission_start(client, user_id, mission_id)
    else:
        await handle_photo_mission_start(client, user_id, mission_id)
