import traceback
import asyncio
import discord
import os
import re
import json
from PIL import Image
import pillow_heif
import io
import requests
from types import SimpleNamespace
from datetime import datetime, date
from typing import Dict, Optional, List
from dateutil.relativedelta import relativedelta

from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    get_mission_record,
    save_mission_record,
    delete_mission_record,
    save_task_entry_record,
    get_user_theme_book_edit_record,
    delete_theme_book_edit_record
)

from bot.utils.decorator import exception_handler
from bot.utils.drive_file_utils import create_file_from_url
from bot.config import config

async def handle_theme_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    book_id = mission['book_id']

    # Delete mission cache
    delete_mission_record(user_id)
    if user_id in client.photo_mission_replace_index:
        del client.photo_mission_replace_index[user_id]

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': 1,
        'total_steps': 5
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    embed = build_theme_mission_instruction_embed(mission)
    await user.dm_channel.send(embed=embed)
    embed = get_baby_registration_embed()
    await user.dm_channel.send(embed=embed)

    saved_results = {
        'previous_question': embed.description
    }
    save_mission_record(user_id, mission_id, saved_results)

    return

async def handle_theme_mission_restart(client, user_id, book_id, mission_id=None):
    user_id = str(user_id)

    # Delete mission cache
    delete_mission_record(user_id)
    if user_id in client.photo_mission_replace_index:
        del client.photo_mission_replace_index[user_id]

    # Load mission info
    if not mission_id:
        mission_ids = config.theme_book_mission_map.get(book_id, [])
        if not mission_ids:
            return
        mission_id = mission_ids[0]

    mission = await client.api_utils.get_mission_info(mission_id)

    mission_result = await load_current_mission_status(client, user_id, book_id)
    client.logger.info(f"Loaded mission record from API for user {user_id}, mission {mission_id}: {mission_result}")

    # define current step based on loaded data
    if len(mission_result.get('aside_texts', [])) > 0:
        current_step = 4
    elif len(mission_result.get('attachments', [])) > 0:
        current_step = 3
    elif mission_result.get('cover'):
        current_step = 2
    elif mission_result.get('baby_name'):
        # book_id 16 需要額外檢查 relation_or_identity
        current_step = 1 if (book_id == 16 and not mission_result.get('relation_or_identity')) else 2
    else:
        current_step = 1

    mission_result['step_1_completed'] = current_step >= 2
    mission_result['step_2_completed'] = current_step >= 3
    mission_result['step_3_completed'] = current_step >= 4

    # Mission restart
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': current_step,
        'total_steps': 5
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Save loaded mission record
    save_mission_record(user_id, mission_id, mission_result)

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
async def process_theme_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    book_id = student_mission_info['book_id']

    request_info = await prepare_api_request(client, message, student_mission_info)
    print(f"Request info: {request_info}")

    if request_info.get('direct_action') == "replace_photo":
        record = get_user_theme_book_edit_record(user_id, mission_id)
        message_id = record.get('message_id')
        if message_id:
            try:
                msg = await message.channel.fetch_message(int(message_id))
                if msg:
                    await msg.delete()
            except Exception as e:
                client.logger.error(f"刪除訊息失敗: {e}")
                pass
        delete_theme_book_edit_record(user_id, mission_id)

    if request_info.get('direct_action') == 'error':
        await message.channel.send(request_info.get('context', '發生錯誤，請稍後再試。'))
        return
    elif request_info['needs_ai_prediction']:
        prompt_path = config.get_prompt_file(mission_id)
        async with message.channel.typing():
            conversations = [{'role': 'user', 'message': request_info['context']}] if request_info['context'] else None
            mission_result = client.openai_utils.process_user_message(prompt_path, request_info['user_message'], conversations=conversations)
            client.logger.info(f"Assistant response: {mission_result}")
    else:
        # Skip AI prediction, use direct response
        mission_result = request_info.get('direct_response', {})

    previous_result = get_mission_record(user_id, mission_id)
    mission_result = client.openai_utils.process_theme_book_validation(book_id, mission_result, previous_result)
    save_mission_record(user_id, mission_id, mission_result)

    await _handle_mission_step(client, message, student_mission_info, mission_result)

async def prepare_api_request(client, message, student_mission_info):
    user_id = str(message.author.id)
    book_id = student_mission_info['book_id']
    mission_id = student_mission_info['mission_id']
    current_step = student_mission_info.get('current_step', 1)

    # Get saved mission record
    saved_result = get_mission_record(user_id, mission_id)
    if not saved_result:
        saved_result = {
            'baby_name': None,
            'relation_or_identity': None,
            'cover': None,
            'attachments': [],
            'aside_texts': [],
            'is_ready': False
        }
    if 'attachments' not in saved_result:
        saved_result['attachments'] = []
    if 'aside_texts' not in saved_result:
        saved_result['aside_texts'] = []

    # Replace photo request
    if user_id in client.photo_mission_replace_index and message.attachments:
        photo_index = client.photo_mission_replace_index[user_id]
        if photo_index == 0:
            cover_attachment = extract_attachment_info(message.attachments[0].url)
            saved_result['cover'] = cover_attachment
            return {
                'needs_ai_prediction': False,
                'direct_action': 'cover_upload',
                'direct_response': saved_result
            }
        else:
            if photo_index > len(saved_result.get('attachments') or []):
                return {
                    'needs_ai_prediction': False,
                    'direct_action': 'error',
                    'context': "無法替換照片，請重新上傳照片或是尋求客服協助喔！"
                }

            replace_attachment = extract_attachment_info(message.attachments[0].url, photo_index)
            # Convert HEIC/HEIF to JPG if needed
            if replace_attachment['filename'].endswith('.heic') or replace_attachment['filename'].endswith('.heif'):
                new_attachment = await convert_heic_to_jpg_attachment(client, replace_attachment)
                if new_attachment:
                    replace_attachment = new_attachment

            # Save attachment info
            saved_result['attachments'][photo_index-1] = replace_attachment
            saved_result['message'] = '已收到照片'

            # Reset aside text for specific book IDs
            if book_id in [13, 14, 15, 16]:
                saved_result['aside_texts'][photo_index-1] = {
                    "photo_index": photo_index,
                    "aside_text": '[使用者選擇跳過]'
                }
                saved_result['is_ready'] = True

            return {
                'needs_ai_prediction': False,
                'direct_action': 'photo_replacement',
                'direct_response': saved_result
            }

    # baby name registration
    if current_step == 1 and message.attachments:
        return {
            'needs_ai_prediction': False,
            'direct_action': 'error',
            'context': "請先完成主角寶寶姓名登記，再上傳照片喔！"
        }

    # getting user message
    if current_step == 2 and len(message.attachments) == 1:
        cover_attachment = extract_attachment_info(message.attachments[0].url)
        saved_result['cover'] = cover_attachment
        return {
            'needs_ai_prediction': False,
            'direct_action': 'cover_upload',
            'direct_response': saved_result
        }

    elif current_step == 3 and message.attachments:
        if len(saved_result.get('attachments') or []) + len(message.attachments) > 6:
            return {
                'needs_ai_prediction': False,
                'direct_action': 'error',
                'context': "已達到照片上限6張，請挑選後再上傳喔！"
            }

        for att in message.attachments:
            attachment = extract_attachment_info(att.url, photo_index=len(saved_result['attachments'])+1)
            # Convert HEIC/HEIF to JPG if needed
            if attachment['filename'].endswith('.heic') or attachment['filename'].endswith('.heif'):
                new_attachment = await convert_heic_to_jpg_attachment(client, attachment)
                if new_attachment:
                    attachment = new_attachment

            # Save attachment info
            saved_result['attachments'].append(attachment)

        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_upload',
            'direct_response': saved_result
        }

    # getting user text input
    elif current_step == 4 and message.content.strip():
        photo_index = len([t for t in saved_result['aside_texts'] if t != 'null' and t is not None]) + 1
        user_message = (
            f"Photo {photo_index} answer: {message.content.strip()}\n"
            f"⚠️ Keep as single aside_text, do not split"
        )
    else:
        user_message = message.content

    # Build full context for AI prediction
    context = _build_full_context(user_id, mission_id, user_message, current_step)
    return {
        'needs_ai_prediction': True,
        'direct_action': None,
        'context': context,
        'user_message': user_message
    }

def _build_full_context(user_id: str, mission_id: int, current_request: str, current_step: int) -> str:
    saved_result = get_mission_record(user_id, mission_id)
    if not saved_result:
        return ""
    context_parts = []

    # Add previously collected information
    if saved_result.get('baby_name'):
        context_parts.append(f"Baby name already collected: {saved_result['baby_name']}")
    if saved_result.get('relation_or_identity'):
        context_parts.append(f"Relation or identity already collected: {saved_result['relation_or_identity']}")
    if saved_result.get('aside_texts'):
        context_parts.append(f"Previous aside texts: {saved_result['aside_texts']}")
    if saved_result.get('previous_question'):
        context_parts.append(f"Previous question asked: {saved_result['previous_question']}")
    return "\n".join(context_parts)

async def _handle_mission_step(client, message, student_mission_info, mission_result):
    user_id = str(message.author.id)
    book_id = student_mission_info['book_id']
    mission_id = student_mission_info['mission_id']
    current_step = student_mission_info.get('current_step', 1)

    # Update student_mission_info with determined step
    student_mission_info['current_step'] = current_step

    # Get enough information to proceed
    if mission_result.get('is_ready'):
        embed = get_waiting_embed(watting_time='long')
        await message.channel.send(embed=embed)

        baby_info = await client.api_utils.get_baby_profile(user_id)
        if not baby_info or not baby_info.get('baby_name', None):
            await submit_baby_data(client, message, student_mission_info, mission_result)

        # re-submit single page
        if user_id in client.photo_mission_replace_index:
            photo_index = client.photo_mission_replace_index[user_id]
            resubmit_mission_id = mission_id + photo_index
            success = await submit_image_data(client, user_id, book_id, resubmit_mission_id, mission_result, photo_index=photo_index)
            if bool(success):
                await client.api_utils.submit_generate_photo_request(user_id, resubmit_mission_id)
                client.logger.info(f"送出繪本任務 {resubmit_mission_id}")
            else:
                client.logger.warning(f"送出繪本任務 {resubmit_mission_id} 失敗")
                await message.channel.send("照片上傳失敗了，請稍後再試，或是尋求客服協助喔！")

        else:
            # submit cover
            success = await submit_image_data(client, user_id, book_id, mission_id, mission_result, photo_index=0)

            # submit multiple pages
            all_success = True
            for photo_index in range(len(mission_result.get('attachments', []))+1):
                submit_mission_id = mission_id + photo_index
                success = await submit_image_data(client, user_id, book_id, submit_mission_id, mission_result, photo_index=photo_index)
                if not success:
                    all_success = False
                    break

            if all_success:
                # start to generate album
                await client.api_utils.submit_generate_album_request(user_id, book_id)
                client.logger.info(f"送出繪本任務 {mission_id}")
            else:
                await message.channel.send("照片上傳失敗了，請稍後再試，或是尋求客服協助喔！")
                return

    else:
        if user_id in client.photo_mission_replace_index and client.photo_mission_replace_index[user_id] > 0:
            photo_index = client.photo_mission_replace_index[user_id]
            # ask for aside text
            embed = get_aside_text_instruction_embed(book_id, student_mission_info, mission_result, photo_index=photo_index)
            if book_id == 14:
                await message.channel.send(embed=embed)
            else:
                student_mission_info['photo_index'] = photo_index
                view = TaskSelectView(client, 'skip_theme_book_aside_text', mission_id, mission_result=student_mission_info)
                view.message = await message.channel.send(embed=embed, view=view)
                save_task_entry_record(user_id, str(view.message.id), "skip_theme_book_aside_text", mission_id, result=student_mission_info)

        elif mission_result.get('step_1_completed') == True and not mission_result.get('step_2_completed') and not mission_result.get('ask_for_relation_or_identity'):
            # ask for cover photo
            mission_info = await client.api_utils.get_mission_info(mission_id)
            embed = get_cover_instruction_embed(mission_info)
            await message.channel.send(embed=embed)

            # update mission status
            student_mission_info['current_step'] = 2
            await client.api_utils.update_student_mission_status(**student_mission_info)

        elif mission_result.get('ask_for_relation_or_identity'):
            # special handling for book_id 16 (relationship recognition)
            embed = get_identity_embed(student_mission_info)
            mission_result['previous_question'] = embed.description
            save_mission_record(user_id, mission_id, mission_result)
            await message.channel.send(embed=embed)

        elif mission_result.get('step_2_completed') == True and not mission_result.get('step_3_completed'):
            attachments = mission_result.get('attachments', [])
            # ask for next photo
            photo_index = len(attachments) + 1
            mission_info = await client.api_utils.get_mission_info(mission_id+photo_index)
            embed = get_story_pages_embed(book_id, mission_info, photo_index=photo_index, uploaded_count=len(attachments))
            await message.channel.send(embed=embed)

            # update mission status
            student_mission_info['current_step'] = 3
            await client.api_utils.update_student_mission_status(**student_mission_info)

        elif mission_result.get('step_3_completed') == True and not mission_result.get('step_4_completed'):
            aside_texts = mission_result.get('aside_texts', [])
            photo_index = len(aside_texts) + 1
            # ask for aside text
            embed = get_aside_text_instruction_embed(book_id, student_mission_info, mission_result, photo_index=photo_index)
            mission_result['previous_question'] = embed.description
            save_mission_record(user_id, mission_id, mission_result)
            if book_id == 14:
                await message.channel.send(embed=embed)
            else:
                view = TaskSelectView(client, 'skip_theme_book_aside_text', mission_id, mission_result=student_mission_info)
                view.message = await message.channel.send(embed=embed, view=view)
                save_task_entry_record(user_id, str(view.message.id), "skip_theme_book_aside_text", mission_id, result=student_mission_info)
            
            # update mission status
            student_mission_info['current_step'] = 4
            await client.api_utils.update_student_mission_status(**student_mission_info)

        else:
            # Continue to collect additional information
            await message.channel.send(mission_result['message'])

# --------------------- Event Handlers ---------------------
async def submit_baby_data(client, message, student_mission_info, mission_result):
    response = await client.api_utils.update_student_baby_name(str(message.author.id), mission_result.get('baby_name', None))
    if not bool(response):
        await message.channel.send("更新寶寶資料失敗，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
        return False
    return True

async def submit_image_data(client, user_id, book_id, mission_id, mission_result, photo_index=0):
    aside_text = None
    if photo_index == 0:
        baby_name = mission_result.get('baby_name', None)
        if not baby_name:
            baby_info = await client.api_utils.get_baby_profile(user_id)
            baby_name = baby_info.get('baby_name', None) if baby_info else None
        aside_text = baby_name
        if book_id == 16:
            aside_text += "|" + mission_result.get('relation_or_identity', None)
        attachments = [mission_result['cover']]
    else:
        attachments = [mission_result['attachments'][photo_index-1]]
        aside_text = mission_result['aside_texts'][photo_index-1].get("aside_text", None) if len(mission_result.get('aside_texts', [])) >= photo_index else None

    success = await client.api_utils.update_mission_image_content(user_id, mission_id, attachments, aside_text=aside_text)
    return bool(success)

# --------------------- Helper Functions ---------------------
def extract_attachment_info(attachment_url: str, photo_index: int=0) -> Optional[Dict[str, str]]:
    """Extracts attachment ID, filename, and full URL from a Discord attachment URL."""

    pattern = r'https://cdn\.discordapp\.com/attachments/(\d+)/(\d+)/([^?]+)(\?.*)?'
    match = re.match(pattern, attachment_url)
    if not match:
        return None

    channel_id, attachment_id, filename, query_params = match.groups()
    return {
        "photo_index": photo_index,
        "id": attachment_id,
        "filename": filename.lower(),
        "url": attachment_url
    }

async def convert_heic_to_jpg_attachment(client, heic_attachment):
    try:
        # you need to revised the request to fetch the heic image using async ways
        async with client.session.get(heic_attachment['url']) as response:
            heic_content = await response.read()

        client.logger.info(f"開始轉換 HEIC 檔案: {heic_attachment['filename']}")
        heic_data = io.BytesIO(heic_content)
        heif_file = pillow_heif.read_heif(heic_data)
        image = Image.frombytes(
            heif_file.mode,
            heif_file.size,
            heif_file.data,
            "raw",
        )

        # convert to JPEG
        jpg_buffer = io.BytesIO()
        image.save(jpg_buffer, format='JPEG', quality=85)
        jpg_buffer.seek(0)

        # post to upload_data channel
        background_channel = client.get_channel(int(config.FILE_UPLOAD_CHANNEL_ID))
        if background_channel is None or not isinstance(background_channel, discord.TextChannel):
            raise Exception('Invalid channel')

        jpg_filename = heic_attachment['filename'].replace('.heic', '.jpg').replace('.heif', '.jpg')
        jpg_file = discord.File(jpg_buffer, filename=jpg_filename)
        jpg_message = await background_channel.send(file=jpg_file)
        client.logger.info(f"HEIC 轉換成功，JPG 訊息 ID: {jpg_message.id}")
        return {
            "photo_index": heic_attachment['photo_index'],
            "id": jpg_message.attachments[0].id,
            "filename": jpg_message.attachments[0].filename,
            "url": jpg_message.attachments[0].url
        }

    except Exception as e:
        print(f"HEIC 轉換失敗: {e}")
        return None

# --------------------- Mission Status Loader ---------------------
async def load_current_mission_status(client, user_id, book_id):
    mission_ids = config.theme_book_mission_map.get(book_id, [])
    if not mission_ids:
        return {
            "baby_name": None,
            "relation_or_identity": None,
            "cover": {"photo_index": 0, "url": None},
            "attachments": [],
            "aside_texts": [],
        }

    mission_statuses = {}
    for mission_id in mission_ids:
        status = await client.api_utils.get_student_mission_status(user_id, mission_id)
        mission_statuses[mission_id] = status or {}

    mission_results = {}
    # process baby name and relation/identity
    cover_status = mission_statuses.get(mission_ids[0], {})
    aside_text_cover = cover_status.get("aside_text")
    if aside_text_cover:
        if book_id == 16:
            parts = aside_text_cover.split("|")
            mission_results["baby_name"] = parts[0] if len(parts) > 0 else None
            mission_results["relation_or_identity"] = parts[1] if len(parts) > 1 else None
        else:
            mission_results["baby_name"] = aside_text_cover
    else:
        mission_results["baby_name"] = None
        if book_id == 16:
            mission_results["relation_or_identity"] = None

    # process cover and attachments
    mission_results["cover"] = {
        "photo_index": 0,
        "url": cover_status.get("image_url", None),
    }
    mission_results['attachments'], mission_results['aside_texts'] = [], []
    for mission_id in mission_ids[1:]:
        status = mission_statuses.get(mission_id, {})
        mission_results["attachments"].append({
            "photo_index": mission_id - mission_ids[0],
            "url": status.get("image_url", None),
        })

        raw_aside_text = status.get("aside_text")
        mission_results["aside_texts"].append({
            "photo_index": mission_id - mission_ids[0],
            "aside_text": status.get("aside_text") if raw_aside_text not in (None, "", "null") else "[使用者選擇跳過]",
        })

    return mission_results

# --------------------- Embed Builders ---------------------
def build_theme_mission_instruction_embed(mission_info):
    embed = discord.Embed(
        title=mission_info['mission_type'],
        description=mission_info['mission_instruction'],
        color=0xeeb2da
    )
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )
    return embed

def get_baby_registration_embed():
    embed = discord.Embed(
        title="📝 主角登記",
        description=(
            "🧸 暱稱（建議2-3字）\n"
        ),
        color=0xeeb2da,
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_identity_embed(mission_info):
    embed = discord.Embed(
        title="📝 這位特別的陪伴者是誰呢？",
        description="例如：爸爸、媽媽、爺爺奶奶、兄弟姊妹、寵物⋯⋯\n(也可以輸入名字喔！)",
        color=0xeeb2da,
    )
    embed.set_author(name=f"成長繪本｜{mission_info['mission_title']}")
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_cover_instruction_embed(mission_info):
    embed = discord.Embed(
        title="📤 請上傳封面照片",
        description=f"📸 {mission_info['photo_mission']}\n\n💡 請選擇寶寶頭部置中的照片\n",
        color=0xeeb2da,
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_story_pages_embed(book_id, mission_info, photo_index, required_photos=6, uploaded_count=0):
    if book_id in [13, 14, 15, 16]:
        remaining = required_photos - uploaded_count
        if uploaded_count == 0:
            title = f"📸 上傳照片（0/{required_photos}）"
        elif uploaded_count < required_photos:
            title = f"📸 上傳照片（{uploaded_count}/{required_photos}）"
        else:
            title = f"✅ 照片上傳完成（{required_photos}/{required_photos}）"

        if book_id == 13:
            base_description = "請上傳 **寶寶與動物的合照**"
        elif book_id == 14:
            base_description = "請上傳 **寶寶與家人的合照**"
        elif book_id == 15:
            base_description = "請上傳 **寶寶與日常用品的照片**"
        elif book_id == 16:
            base_description = "請上傳 **寶寶與特別陪伴者的合照**"

        if uploaded_count == 0:
            description = f"{base_description}\n💡 一次可以上傳多張照片"
        elif uploaded_count < required_photos:
            description = f"{base_description}\n\n✅ 已收到 **{uploaded_count}** 張\n⏳ 還需要 **{remaining}** 張"
        else:
            description = f"{base_description}\n\n🎉 已收到全部 **{required_photos}** 張照片！"

        embed = discord.Embed(
            title=title,
            description=description,
            color=0xeeb2da,
        )
        embed.set_author(name=f"{mission_info['mission_type']}")
    else:
        embed = discord.Embed(
            title="📤 請上傳指定照片",
            description=f"💡 {mission_info['photo_mission']}",
            color=0xeeb2da,
        )
        embed.set_author(name=f"{mission_info['mission_type']} ({photo_index}/6)")
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_aside_text_instruction_embed(book_id, mission_info, mission_result, photo_index):
    if book_id == 13:
        title = "請問照片裡的動物是什麼？"
        description = "例如：大象、長頸鹿、獅子等⋯⋯"
    elif book_id == 14:
        title = "請問照片中的人是誰呢？(15字以內)"
        description = "例如：媽媽、阿公、阿嬤、兄弟姊妹、寵物⋯⋯\n(也可以輸入名字喔！)"
    elif book_id == 15:
        title = "請問照片中的物品是什麼？"
        description = "例如：奶瓶、玩偶、碗、襪子等。"
    elif book_id == 16:
        title = "請描述寶寶和特定陪伴者的互動(15字以內)"
        description = "例如：一起玩耍、閱讀故事書、散步等。"
    else:
        title = "請輸入照片描述"
        description = "例如：第一次翻身、第一次去公園。"

    embed = discord.Embed(
        title=title,
        description=description,
        color=0xeeb2da,
    )
    embed.set_image(url=mission_result['attachments'][photo_index-1]['url'])
    embed.set_author(name=f"✍️ {mission_info['mission_type']} ({photo_index}/6)")
    return embed

def get_waiting_embed(watting_time='short'):
    if watting_time == 'long':
        embed = discord.Embed(
            title=f"繪本準備中，請稍 3 ~ 5 分鐘喔 !",
            color=0xeeb2da
        )
    else:
        embed = discord.Embed(
            title=f"繪本準備中，請稍等一下",
            color=0xeeb2da
        )
    embed.set_image(url=f"https://infancixbaby120.com/discord_assets/loading2.gif")
    return embed
