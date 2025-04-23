import asyncio
import discord
import re

from bot.config import config
from bot.handlers.record_mission_handler import handle_record_mission_start, handle_check_baby_records
from bot.handlers.video_mission_handler import handle_video_mission_start, handle_video_mission_dm
from bot.handlers.utils import handle_greeting_job

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
        match = re.search(r'START_MISSION_(\d+)', message.content)
        if match:
            mission_id = int(match.group(1))
            await handle_start_mission(client, user_id, mission_id)
        return
    else:
        return

async def handle_direct_message(client, message):
    client.logger.info(f"Message received: {message}")
    user_id = str(message.author.id)
    student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)

    if not bool(student_mission_info):
        client.api_utils.store_message(str(user_id), 'user', message.content)
        reply_msg = "請透過儀表板選擇任務喔！"
        await message.channel.send(reply_msg)
        client.api_utils.store_message(str(user_id), 'assistant', reply_msg)
        return

    if message.stickers:
        message.content = "收到使用者的貼圖"
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
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.heic', '.heif')):
        is_valid = await client.s3_client.check_discord_attachment(message.attachments[0])
        if is_valid:
            photo_url = message.attachments[0].url
            message.content = f"收到使用者的照片: {photo_url}"
        else:
            await message.channel.send("請上傳照片，並確保照片大小不超過 8MB，格式為 JPG、PNG、GIF、WEBP、HEIC 或 HEIF。")
            return
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
        await message.channel.send("汪～影片太重啦～ 加一沒法幫你處理喔！")
        return

    if not message.content.strip():
        await message.channel.send(f"無法處理您上傳的檔案內容，請輸入文字訊息或確保檔案格式正確後再試一次。如需幫助，請聯絡客服。")
        return

    await client.api_utils.store_message(user_id, 'user', message.content)
    student_mission_info['mission_id'] = int(student_mission_info['mission_id'])
    if student_mission_info['mission_id'] in config.record_mission_list:
        await handle_check_baby_records(client, message, student_mission_info)
    else:
        await handle_video_mission_dm(client, message, student_mission_info)

    return

async def handle_start_mission(client, user_id, mission_id):
    mission_id = int(mission_id)
    if mission_id in config.record_mission_list:
        await handle_record_mission_start(client, user_id, mission_id)
    else:
        await handle_video_mission_start(client, user_id, mission_id)
