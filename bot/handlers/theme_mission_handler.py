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
from bot.utils.mission_instruction_utils import get_mission_instruction
from bot.config import config

async def handle_theme_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    book_id = mission['book_id']

    # Delete mission cache
    delete_mission_record(user_id)
    if user_id in client.photo_mission_replace_index:
        del client.photo_mission_replace_index[user_id]

    # Get baby info from API
    baby_info = await client.api_utils.get_baby_profile(user_id)

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': 1,
        'total_steps': 4
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    embed = build_theme_mission_instruction_embed(mission)
    await user.dm_channel.send(embed=embed)

    if baby_info and baby_info.get('baby_name'):
        # Use existing baby info - show confirmation first
        saved_results = {
            'baby_name': baby_info.get('baby_name'),
            'baby_name_en': baby_info.get('baby_name_en'),
            'birthday': baby_info.get('birthday'),
            'gender': baby_info.get('gender'),
            'relation_or_identity': None if book_id != 16 else '',
            'step_1_completed': False,  # Will be set to True after confirmation
            'ask_for_relation_or_identity': False  # Will be set to True after cover upload for book 16
        }
        save_mission_record(user_id, mission_id, saved_results)

        # Show confirmation embed with button
        embed = get_baby_confirmation_embed(saved_results)
        view = TaskSelectView(client, "theme_baby_info_confirm", mission_id, mission_result=saved_results)
        view.message = await user.dm_channel.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "theme_baby_info_confirm", mission_id, result=saved_results)
    else:
        # No baby info, ask for baby name
        embed = get_baby_registration_embed()
        await user.dm_channel.send(embed=embed)
        saved_results = {}
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
    valid_aside_texts = [t for t in mission_result.get('aside_texts', []) if t is not None and str(t).strip()]
    valid_attachments = [a for a in mission_result.get('attachments', []) if a and a.get('url')]
    valid_cover = mission_result.get('cover') and mission_result['cover'].get('url')

    if len(valid_aside_texts) > 0:
        current_step = 4
    elif len(valid_attachments) > 0:
        current_step = 3
    elif valid_cover:
        # For book 16, check if relation/identity is filled after cover
        if book_id == 16 and not mission_result.get('relation_or_identity'):
            # Have cover but need relation/identity (step 2.5)
            current_step = 2
            mission_result['ask_for_relation_or_identity'] = True
        else:
            current_step = 3
    elif mission_result.get('baby_name'):
        current_step = 2
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
        'total_steps': 4
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Save loaded mission record
    save_mission_record(user_id, mission_id, mission_result)

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
async def process_theme_mission_filling(client, message, student_mission_info):
    """
    Main flow for theme mission filling:
    1. process_user_input: Handle photo/text input and save to saved_result
    2. determine_next_step: Decide what to do next
    3. send_mission_step or submit_theme_mission
    """
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    book_id = student_mission_info['book_id']

    # Step 1: Process user input (photo or text)
    result = await process_user_input(client, message, student_mission_info)

    if result.get('error'):
        await message.channel.send(result.get('error'))
        return

    mission_result = result.get('mission_result', {})
    is_photo_replacement = result.get('is_photo_replacement', False)

    # Handle photo replacement cleanup
    if is_photo_replacement:
        record = get_user_theme_book_edit_record(user_id, mission_id)
        message_id = record.get('message_id')
        if message_id:
            try:
                msg = await message.channel.fetch_message(int(message_id))
                if msg:
                    await msg.delete()
            except Exception as e:
                client.logger.error(f"刪除訊息失敗: {e}")
        delete_theme_book_edit_record(user_id, mission_id)

    # Step 2: Determine next step
    if is_photo_replacement and book_id in [13, 14, 15, 16]:
        replace_index = client.photo_mission_replace_index.get(user_id, 0)
        if replace_index > 0:
            next_step_type, step_index = 'question', replace_index - 1
        else:
            next_step_type, step_index = None, None
    else:
        next_step_type, step_index = determine_next_step(mission_id, book_id, mission_result)
        client.logger.info(f"Next step: {next_step_type}, index: {step_index}")

    # Set mission ready status and prepare next step info
    mission_result['is_ready'] = (next_step_type is None)

    if next_step_type == 'question':
        mission_result['current_question_index'] = step_index
    elif next_step_type == 'photo':
        mission_result['show_next_photo_instruction'] = True
        mission_result['next_photo_index'] = step_index

    # Save result to local
    save_mission_record(user_id, mission_id, mission_result)

    # Step 3: Submit or show next step
    if mission_result.get('is_ready'):
        await submit_theme_mission(client, message, student_mission_info, mission_result)
    else:
        await send_mission_step(client, message, mission_id, book_id, student_mission_info, mission_result)


async def process_user_input(client, message, student_mission_info):
    """
    Process user input (photo or text) and return updated mission_result.

    Returns:
        dict with keys:
        - 'mission_result': Updated saved_result
        - 'error': Error message if any
        - 'is_photo_replacement': True if this was a photo replacement
    """
    user_id = str(message.author.id)
    book_id = student_mission_info['book_id']
    mission_id = student_mission_info['mission_id']
    current_step = student_mission_info.get('current_step', 1)

    # Load saved mission record
    saved_result = get_mission_record(user_id, mission_id) or {
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

    has_photo = bool(message.attachments)
    has_text = bool(message.content.strip())

    # Case 1: Photo replacement mode
    if user_id in client.photo_mission_replace_index and has_photo:
        photo_index = client.photo_mission_replace_index[user_id]

        if photo_index == 0:
            # Replace cover
            cover_attachment = extract_attachment_info(message.attachments[0].url)
            saved_result['cover'] = cover_attachment
            save_mission_record(user_id, mission_id, saved_result)
            return {'mission_result': saved_result, 'is_photo_replacement': True}
        else:
            # Replace content photo
            if photo_index > len(saved_result.get('attachments') or []):
                return {'error': "無法替換照片，請重新上傳照片或是尋求客服協助喔！"}

            replace_attachment = extract_attachment_info(message.attachments[0].url, photo_index)
            # Convert HEIC/HEIF to JPG if needed
            if replace_attachment['filename'].endswith(('.heic', '.heif')):
                new_attachment = await convert_heic_to_jpg_attachment(client, replace_attachment)
                if new_attachment:
                    replace_attachment = new_attachment

            saved_result['attachments'][photo_index - 1] = replace_attachment

            # Clear aside text for this photo (book 13-16)
            if book_id in [13, 14, 15, 16]:
                if saved_result.get('aside_texts') and len(saved_result['aside_texts']) >= photo_index:
                    saved_result['aside_texts'][photo_index - 1] = None
                saved_result['is_ready'] = False

            save_mission_record(user_id, mission_id, saved_result)
            return {'mission_result': saved_result, 'is_photo_replacement': True}

    # Case 2: Baby name or relation registration (step 1)
    if not saved_result.get('step_1_completed') or saved_result.get('ask_for_relation_or_identity'):
        if has_photo:
            if not saved_result.get('step_1_completed'):
                return {'error': "請先完成主角寶寶姓名登記，再上傳照片喔！"}
            else:
                return {'error': "請先回答問題，再上傳照片喔！"}

        mission_result = await handle_text_input(client, mission_id, book_id, saved_result, message)
        return {'mission_result': mission_result}

    # Case 3: Cover photo upload (step 2)
    if current_step == 2 and has_photo and len(message.attachments) == 1:
        if not saved_result.get('ask_for_relation_or_identity'):
            cover_attachment = extract_attachment_info(message.attachments[0].url)
            saved_result['cover'] = cover_attachment

            # For book 16, set flag to ask for relation/identity after cover upload
            if book_id == 16:
                saved_result['ask_for_relation_or_identity'] = True

            save_mission_record(user_id, mission_id, saved_result)
            return {'mission_result': saved_result}

    # Case 4: Photo upload (step 3)
    if current_step == 3 and has_photo:
        required_photo_count = config.get_required_attachment_count(mission_id, 'photo')
        # Fallback for theme books
        if required_photo_count == 0 and book_id in config.theme_book_mission_map:
            intro_mission_id = config.theme_book_mission_map[book_id][0]
            required_photo_count = config.get_required_attachment_count(intro_mission_id, 'photo')

        mission_result = handle_photo_upload(mission_id, book_id, saved_result, message, required_photo_count)
        save_mission_record(user_id, mission_id, mission_result)
        return {'mission_result': mission_result}

    # Case 5: Text input for aside_text (step 4)
    if current_step == 4 and has_text:
        mission_result = await handle_text_input(client, mission_id, book_id, saved_result, message)
        return {'mission_result': mission_result}

    # Default: Error
    return {'error': "請依照步驟進行操作喔！"}

def handle_photo_upload(mission_id, book_id, saved_result, message, required_photo_count):
    """
    Handle photo upload for theme missions.
    For book 13-16: supports uploading multiple photos at once (up to 6 total)
    """
    # Count only valid attachments with urls
    attachments = saved_result.get('attachments', [])
    valid_attachments = [a for a in attachments if a and a.get('url')]
    current_photo_count = len(valid_attachments)
    upload_count = len(message.attachments)

    # Reset show_next_photo_instruction flag when photo is uploaded
    saved_result['show_next_photo_instruction'] = False

    # Case 1: User uploads multiple photos that would exceed the limit
    if current_photo_count < required_photo_count and (current_photo_count + upload_count) > required_photo_count:
        saved_result['message'] = f"已達到照片上限 {required_photo_count} 張，請挑選後再上傳喔！"
        return saved_result

    # Case 2: Already have enough photos - assume user wants to replace
    if current_photo_count >= required_photo_count:
        replace_index = required_photo_count - 1
        attachment = extract_attachment_info(message.attachments[0].url, photo_index=replace_index)
        saved_result['attachments'][replace_index] = attachment

        # Clear the corresponding aside_text for this photo
        if replace_index < len(saved_result.get('aside_texts', [])):
            saved_result['aside_texts'][replace_index] = None

        saved_result['message'] = f"已替換第 {replace_index + 1} 張照片！"
        return saved_result

    # Case 3: Normal upload - add new photos
    for att in message.attachments:
        attachment = extract_attachment_info(att.url, photo_index=current_photo_count)
        saved_result['attachments'].append(attachment)
        # Recalculate valid attachments count
        valid_attachments = [a for a in saved_result['attachments'] if a and a.get('url')]
        current_photo_count = len(valid_attachments)

    if current_photo_count < required_photo_count:
        saved_result['message'] = f"目前已收到 {current_photo_count} 張照片，還需要 {required_photo_count - current_photo_count} 張照片喔！"
    else:
        saved_result['message'] = "已收到所有照片！"

    return saved_result

async def handle_text_input(client, mission_id, book_id, saved_result, message):
    """
    Handle text input (aside_text or baby_name/relation) for theme missions.
    This function runs OpenAI prediction, assigns value to saved_result, and saves mission_record.
    """
    user_id = str(message.author.id)
    user_message = message.content.strip()

    # Check if asking for baby name
    if not saved_result.get('step_1_completed'):
        saved_result['baby_name'] = user_message
        saved_result['step_1_completed'] = True

        # For book 16, also need relation/identity
        if book_id == 16:
            saved_result['ask_for_relation_or_identity'] = True

        saved_result['message'] = f"已記錄寶寶名稱：{user_message}"
        save_mission_record(user_id, mission_id, saved_result)
        return saved_result

    # Check if asking for relation/identity (book 16 only)
    if book_id == 16 and saved_result.get('ask_for_relation_or_identity'):
        saved_result['relation_or_identity'] = user_message
        saved_result['ask_for_relation_or_identity'] = False
        saved_result['message'] = f"已記錄關係：{user_message}"
        save_mission_record(user_id, mission_id, saved_result)
        return saved_result

    # Handle aside_text questions
    current_aside_text_count = len([t for t in saved_result.get('aside_texts', []) if t is not None])
    current_question_index = saved_result.get('current_question_index', current_aside_text_count)

    # Get the current question from mission_instruction.json
    instruction_data = get_mission_instruction(mission_id, step_index=current_question_index, instruction_type='question')
    additional_context = None

    if instruction_data and instruction_data.get('question'):
        additional_context = f"Question: {instruction_data['question']}"
    else:
        # Use AI only for typo correction
        additional_context = "任務：請根據問題擷取需要的答案，只修正明顯的錯字和標點符號，保持原文語氣和內容不變。"

    # Build context for AI validation
    context_parts = []
    if saved_result.get('attachments'):
        context_parts.append(f"Photo count: {len(saved_result['attachments'])} photos uploaded")
    if saved_result.get('aside_texts'):
        context_parts.append(f"Previous answers: {saved_result['aside_texts']}")

    context = "\n".join(context_parts) if context_parts else ""
    conversations = [{'role': 'user', 'message': context}] if context else None

    # Run OpenAI prediction
    prompt_path = config.get_prompt_file(mission_id)

    client.logger.info(f"Assistant Input:\nprompt_path: {prompt_path}\nuser_message: {user_message}\nadditional_context: {additional_context}\nconversations: {conversations}")
    async with message.channel.typing():
        mission_result = client.openai_utils.process_user_message(
            prompt_path,
            user_message,
            conversations=conversations,
            additional_context=additional_context
        )
        client.logger.info(f"Assistant response: {mission_result}")

    # Process aside_text answer
    if mission_result.get('aside_text'):
        aside_text = mission_result['aside_text']
        required_aside_text_count = config.get_required_aside_text_count(mission_id, 'aside_text')

        if 'aside_texts' not in saved_result:
            saved_result['aside_texts'] = []

        # Store at the correct index
        if current_question_index < required_aside_text_count:
            while len(saved_result['aside_texts']) <= current_question_index:
                saved_result['aside_texts'].append(None)
            saved_result['aside_texts'][current_question_index] = aside_text

        # Replace if already full
        elif current_aside_text_count >= required_aside_text_count:
            replace_index = required_aside_text_count - 1
            while len(saved_result['aside_texts']) <= replace_index:
                saved_result['aside_texts'].append(None)
            saved_result['aside_texts'][replace_index] = aside_text
            saved_result['message'] = f"已替換第 {replace_index + 1} 個回答！"

        if 'message' not in saved_result:
            saved_result['message'] = "已記錄您的答案！"

    # Save mission_record
    save_mission_record(user_id, mission_id, saved_result)
    return saved_result

# --------------------- Mission Flow Functions ---------------------
def determine_next_step(mission_id, book_id, mission_result):
    """
    Determine the next step for theme missions.
    Step 1: Baby name (+ relation for book 16)
    Step 2: Cover photo
    Step 3: Upload 6 photos / Upload photo (6 rounds)
    Step 4: Answer questions for each photo
    Returns:
        tuple: (next_step_type: str or None, step_index: int or None)
        - ('baby_name', None) - need to register baby name
        - ('relation', None) - need to register relation (book 16 only)
        - ('cover', None) - need to upload cover
        - ('photo', photo_index) - need to upload next photo
        - ('question', question_index) - need to answer next question
        - (None, None) - mission is complete
    """

    # Step 1: Check baby name
    if not mission_result.get('step_1_completed'):
        return 'baby_name', None

    # Step 2: Check cover photo (must have valid url)
    required_cover_count = config.get_required_attachment_count(mission_id, 'cover')
    if required_cover_count > 0:
        cover = mission_result.get('cover')
        if not cover or not cover.get('url'):
            return 'cover', None

    # Step 2.5: Check relation/identity (book 16 only, after cover)
    if book_id == 16 and mission_result.get('ask_for_relation_or_identity'):
        return 'relation', None

    # Step 3 & 4: Check photos and aside_texts
    required_photo_count = config.get_required_attachment_count(mission_id, 'photo')
    required_aside_text_count = config.get_required_aside_text_count(mission_id, 'aside_text')

    # For theme books, if current mission_id has no requirements, use the first mission_id (intro mission)
    if required_photo_count == 0 and book_id in config.theme_book_mission_map:
        required_photo_count = config.get_required_attachment_count(mission_id, 'photo')
        required_aside_text_count = config.get_required_aside_text_count(mission_id, 'aside_text')

    # Count only attachments with valid urls
    attachments = mission_result.get('attachments', [])
    current_photo_count = len([a for a in attachments if a and a.get('url')])
    current_aside_text_count = len([t for t in mission_result.get('aside_texts', []) if t is not None and str(t).strip()])

    # Step 3: Upload all 6 photos
    if current_photo_count < required_photo_count:
        return 'photo', current_photo_count

    # For book 13-16: upload all photos first, then answer questions
    if book_id in [13, 14, 15, 16]:
        # Step 4: Answer questions for all photos
        if current_aside_text_count < required_aside_text_count:
            return 'question', current_aside_text_count

    # All steps completed
    return None, None

async def send_mission_step(client, message, mission_id, book_id, student_mission_info, mission_result):
    """
    Send the next step message/embed to the user.
    Handles different scenarios: asking questions, requesting next photo, etc.
    """
    client.logger.info(f"[send_mission_step] START - mission_id: {mission_id}, book_id: {book_id}")
    client.logger.info(f"[send_mission_step] mission_result keys: {mission_result.keys() if mission_result else 'None'}")

    message_text = mission_result.get('message')

    # Check if asking for relation (book 16 only)
    if book_id == 16 and mission_result.get('ask_for_relation_or_identity'):
        client.logger.info(f"[send_mission_step] Showing relation/identity embed for book 16")
        embed = get_identity_embed(student_mission_info)
        await message.channel.send(embed=embed)
        return

    # Check if we need to show cover photo instruction
    required_cover_count = config.get_required_attachment_count(mission_id, 'cover')
    client.logger.info(f"[send_mission_step] Cover check - required: {required_cover_count}, has cover: {mission_result.get('cover')}")
    if required_cover_count > 0 and not mission_result.get('cover'):
        client.logger.info(f"[send_mission_step] Showing cover instruction embed")
        embed = get_cover_instruction_embed(student_mission_info)
        await message.channel.send(embed=embed)

        # Update mission status
        student_mission_info['current_step'] = 2
        await client.api_utils.update_student_mission_status(**student_mission_info)
        return

    # Check if we need to show next photo instruction (step 3)
    attachments = mission_result.get('attachments', [])
    valid_attachments = [a for a in attachments if a and a.get('url')]
    required_photo_count = config.get_required_attachment_count(mission_id, 'photo')
    client.logger.info(f"[send_mission_step] Photo check - valid: {len(valid_attachments)}, required: {required_photo_count}, show_next: {mission_result.get('show_next_photo_instruction')}")

    if mission_result.get('show_next_photo_instruction') or (
        len(valid_attachments) < required_photo_count
    ):
        photo_index = len(valid_attachments) + 1
        client.logger.info(f"[send_mission_step] Showing photo upload embed for photo #{photo_index}")
        embed = get_story_pages_embed(book_id, student_mission_info, photo_index=photo_index, uploaded_count=len(valid_attachments))
        await message.channel.send(embed=embed)

        # Update mission status
        student_mission_info['current_step'] = 3
        await client.api_utils.update_student_mission_status(**student_mission_info)
        return

    # Check if we need to show question embed (step 4)
    current_question_index = mission_result.get('current_question_index')
    client.logger.info(f"[send_mission_step] Question check - current_question_index: {current_question_index}")

    if current_question_index is not None:
        photo_index = current_question_index + 1
        # For theme missions, all photos use the same question (step_index=0)
        client.logger.info(f"[send_mission_step] Looking up instruction for mission_id: {mission_id}, step_index: 0")
        instruction_data = get_mission_instruction(mission_id, step_index=0, instruction_type='question')
        client.logger.info(f"[send_mission_step] instruction_data: {instruction_data}")

        if instruction_data and instruction_data.get('question'):
            # Show question embed with photo
            client.logger.info(f"[send_mission_step] Showing question embed with instruction_data")
            embed = get_question_embed_with_photo(student_mission_info, mission_result, instruction_data, photo_index)
        else:
            # Fallback
            client.logger.info(f"[send_mission_step] No instruction_data, using fallback embed")
            embed = discord.Embed(
                title="請輸入照片描述",
                description="請於對話框輸入文字",
                color=0xeeb2da
            )
            # Set photo if available
            attachments = mission_result.get('attachments', [])
            valid_attachments = [a for a in attachments if a and a.get('url')]
            if photo_index <= len(valid_attachments):
                embed.set_image(url=valid_attachments[photo_index-1]['url'])

        # For book 14, no skip button
        if book_id == 14:
            await message.channel.send(embed=embed)
        else:
            # Show with skip button for book 13, 15, 16
            view = TaskSelectView(client, "skip_theme_book_aside_text", mission_id, mission_result=student_mission_info)
            view.message = await message.channel.send(embed=embed, view=view)
            save_task_entry_record(str(message.author.id), str(view.message.id), "skip_theme_book_aside_text", mission_id, result=student_mission_info)

        # Update mission status
        student_mission_info['current_step'] = 4
        await client.api_utils.update_student_mission_status(**student_mission_info)
        return

    # Default: send text message
    client.logger.info(f"[send_mission_step] Sending default message: {message_text}")
    if message_text:
        await message.channel.send(message_text)

# --------------------- Event Handlers ---------------------
async def submit_theme_mission(client, message, student_mission_info, mission_result):
    """Submit theme mission to API and trigger album generation"""
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    book_id = student_mission_info['book_id']

    cover = mission_result.get('cover')
    attachments = mission_result.get('attachments', [])
    valid_attachments = [a for a in attachments if a and a.get('url')]
    photo_count = len(valid_attachments)

    # Submit cover (mission_id)
    success = await submit_image_data(client, user_id, book_id, mission_id, mission_result, photo_index=0)

    # Submit multiple pages (mission_id+1 to mission_id+6)
    all_success = success
    for photo_index in range(1, photo_count + 1):
        submit_mission_id = mission_id + photo_index
        success = await submit_image_data(client, user_id, book_id, submit_mission_id, mission_result, photo_index=photo_index)
        if not success:
            all_success = False
            break

    if all_success:
        embed = get_waiting_embed(waiting_time='long')
        await message.channel.send(embed=embed)

        # Update all mission statuses to completed (cover + 6 content missions)
        for i in range(photo_count + 1):
            submit_mission_id = mission_id + i
            await client.api_utils.update_student_mission_status(
                user_id=user_id,
                mission_id=submit_mission_id,
                current_step=4,
                total_steps=4
            )

        # Start to generate album
        await client.api_utils.submit_generate_album_request(user_id, book_id)
        client.logger.info(f"送出繪本任務 {mission_id} 及相關 {photo_count} 個任務")

    else:
        await message.channel.send("照片上傳失敗了，請稍後再試，或是尋求客服協助喔！")
        return

async def submit_image_data(client, user_id, book_id, mission_id, mission_result, photo_index=0):
    aside_text = None
    if photo_index == 0:
        baby_info = await client.api_utils.get_baby_profile(user_id)
        baby_name = baby_info.get('baby_name', None) if baby_info else None
        aside_text = baby_name
        if book_id == 16:
            aside_text += "|" + mission_result.get('relation_or_identity', None)
        attachments = [mission_result['cover']]
    else:
        attachments = [mission_result['attachments'][photo_index-1]]
        aside_text = mission_result['aside_texts'][photo_index-1] if len(mission_result.get('aside_texts', [])) >= photo_index else None

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
        mission_results["aside_texts"].append(
            status.get("aside_text") if raw_aside_text not in (None, "", "null") else None
        )

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
            "請提供寶寶的基本資料：\n\n"
            "🧸 暱稱（建議2-3字）\n"
            "🎂 出生日期（例如：2025-05-01）\n"
            "👤 性別（男/女）"
        ),
        color=0xeeb2da,
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_baby_confirmation_embed(mission_result):
    """Show baby information confirmation"""
    context = []
    if mission_result.get('baby_name'):
        context.append(f"🧸 暱稱：{mission_result['baby_name']}")
    if mission_result.get('baby_name_en'):
        context.append(f"🧸 英文名字：{mission_result['baby_name_en']}")
    if mission_result.get('birthday'):
        context.append(f"🎂 出生日期：{mission_result['birthday']}")

    # Display gender as Chinese
    gender = mission_result.get('gender')
    if gender:
        gender_text = '男生' if gender in ['男', 'm', 'male', 'M'] else '女生' if gender in ['女', 'f', 'female', 'F'] else gender
        context.append(f"👤 性別：{gender_text}")

    embed = discord.Embed(
        title="✅ 確認主角資料",
        description="\n".join(context) if context else "無資料",
        color=0xeeb2da,
    )
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="請點選下方按鈕確認或重新填寫"
    )
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
        description=f"📸 {mission_info.get('photo_mission', '請上傳寶寶的照片')}\n\n💡 請選擇寶寶頭部置中的照片\n",
        color=0xeeb2da,
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_story_pages_embed(book_id, mission_info, photo_index, required_photos=6, uploaded_count=0):
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
    else:
        base_description = "請上傳照片"

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
    embed.set_author(name=f"{mission_info.get('mission_type', '主題繪本')}")
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_question_embed_with_photo(mission_info, mission_result, instruction_data, photo_index):
    """Build question embed with corresponding photo displayed"""
    title_text = instruction_data.get('question', '請輸入照片描述')
    description = instruction_data.get('description', '')

    embed = discord.Embed(
        title=title_text,
        description=description,
        color=0xeeb2da,
    )
    embed.set_author(name=f"✍️ {mission_info.get('mission_type', '主題繪本')} ({photo_index}/6)")

    # IMPORTANT: Show the photo for this question
    attachments = mission_result.get('attachments', [])
    valid_attachments = [a for a in attachments if a and a.get('url')]
    if photo_index <= len(valid_attachments):
        embed.set_image(url=valid_attachments[photo_index-1]['url'])

    return embed

def get_confirmation_embed(mission_id, book_id, mission_result):
    """
    Create confirmation embed for theme missions with aside_text.
    Shows all questions and answers with their corresponding photos.
    """
    aside_texts = mission_result.get('aside_texts', [])

    # Build description with questions and answers
    description_parts = []

    for i, aside_text in enumerate(aside_texts):
        if aside_text:  # Skip None or empty aside_texts
            # Get question from mission_instruction.json (all photos use step_index=0 for theme missions)
            instruction_data = get_mission_instruction(mission_id, step_index=0, instruction_type='question')

            if instruction_data and instruction_data.get('question'):
                question_title = instruction_data['question']
            else:
                question_title = f"照片 {i + 1}"

            # Format: Question followed by quoted answer
            description_parts.append(f"**{question_title}**")
            description_parts.append(f"> {aside_text}")
            description_parts.append("")  # Empty line for spacing

    # Join all parts
    description = '\n'.join(description_parts).strip()

    embed = discord.Embed(
        title="🔍 確認內容",
        description=description,
        color=0xeeb2da,
    )
    embed.set_footer(text="如需修改，請直接輸入新內容")
    return embed

def get_waiting_embed(waiting_time='short'):
    if waiting_time == 'long':
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
