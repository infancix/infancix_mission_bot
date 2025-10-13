import asyncio
import discord
import os
import re
import time

from bot.config import config
from bot.handlers.quiz_mission_handler import handle_quiz_mission_start
from bot.handlers.questionnaire_mission_handler import handle_questionnaire_mission_start
from bot.handlers.photo_mission_handler import (
    handle_photo_mission_start,
    handle_baby_optin,
    process_baby_registration_message,
    process_photo_mission_filling,
    process_add_on_photo_mission_filling
) 
from bot.handlers.pregnancy_mission_handler import (
    handle_pregnancy_mission_start,
    process_pregnancy_registration_message
)
from bot.handlers.audio_mission_handler import (
    handle_audio_mission_start,
    process_audio_mission_filling
)
from bot.handlers.theme_mission_handler import (
    handle_theme_mission_start,
    process_theme_mission_filling
)
from bot.views.growth_photo import GrowthPhotoView
from bot.views.album_select_view import AlbumView
from bot.views.theme_book_view import ThemeBookView
from bot.views.task_select_view import TaskSelectView
from bot.views.confirm_growth_album_view import ConfirmGrowthAlbumView
from bot.utils.message_tracker import (
    delete_task_entry_record,
    save_growth_photo_records,
    load_theme_book_edit_records,
    save_theme_book_edit_record,
    save_confirm_growth_album_record
)

async def handle_background_message(client, message):
    client.logger.debug(f"Background message received: {message}")
    client.logger.debug(f"Message mentions: {message.mentions}")

    if len(message.mentions) == 1:
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
            if mission_id == config.baby_pre_registration_mission:
                await handle_first_photo_book(client, user_id, baby_id, book_id=1)
            elif mission_id < 7000:
                await handle_notify_photo_ready_job(client, user_id, baby_id, mission_id)
            else:
                await handle_notify_theme_book_change_page(client, user_id, baby_id)
        elif album_match:
            baby_id = int(album_match.group(1))
            book_id = int(album_match.group(2))
            if book_id in config.theme_book_map:
                await handle_notify_theme_book_ready_job(client, user_id, baby_id, book_id)
            else:
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

    # 錄音檔
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.mp3', '.wav', '.m4a', '.flac', '.aac', '.wma')):
        message.content = "收到使用者的錄音檔"

    # 照片
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.heic', '.heif')):
        for e, attachment in enumerate(message.attachments):
            file_ext = os.path.splitext(attachment.filename)[1].lower()
            is_valid = file_ext in config.IMAGE_ALLOWED_EXTENSIONS
            if not is_valid:
                if len(message.attachments) > 1:
                    await message.channel.send("第 {} 張照片格式不正確".format(e + 1))
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
    if mission_id == config.baby_pre_registration_mission:
        await handle_baby_optin(client, message, student_mission_info)
    elif mission_id == config.baby_registration_mission:
        await process_baby_registration_message(client, message, student_mission_info)
    elif mission_id == config.pregnant_registration_mission:
        await process_pregnancy_registration_message(client, message, student_mission_info)
    elif mission_id in config.family_intro_mission:
        await process_photo_mission_filling(client, message, student_mission_info)
    elif mission_id in config.audio_mission:
        await process_audio_mission_filling(client, message, student_mission_info)
    elif mission_id in config.add_on_photo_mission:
        await process_add_on_photo_mission_filling(client, message, student_mission_info)
    elif mission_id in config.photo_mission_list:
        await process_photo_mission_filling(client, message, student_mission_info)
    elif mission_id in config.theme_mission_list:
        await process_theme_mission_filling(client, message, student_mission_info)
    elif mission_id >= 102 and mission_id <= 135:
        msg = (
            "孕期如果有任何問題，可以找24小時AI育兒助手「喵喵 <@1287675308388126762>」\n"
            "或是聯絡社群客服「阿福 <@1272828469469904937>」。"
        )
        await message.channel.send(msg)
    else:
        msg = (
            "無法處理您的訊息，任務有什麼不清楚的部分\n"
            "若有育兒問題，請找24小時AI育兒助手「喵喵 <@1287675308388126762>」\n"
            "或是聯絡社群客服「阿福 <@1272828469469904937>」。"
        )
        await message.channel.send(msg)
    return

async def handle_start_mission(client, user_id, mission_id):
    mission_id = int(mission_id)
    if mission_id >= 101 and mission_id <= 135:
        await handle_pregnancy_mission_start(client, user_id, mission_id)
    elif mission_id in config.theme_mission_list:
        await handle_theme_mission_start(client, user_id, mission_id)
    elif mission_id in config.audio_mission:
        await handle_audio_mission_start(client, user_id, mission_id)
    elif mission_id in config.questionnaire_mission:
        await handle_questionnaire_mission_start(client, user_id, mission_id)
    elif mission_id in config.photo_mission_list:
        await handle_photo_mission_start(client, user_id, mission_id)
    elif mission_id < 100 and mission_id not in config.photo_mission_list:
        await handle_quiz_mission_start(client, user_id, mission_id)
    elif mission_id in config.confirm_album_mission:
        await handle_confirm_growth_album_mission_start(client, user_id, mission_id)
    else:
        print(f"Unhandled mission ID: {mission_id}")
        return

async def handle_notify_photo_ready_job(client, user_id, baby_id, mission_id):
    try:
        # Send the photo message to the user
        client.logger.info(f"Send photo message to user {user_id}, baby_id: {baby_id}, mission {mission_id}")
        mission_result = await client.api_utils.get_student_mission_status(str(user_id), mission_id)
        user = await client.fetch_user(user_id)
        view = GrowthPhotoView(client, user_id, int(mission_id), mission_result=mission_result)
        embed = view.generate_embed(baby_id, int(mission_id))
        view.message = await user.send(embed=embed, view=view)
        # save and delete task status
        save_growth_photo_records(str(user_id), view.message.id, mission_id, result=mission_result)
        delete_task_entry_record(str(user_id), mission_id)
        # Log the successful message send
        client.logger.info(f"Send photo message to user {user_id}, mission {mission_id}")
    except Exception as e:
        client.logger.error(f"Failed to send photo message to user {user_id}: {e}")

    return

async def handle_notify_album_ready_job(client, user_id, baby_id, book_id):
    album = await client.api_utils.get_student_album_purchase_status(user_id, book_id)
    if album is None:
        client.logger.error(f"Album not found for user {user_id}, book {book_id}")
        return

    albums = [{
        'baby_id': baby_id,
        'book_id': book_id,
        **album
    }]
    view = AlbumView(client, albums)
    embed = view.get_current_embed()

    try:
        # Send the album preview to the user
        user = await client.fetch_user(user_id)
        await user.send(embed=embed)

        # Log the successful message send
        client.logger.info(f"Send album message to user {user_id}, book {book_id}")

    except Exception as e:
        client.logger.error(f"Failed to send album message to user {user_id}: {e}")

    return

async def handle_notify_theme_book_ready_job(client, user_id, baby_id, book_id):
    mission_id = config.theme_book_map.get(book_id)
    book_info = await client.api_utils.get_student_album_purchase_status(user_id, book_id)
    mission_info = await client.api_utils.get_mission_info(mission_id)

    book_info.update({
        'user_id': str(user_id),
        'book_id': book_id,
        'mission_id': mission_id,
        'book_author': mission_info['mission_type'],
    })

    view = ThemeBookView(client, book_info)
    embed = view.get_current_embed(str(user_id))

    try:
        user = await client.fetch_user(user_id)
        view.message = await user.send(embed=embed, view=view)
        # Log the successful message send
        client.logger.info(f"Send theme book message to user {user_id}, book {book_id}")
        save_theme_book_edit_record(str(user_id), view.message.id, mission_id, book_info)
    except Exception as e:
        client.logger.error(f"Failed to send theme book message to user {user_id}: {e}")
    return

async def handle_notify_theme_book_change_page(client, user_id, baby_id):
    records = load_theme_book_edit_records()
    try:
        if str(user_id) in records:
            base_mission_id, edit_status = next(iter(records.get(str(user_id), {}).items()))
            channel = await client.fetch_user(user_id)
            message = await channel.fetch_message(int(edit_status['message_id']))
            await message.delete()

            # Create a new one
            book_info = edit_status.get('result', None)
            view = ThemeBookView(client, book_info)
            embed = view.get_current_embed(str(user_id))
            view.message = await channel.send(embed=embed, view=view)
            save_theme_book_edit_record(str(user_id), view.message.id, base_mission_id, book_info)
            client.logger.info(f"✅ Restored theme book edits for user {user_id}")
    except Exception as e:
        client.logger.warning(f"⚠️ Failed to restore theme book edits for {user_id}: {e}")

async def handle_first_photo_book(client, user_id, baby_id, book_id=1):
    baby_profile = await client.api_utils.get_baby_profile(user_id)
    baby_name = baby_profile.get('baby_name', '寶寶')
    embed = discord.Embed(
        title=f"🌏 {baby_name}的地球冒險日記",
        description=(
            "恭喜你成功為寶寶製作第一本專屬繪本封面 🎉\n\n"
            "想更快完成屬於寶寶的一整本繪本嗎？點下方按鈕，馬上解鎖秘訣 🚀"
        ),
        color=0xeeb2da,
        )
    image_url = f"https://infancixbaby120.com/discord_image/{baby_id}/{book_id}/2.jpg?t={int(time.time())}"
    embed.set_image(url=image_url)
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/logo.png",
        text="用科學育兒，用愛紀錄成長"
    )
    view = TaskSelectView(client, "show_command_instruction", 1000)
    try:
        user = await client.fetch_user(user_id)
        await user.send(embed=embed, view=view)
        client.logger.info(f"Send first photo book message to user {user_id}, book {book_id}")
        student_mission_info = {
            'user_id': user_id,
            'mission_id': 1000,
            'current_step': 1,
            'total_steps': 1
        }
        await client.api_utils.update_student_mission_status(**student_mission_info)
    except Exception as e:
        client.logger.error(f"Failed to send first photo book message to user {user_id}: {e}")
    return

async def handle_confirm_growth_album_mission_start(client, user_id, mission_id, book_id=1):
    album_status = await client.api_utils.get_student_album_purchase_status(user_id, book_id=book_id)
    client.logger.info(f"Album status for user {user_id}, book {book_id}: {album_status}")
    if album_status and album_status.get("purchase_status", "未購買") == "已購買" and album_status.get("shipping_status", "待確認") == "待確認":
        confirm_album_view = ConfirmGrowthAlbumView(client, user_id, album_result=album_status)
        embed = confirm_album_view.preview_embed()

        user = await client.fetch_user(user_id)
        if user.dm_channel is None:
            await user.create_dm()

        message = await user.send(embed=embed, view=confirm_album_view)
        confirm_album_view.message = message
        save_confirm_growth_album_record(str(user_id), message.id, book_id, result=album_status)

    return
