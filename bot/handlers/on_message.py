import asyncio
import discord
import os
import re
import time

from bot.config import config
from bot.handlers.questionnaire_mission_handler import (
    handle_questionnaire_mission_start,
    process_questionnaire_mission_filling
)
from bot.handlers.profile_handler import (
    handle_registration_mission_start,
    process_baby_profile_filling
)
from bot.handlers.photo_mission_handler import (
    handle_photo_mission_start,
    process_photo_mission_filling
) 
from bot.handlers.pregnancy_mission_handler import (
    handle_pregnancy_mission_start,
    process_pregnancy_registration_message
)
from bot.handlers.audio_mission_handler import (
    handle_audio_mission_start,
    process_audio_mission_filling
)
from bot.handlers.video_mission_handler import (
    handle_video_mission_start,
    process_video_mission_filling
)
from bot.handlers.theme_mission_handler import (
    handle_theme_mission_start,
    handle_theme_mission_restart,
    process_theme_mission_filling
)
from bot.views.growth_photo import GrowthPhotoView
from bot.views.album_select_view import AlbumView
from bot.views.confirm_growth_album_view import ConfirmGrowthAlbumView
from bot.views.theme_book_view import EditThemeBookView
from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    save_task_entry_record,
    delete_task_entry_record,
    save_growth_photo_records,
    load_theme_book_edit_records,
    save_theme_book_edit_record,
    save_confirm_growth_albums_record
)
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.utils.id_utils import encode_ids

async def handle_background_message(client, message):
    client.logger.debug(f"Background message received: {message}")
    client.logger.debug(f"Message mentions: {message.mentions}")

    if len(message.mentions) != 1:
        return

    user_id = message.mentions[0].id
    content = message.content

    # Determine the environment prefix
    prefix = 'DEV_' if config.ENV else ''

    patterns = [
        (rf'START_MISSION_{prefix}(\d+)', handle_mission),
        (rf'PHOTO_GENERATION_COMPLETED_{prefix}(\d+)_(\d+)', handle_photo),
        (rf'ALBUM_GENERATION_COMPLETED_{prefix}(\d+)_(\d+)', handle_album),
        (rf'MONTHLY_PRINT_{prefix}REMINDER', handle_notify_monthly_print_reminder_job),
    ]
    for pattern, handler in patterns:
        match = re.search(pattern, content)
        if match:
            await handler(client, user_id, match)
            return

async def handle_mission(client, user_id, match):
    mission_id = int(match.group(1))
    if mission_id == 1000:
        await handle_app_instruction(client, user_id, mission_id)
    elif mission_id in config.book_intro_mission:
        await handle_book_intro_mission(client, user_id, mission_id)
    else:
        await handle_start_mission(client, user_id, mission_id)

async def handle_photo(client, user_id, match):
    baby_id = int(match.group(1))
    mission_id = int(match.group(2))
    if mission_id < 7000:
        await handle_notify_photo_ready_job(client, user_id, baby_id, mission_id)
    else:
        await handle_notify_theme_book_change_page(client, user_id, baby_id)

async def handle_album(client, user_id, match):
    baby_id = int(match.group(1))
    book_id = int(match.group(2))
    if book_id in config.theme_book_mission_map:
        await handle_theme_mission_restart(client, user_id, book_id)
        await handle_notify_theme_book_ready_job(client, user_id, baby_id, book_id)
    else:
        await handle_notify_album_ready_job(client, user_id, baby_id, book_id)

async def handle_direct_message(client, message):
    client.logger.debug(f"Message received: {message}")
    user_id = str(message.author.id)

    # Check for baby book activation keyword
    if "開啟製作寶寶繪本" in message.content:
        await client.api_utils.store_message(str(user_id), 'user', message.content)
        await handle_app_instruction(client, int(user_id), 1000)
        return

    student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)

    if not bool(student_mission_info):
        await client.api_utils.store_message(str(user_id), 'user', message.content)
        reply_msg = "請於對話框輸入 */查看育兒里程碑*，重啟任務"
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
        message.content = "收到使用者的影片"
    else:
        if not message.content.strip():
            await message.channel.send(f"無法處理您上傳的檔案內容，請輸入文字訊息或確保檔案格式正確後再試一次。如需幫助，請聯絡客服。")
            return

    await client.api_utils.store_message(user_id, 'user', message.content)
    mission_id = int(student_mission_info['mission_id'])
    student_mission_info['user_id'] = user_id
    # dispatch question
    if mission_id in config.baby_profile_registration_missions:
        await process_baby_profile_filling(client, message, student_mission_info)
    elif mission_id == config.pregnant_registration_mission:
        await process_pregnancy_registration_message(client, message, student_mission_info)
    elif mission_id in config.video_mission:
        await process_video_mission_filling(client, message, student_mission_info)
    elif mission_id in config.audio_mission:
        await process_audio_mission_filling(client, message, student_mission_info)
    elif mission_id in config.questionnaire_mission:
        await process_questionnaire_mission_filling(client, message, student_mission_info)
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
    from bot.handlers.utils import start_mission_by_id

    mission_id = int(mission_id)

    # Handle special cases first
    if mission_id == 1000:
        await handle_app_instruction(client, user_id, mission_id)
    elif mission_id >= 101 and mission_id <= 135:
        await handle_pregnancy_mission_start(client, user_id, mission_id)
    elif mission_id in config.confirm_album_mission:
        await handle_confirm_growth_album_mission_start(client, user_id, mission_id)
    else:
        # Use shared mission routing function for common mission types
        await start_mission_by_id(client, user_id, mission_id, send_weekly_report=1)

async def handle_app_instruction(client, user_id, mission_id):
    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    embed = discord.Embed(
        title="👋 歡迎來到 Baby120 繪本工坊",
        description=(
            "**📖 什麼是繪本工坊？**\n"
            "用簡單幾步驟，為寶寶製作專屬成長繪本，記錄每個月的珍貴瞬間\n\n"
            "**🎯 製作流程（4 步驟）**\n"
            "1️⃣ 登記寶寶姓名 → 完成封面\n"
            "2️⃣ 逐頁製作內頁 → 上傳照片 + 輸入內容 + 即時瀏覽\n"
            "3️⃣ 完成後預覽整本繪本\n"
            "4️⃣ 每月 1 號由客服阿福聯絡送印出貨\n"
            "⚠️ 試用版可製作部分頁面\n\n"
            "📖 [製作繪本教學](https://baby120.ai/make-book-guide/)\n\n"
            "------\n"
            "🚀 點擊下方按鈕，開始製作第一個月的繪本吧！"
        ),
        color=0xeeb2da,
    )
    embed.set_image(url="https://infancixbaby120.com/discord_assets/app_intro.jpg")
    embed.set_footer(
        text="若有任何問題，請聯絡社群客服「阿福」。"
    )
    view = TaskSelectView(client, "go_book_instruction", mission_id=1000)
    view.message = await user.send(embed=embed, view=view)
    save_task_entry_record(user_id, str(view.message.id), "go_book_instruction", mission_id)
    return

async def handle_book_intro_mission(client, user_id, mission_id):
    mission_info = await client.api_utils.get_mission_info(mission_id)
    book_info = await client.api_utils.get_album_info(mission_info['book_id'])
    embed = discord.Embed(
        title=f"📖繪本介紹: **{book_info['book_title']}**",
        description=(
            f"{book_info['book_introduction']}\n\n"
            f"{mission_info['mission_instruction']}"
        ),
        color=0xeeb2da,
    )
    if 'mission_instruction_image_url' in mission_info and mission_info['mission_instruction_image_url'] != "":
        instruction_url = create_preview_image_from_url(mission_info['mission_instruction_image_url'])
        embed.set_image(url=instruction_url)

    book_id = mission_info.get('book_id', None)
    if book_id is None:
        client.logger.error(f"Book ID not found for mission {mission_id}")
        return

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    payload = {
        'user_id': user_id,
        'book_id': book_id,
        'mission_id': mission_id,
        'next_mission_id': mission_id,
        'is_first_mission': True,
    }
    view = TaskSelectView(client, "go_next_mission", mission_id, mission_result=payload)
    view.message = await user.send(embed=embed, view=view)
    save_task_entry_record(user_id, str(view.message.id), "go_next_mission", mission_id, payload)
    return

async def handle_notify_photo_ready_job(client, user_id, baby_id, mission_id):
    try:
        # Send the photo message to the user
        client.logger.info(f"Send photo message to user {user_id}, baby_id: {baby_id}, mission {mission_id}")
        mission_result = await client.api_utils.get_student_mission_status(str(user_id), mission_id)
        user = await client.fetch_user(user_id)
        mission_result = {
            **mission_result,
            'user_id': str(user_id),
            'baby_id': baby_id,
            'book_id': mission_result['book_id']
        }
        view = GrowthPhotoView(client, user_id, int(mission_id), mission_result=mission_result)
        embed, file_path, filename = view.generate_embed(baby_id, int(mission_id))
        await asyncio.sleep(0.5)
        file = discord.File(file_path, filename=filename)
        view.message = await user.send(embed=embed, view=view, file=file)
        # save and delete task status
        save_growth_photo_records(str(user_id), view.message.id, mission_id, result=mission_result)
        delete_task_entry_record(str(user_id), mission_id)
        # Log the successful message send
        client.logger.info(f"Send photo message to user {user_id}, mission {mission_id}")
    except Exception as e:
        client.logger.error(f"Failed to send photo message to user {user_id}: {e}")

    return

async def handle_notify_album_ready_job(client, user_id, baby_id, book_id):
    album_info = await client.api_utils.get_student_album_purchase_status(user_id, book_id)
    completed_missions = await client.api_utils.get_student_complete_photo_mission(user_id, book_id)
    incomplete_missions = await client.api_utils.get_student_incomplete_photo_mission(user_id, book_id)
    if album_info is None:
        client.logger.error(f"Album not found for user {user_id}, book {book_id}")
        return

    try:
        # Create the album preview view
        view = AlbumView(client, user_id, album_info, completed_missions, incomplete_missions)
        embed, file_path, filename, fallback_url = view.preview_embed()

        # Send the album preview to the user
        user = await client.fetch_user(user_id)
        await asyncio.sleep(0.5)

        try:
            file = discord.File(file_path, filename=filename)
            await user.send(embed=embed, view=view, file=file)
        except FileNotFoundError:
            client.logger.warning(f"File not found: {file_path}, using fallback URL: {fallback_url}")
            if fallback_url:
                embed.set_image(url=fallback_url)
            await user.send(embed=embed, view=view)
        except Exception as e:
            client.logger.error(f"Error loading file {file_path}: {e}, using fallback URL: {fallback_url}")
            if fallback_url:
                embed.set_image(url=fallback_url)
            await user.send(embed=embed, view=view)

        # Log the successful message send
        client.logger.info(f"Send album message to user {user_id}, book {book_id}")
    except Exception as e:
        client.logger.error(f"Failed to send album message to user {user_id}: {e}")
    return

async def handle_notify_theme_book_ready_job(client, user_id, baby_id, book_id):
    book_info = await client.api_utils.get_student_album_purchase_status(user_id, book_id)
    view = EditThemeBookView(client, book_info)
    embed, file_path, filename = view.get_current_embed(str(user_id))
    file = discord.File(file_path, filename=filename)
    try:
        user = await client.fetch_user(user_id)
        await asyncio.sleep(0.5)
        view.message = await user.send(
            embed=embed,
            view=view,
            file=file,
        )
        # Log the successful message send
        client.logger.info(f"Send theme book message to user {user_id}, book {book_id}")
        save_theme_book_edit_record(str(user_id), view.message.id, book_id, book_info)
    except Exception as e:
        client.logger.error(f"Failed to send theme book message to user {user_id}: {e}")
    return

async def handle_notify_theme_book_change_page(client, user_id, baby_id):
    records = load_theme_book_edit_records()
    try:
        if str(user_id) in records:
            book_id, edit_status = next(iter(records.get(str(user_id), {}).items()))
            channel = await client.fetch_user(user_id)

            # Try to delete old message, but don't fail if it doesn't exist
            try:
                message = await channel.fetch_message(int(edit_status['message_id']))
                await message.delete()
            except discord.NotFound:
                client.logger.info(f"ℹ️ Old message not found for {user_id}, skipping delete")
            except discord.Forbidden:
                client.logger.warning(f"⚠️ No permission to delete message for {user_id}")
            except Exception as delete_error:
                client.logger.warning(f"⚠️ Unexpected error deleting message for {user_id}: {delete_error}")

            # Create a new one
            book_info = edit_status.get('result', None)
            view = EditThemeBookView(client, book_info)
            embed, file_path, filename = view.get_current_embed(str(user_id))
            file = discord.File(file_path, filename=filename)
            await asyncio.sleep(0.5)
            view.message = await channel.send(
                embed=embed,
                view=view,
                file=file,
            )
            save_theme_book_edit_record(str(user_id), view.message.id, book_id, book_info)
            client.logger.info(f"✅ Restored theme book edits for user {user_id}")

    except Exception as e:
        client.logger.warning(f"⚠️ Failed to restore theme book edits for {user_id}: {e}")

async def handle_confirm_growth_album_mission_start(client, user_id, mission_id):
    mission_info = await client.api_utils.get_mission_info(mission_id)
    book_id = mission_info.get('book_id', None)
    await handle_notify_album_job(client, user_id, mission_id, book_id)

async def handle_notify_album_job(client, user_id, mission_id, book_id):
    album_info = await client.api_utils.get_student_album_purchase_status(user_id, book_id)
    completed_missions = await client.api_utils.get_student_complete_photo_mission(user_id, book_id)
    incomplete_missions = await client.api_utils.get_student_incomplete_photo_mission(user_id, book_id)
    client.logger.info(f"Album status for user {user_id}, book {book_id}: {album_info}, incomplete missions: {len(incomplete_missions)}")
    if album_info and album_info.get("purchase_status", "未購買") == "已購買" and album_info.get("shipping_status", "待確認") == "待確認":
        view = AlbumView(client, user_id, album_info, completed_missions, incomplete_missions)
        embed, file_path, filename, fallback_url = view.preview_embed()
        user = await client.fetch_user(user_id)
        if user.dm_channel is None:
            await user.create_dm()
        await asyncio.sleep(0.5)

        try:
            file = discord.File(file_path, filename=filename)
            view.message = await user.send(embed=embed, view=view, file=file)
        except FileNotFoundError:
            client.logger.warning(f"File not found: {file_path}, using fallback URL: {fallback_url}")
            if fallback_url:
                embed.set_image(url=fallback_url)
            view.message = await user.send(embed=embed, view=view)
        except Exception as e:
            client.logger.error(f"Error loading file {file_path}: {e}, using fallback URL: {fallback_url}")
            if fallback_url:
                embed.set_image(url=fallback_url)
            view.message = await user.send(embed=embed, view=view)
    return

async def handle_notify_monthly_print_reminder_job(client, user_id, match):
    albums_info = await client.api_utils.get_purchase_students_reminder_list(user_id)
    incomplete_missions = await client.api_utils.get_student_incomplete_photo_mission(user_id)
    view = ConfirmGrowthAlbumView(client, str(user_id), albums_info, incomplete_missions)
    embed = view.preview_embed()
    try:
        user = await client.fetch_user(user_id)
        if user.dm_channel is None:
            await user.create_dm()

        await asyncio.sleep(0.5)
        view.message = await user.send(embed=embed, view=view)
        save_confirm_growth_albums_record(str(user_id), view.message.id, albums_info, incomplete_missions)
        client.logger.info(f"Send monthly print reminder to user {user_id}")

    except Exception as e:
        client.logger.error(f"Failed to send monthly print reminder to user {user_id}: {e}")
    return
