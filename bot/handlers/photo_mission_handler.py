import traceback
import discord
import os
import re
import json
from types import SimpleNamespace
from datetime import datetime, date
from typing import Dict, Optional, List
from dateutil.relativedelta import relativedelta

from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    save_task_entry_record,
    get_mission_record,
    save_mission_record,
    delete_mission_record,
)
from bot.utils.decorator import exception_handler
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.utils.mission_instruction_utils import get_mission_instruction
from bot.config import config

async def handle_photo_mission_start(client, user_id, mission_id, send_weekly_report=1):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    book = await client.api_utils.get_student_album_purchase_status(user_id, book_id=mission.get('book_id', None)) if mission.get('book_id') else {}
    baby = await client.api_utils.get_baby_profile(user_id)

    # Delete conversation cache
    delete_mission_record(user_id)
    if user_id in client.photo_mission_replace_index:
        del client.photo_mission_replace_index[user_id]
    if user_id in client.skip_aside_text:
        del client.skip_aside_text[user_id]

    # Mission initialization
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': 1,
        'total_steps': 4
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Prepare next mission
    book_id = mission.get('book_id', 0)
    incomplete_missions = await client.api_utils.get_student_incomplete_photo_mission(user_id, book_id)
    next_mission_id = None
    for m in incomplete_missions:
        if m['mission_id'] != mission_id:
            next_mission_id = m['mission_id']
            student_mission_info['next_mission_id'] = next_mission_id
            break

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    if mission_id in config.add_on_photo_mission:
        student_profile = await client.api_utils.get_student_profile(user_id)
        embed = get_add_on_photo_embed(mission, student_profile)
        view = TaskSelectView(client, "check_add_on", mission_id, mission_result=mission)
        view.message = await user.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "check_add_on", mission_id, result=mission)

    else:
        # photo mission
        embed, files = await build_photo_mission_embed(mission, baby, book)
        if send_weekly_report and files:
            await user.send(files=files)
    
        view = TaskSelectView(client, "skip_mission", mission_id, mission_result=student_mission_info)
        view.message = await user.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "skip_mission", mission_id, result=student_mission_info)

    return

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
async def process_photo_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    request_info = await process_user_input(client, message, student_mission_info)
    print(f"Request info: {request_info}")

    if request_info.get('direct_action') == 'error':
        await message.channel.send(request_info.get('context', '發生錯誤，請稍後再試。'))
        return

    # Get mission_result from direct_response (handle_text_input is now self-contained)
    mission_result = request_info.get('direct_response', {})

    # Determine next step using the new function
    next_step_type, step_index = determine_next_step(mission_id, mission_result)
    client.logger.info(f"Next step: {next_step_type}, index: {step_index}")

    # Set mission ready status
    mission_result['is_ready'] = (next_step_type is None)

    # Handle next step based on type
    if next_step_type == 'question':
        # Next step is to ask a question
        mission_result['current_question_index'] = step_index
        instruction_data = get_mission_instruction(mission_id, step_index=step_index, instruction_type='question')
        client.logger.info(f"instruction_data: {instruction_data}")
        if instruction_data and instruction_data.get('question'):
            mission_result['message'] = instruction_data['question']

    elif next_step_type == 'photo':
        # Next step is to upload a photo
        mission_result['show_next_photo_instruction'] = True
        mission_result['next_photo_index'] = step_index

    # Save all result to local
    save_mission_record(user_id, mission_id, mission_result)

    if mission_result.get('is_ready'):
        # Mission is complete - show confirmation or submit directly
        if should_show_confirmation(mission_id, mission_result):
            await show_confirmation(client, message, mission_id, mission_result)
        else:
            await submit_photo_mission(client, message, student_mission_info, mission_result)
    else:
        # Send next step message to user
        await send_mission_step(client, message, mission_id, student_mission_info, mission_result)

    return

def handle_photo_upload(mission_id, saved_result, message, required_photo_count, required_aside_text_count):
    """
    Handle photo upload for missions.
    Implements photo -> question -> photo -> question pattern.
    Supports photo replacement when user uploads after reaching the limit.
    """
    current_photo_count = len(saved_result['attachments'])
    upload_count = len(message.attachments)

    # Reset show_next_photo_instruction flag when photo is uploaded
    saved_result['show_next_photo_instruction'] = False

    # Case 1: User uploads multiple photos that would exceed the limit (before reaching limit)
    if current_photo_count < required_photo_count and (current_photo_count + upload_count) > required_photo_count:
        saved_result['message'] = f"已達到照片上限 {required_photo_count} 張，請挑選後再上傳喔！"
        return saved_result

    # Case 2: Already have enough photos - assume user wants to replace
    if current_photo_count >= required_photo_count:
        # Replace from the last photo backwards
        replace_index = required_photo_count - 1
        attachment = extract_attachment_info(message.attachments[0].url)
        attachment['index'] = replace_index
        saved_result['attachments'][replace_index] = attachment

        # Clear the corresponding aside_text for this photo
        if replace_index < len(saved_result['aside_texts']):
            saved_result['aside_texts'][replace_index] = None

        saved_result['message'] = f"已替換第 {replace_index + 1} 張照片！"
        return saved_result

    # Case 3: Normal upload - add new photo
    for att in message.attachments:
        attachment = extract_attachment_info(att.url)
        attachment['index'] = current_photo_count
        saved_result['attachments'].append(attachment)

        # update count
        current_photo_count = len(saved_result['attachments'])

    if current_photo_count < required_photo_count:
        saved_result['message'] = f"目前已收到 {current_photo_count} 張照片，還需要 {required_photo_count - current_photo_count} 張照片喔！"
    else:
        saved_result['message'] = "已收到所有照片！"

    return saved_result

async def handle_text_input(client, mission_id, saved_result, message):
    """
    Handle text input (aside_text answer) for missions.
    This function is self-contained: it decides question_index, runs OpenAI prediction,
    assigns value to saved_result, and saves mission_record.
    After answering, determines if we need to show next photo instruction.

    Returns:
        dict: Updated saved_result with all changes applied and saved
    """
    user_id = str(message.author.id)
    user_message = message.content
    current_aside_text_count = len(saved_result['aside_texts'])
    current_question_index = saved_result.get('current_question_index', current_aside_text_count)

    # Get the current question from mission_instruction.json
    instruction_data = get_mission_instruction(mission_id, step_index=current_question_index, instruction_type='question')
    additional_context = None

    if instruction_data and instruction_data.get('question'):
        additional_context = f"Question: {instruction_data['question']}"
    elif mission_id in config.relation_or_identity_mission:
        # For relation/identity missions, get question from instruction
        instruction_data = get_mission_instruction(mission_id, step_index=0, instruction_type='question')
        if instruction_data:
            question_text = instruction_data.get('question')
            if question_text:
                additional_context = f"Question: {question_text}"

    # If no specific question, use AI only for typo correction
    if additional_context is None:
        additional_context = "任務：只修正明顯的錯字和標點符號，保持原文語氣和內容不變。不要重寫或潤飾文字。一定要保留使用者的換行符號。"

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

    # Process aside_text answer directly into saved_result
    if mission_result.get('aside_text'):
        aside_text = mission_result['aside_text']

        # Process aside_text based on mission type
        # 1. Letter missions: no normalization or line limit (up to 400 chars)
        if mission_id in config.letter_mission:
            if len(aside_text) > 400:
                saved_result['message'] = "⚠️ 文字超過 400 字，請縮短至 400 字以內。"
                # Save mission_record with warning but don't store aside_text
                save_mission_record(user_id, mission_id, saved_result)
                return saved_result
            processed_text = aside_text

        # 2. Relation/identity missions: no normalization (just names/terms)
        elif mission_id in config.relation_or_identity_mission:
            processed_text = aside_text

        # 3. General photo missions: normalize and check line limit (max 2 lines)
        else:
            from bot.utils.openai_utils import normalize_aside_text, line_count
            processed_text = normalize_aside_text(aside_text)
            client.logger.info(f"Processed aside text: {processed_text}, line count: {line_count(processed_text)}")

            if line_count(processed_text) > 2:
                saved_result['message'] = "⚠️ 文字超過 2 行，請縮短或調整至 30 字或 2 行以內。"
                # Save mission_record with warning but don't store aside_text
                save_mission_record(user_id, mission_id, saved_result)
                return saved_result

        required_aside_text_count = config.get_required_aside_text_count(mission_id, 'aside_text')
        current_aside_text_count = len([t for t in saved_result.get('aside_texts', []) if t is not None])

        if 'aside_texts' not in saved_result:
            saved_result['aside_texts'] = []

        # Case 1: current_question_index is within required range - store at index
        if current_question_index < required_aside_text_count:
            # Ensure aside_texts list is large enough
            while len(saved_result['aside_texts']) <= current_question_index:
                saved_result['aside_texts'].append(None)

            # Store the processed answer at the correct index
            saved_result['aside_texts'][current_question_index] = processed_text

        # Case 2: Already have enough aside_texts - replace from the last one
        elif current_aside_text_count >= required_aside_text_count:
            replace_index = required_aside_text_count - 1
            # Ensure the list is long enough
            while len(saved_result['aside_texts']) <= replace_index:
                saved_result['aside_texts'].append(None)

            saved_result['aside_texts'][replace_index] = processed_text
            saved_result['message'] = f"已替換第 {replace_index + 1} 個回答！"

        # Set default message if not already set
        if 'message' not in saved_result:
            saved_result['message'] = "已記錄您的答案！"

    # Save mission_record
    save_mission_record(user_id, mission_id, saved_result)

    return saved_result

async def process_user_input(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    saved_result = get_mission_record(user_id, mission_id) or {}

    # Initialize storage for attachments and aside_texts
    if 'attachments' not in saved_result:
        saved_result['attachments'] = []
    if 'aside_texts' not in saved_result:
        saved_result['aside_texts'] = []

    # Get required counts
    required_photo_count = config.get_required_attachment_count(mission_id, 'photo')
    required_aside_text_count = config.get_required_aside_text_count(mission_id, 'aside_text')

    # Replace photo request
    if user_id in client.photo_mission_replace_index and message.attachments:
        photo_index = client.photo_mission_replace_index[user_id]

        if not saved_result['attachments'] or photo_index-1 >= len(saved_result['attachments']):
            return {
                'needs_ai_prediction': False,
                'direct_action': 'error',
                'context': "無法替換照片，請重新上傳照片或是尋求客服協助喔！"
            }

        replace_attachment = extract_attachment_info(message.attachments[0].url)
        saved_result['attachments'][photo_index-1] = replace_attachment
        if saved_result.get('aside_texts') and len(saved_result.get('aside_texts')) >= photo_index:
            saved_result['aside_texts'][photo_index-1] = None
        saved_result['message'] = "已收到您的照片"
        saved_result['is_ready'] = False
        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_replacement',
            'direct_response': saved_result
        }

    elif message.attachments:
        mission_result =  handle_photo_upload(mission_id, saved_result, message, required_photo_count, required_aside_text_count)

        # Save mission_record
        save_mission_record(user_id, mission_id, saved_result)

        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_upload',
            'direct_response': mission_result
        }

    else:
        # Handle text input - now async and self-contained (includes save_mission_record)
        mission_result = await handle_text_input(client, mission_id, saved_result, message)

        return {
            'needs_ai_prediction': False,
            'direct_action': 'text_input_processed',
            'direct_response': mission_result
        }


# --------------------- Mission Flow Functions ---------------------
def determine_next_step(mission_id, mission_result):
    """
    Determine the next step for the mission: 'question' or 'photo' or None (if ready).

    Logic:
    - If aside_text requirement is 0, always return 'photo' (until all photos collected)
    - If photo count == aside_text count, next step is 'photo'
    - If photo count > aside_text count, next step is 'question' (for the missing aside_text)
    - If all requirements met, return None

    Returns:
        tuple: (next_step_type: str or None, step_index: int or None)
        - ('photo', photo_index) - need to upload next photo
        - ('question', question_index) - need to answer next question
        - (None, None) - mission is complete
    """
    required_photo_count = config.get_required_attachment_count(mission_id, 'photo')
    required_aside_text_count = config.get_required_aside_text_count(mission_id, 'aside_text')

    current_photo_count = len(mission_result.get('attachments', []))
    current_aside_text_count = len([t for t in mission_result.get('aside_texts', []) if t is not None])

    # Check if mission is complete
    has_all_photos = current_photo_count >= required_photo_count
    has_all_aside_texts = current_aside_text_count >= required_aside_text_count or required_aside_text_count == 0

    if has_all_photos and has_all_aside_texts:
        return None, None

    # Special case: if aside_text requirement is 0, only need photos
    if required_aside_text_count == 0:
        if current_photo_count < required_photo_count:
            return 'photo', current_photo_count
        return None, None

    # Normal case: photo -> question -> photo -> question pattern
    # If counts are equal, next step is photo
    if current_photo_count == current_aside_text_count:
        if current_photo_count < required_photo_count:
            return 'photo', current_photo_count
        return None, None

    # If photo count > aside_text count, need to answer question
    elif current_photo_count > current_aside_text_count:
        if current_aside_text_count < required_aside_text_count:
            # Find which question needs to be answered (first photo without aside_text)
            for i in range(current_photo_count):
                if i >= len(mission_result.get('aside_texts', [])) or mission_result.get('aside_texts', [])[i] is None:
                    return 'question', i
        return None, None

    # If aside_text count > photo count, need to upload photo (shouldn't happen normally)
    else:
        if current_photo_count < required_photo_count:
            return 'photo', current_photo_count
        return None, None

def should_show_confirmation(mission_id, mission_result):
    """
    Determine if we should show confirmation before submitting.
    Letter missions and missions with aside_text should show confirmation.
    """
    if mission_id in config.letter_mission:
        return True
    elif mission_id in config.relation_or_identity_mission:
        return False

    # Check if mission has aside_text
    aside_texts = mission_result.get('aside_texts', [])
    if any(text for text in aside_texts if text):
        return True

    return False

async def show_confirmation(client, message, mission_id, mission_result):
    """Show confirmation embed for missions with text content."""
    embed = get_confirmation_embed(mission_id, mission_result)
    view = TaskSelectView(client, "go_submit", mission_id, mission_result=mission_result)
    view.message = await message.channel.send(embed=embed, view=view)

    user_id = str(message.author.id)
    save_task_entry_record(user_id, str(view.message.id), "go_submit", mission_id, result=mission_result)

async def send_mission_step(client, message, mission_id, student_mission_info, mission_result):
    """
    Send the next step message/embed to the user.
    Handles different scenarios: asking questions, requesting next photo, etc.
    """
    message_text = mission_result.get('message')

    # Check if we need to show next photo instruction (after answering a question)
    if mission_result.get('show_next_photo_instruction'):
        next_photo_index = mission_result.get('next_photo_index', 0)
        instruction_data = get_mission_instruction(mission_id, step_index=next_photo_index, instruction_type='upload')

        if instruction_data:
            # Show photo upload instruction embed
            book_info = student_mission_info.get('book_info')
            embed, _ = await build_photo_mission_embed(
                mission_info=student_mission_info,
                baby_info=None,
                book_info=book_info,
                step_index=next_photo_index
            )
            await message.channel.send(embed=embed)
        else:
            # Fallback: just send a text message
            await message.channel.send(message_text or "請上傳下一張照片")

    # Check if we need to show question embed
    elif mission_result.get('current_question_index') is not None:
        instruction_data = get_mission_instruction(mission_id, step_index=mission_result.get('current_question_index'), instruction_type='question')

        if instruction_data and instruction_data.get('question'):
            # Show question embed
            embed = get_embed_from_instruction(student_mission_info, instruction_data)
        else:
            embed = get_aside_text_embed()

        # Check if this mission type should have a skip button
        # Skip button for photo missions, but NOT for identity/relation/letter missions
        should_show_skip = (
            mission_id not in config.relation_or_identity_mission and
            mission_id not in config.short_answer_mission and
            mission_id not in config.letter_mission
        )

        if should_show_skip:
            # Show with skip button
            from bot.views.task_select_view import TaskSelectView
            from bot.utils.message_tracker import save_task_entry_record

            view = TaskSelectView(client, "go_skip_aside_text", mission_id, mission_result=mission_result)
            view.message = await message.channel.send(embed=embed, view=view)
            save_task_entry_record(str(message.author.id), str(view.message.id), "go_skip_aside_text", mission_id, result=mission_result)
        else:
            # Show without skip button (identity/relation/letter missions)
            await message.channel.send(embed=embed)


    elif message_text:
        # Send simple text message
        await message.channel.send(message_text)

# --------------------- Event Handlers ---------------------
async def submit_photo_mission(client, message, student_mission_info, mission_result):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # Get attachments and aside_texts
    attachments = mission_result.get('attachments', [])
    aside_texts = [str(aside_text) if aside_text else '' for aside_text in mission_result.get('aside_texts', [])]
    concated_aside_text = "|".join(aside_texts)
    content = concated_aside_text if mission_id in config.letter_mission else None
    update_status = await client.api_utils.update_mission_image_content(
        user_id,
        mission_id,
        discord_attachments=attachments,
        aside_text=concated_aside_text,
        content=content
    )

    if bool(update_status):
        if mission_id in config.add_on_photo_mission:
            embed = get_waiting_embed()
            await message.channel.send(embed=embed)

        await client.api_utils.submit_generate_photo_request(user_id, mission_id)
        client.logger.info(f"送出繪本任務 {mission_id}")

# --------------------- Helper Functions ---------------------
def extract_attachment_info(attachment_url: str) -> Optional[Dict[str, str]]:
    """Extracts attachment ID, filename, and full URL from a Discord attachment URL."""

    pattern = r'https://cdn\.discordapp\.com/attachments/(\d+)/(\d+)/([^?]+)(\?.*)?'
    match = re.match(pattern, attachment_url)
    if not match:
        return None

    channel_id, attachment_id, filename, query_params = match.groups()
    return {
        "id": attachment_id,
        "filename": filename,
        "url": attachment_url
    }

async def build_photo_mission_embed(mission_info=None, baby_info=None, book_info=None, step_index=0):
    if baby_info is None:
        author = "恭喜寶寶出生！"
    else:
        try:
            baby_info['birthdate'] = baby_info.get('birthdate') or baby_info.get('birthday')
            birthday = datetime.strptime(baby_info['birthdate'], '%Y-%m-%d').date()
            diff = relativedelta(date.today(), birthday)
            year = diff.years
            months = diff.months
            days = diff.days
            if year > 0:
                author = f"🧸今天{baby_info['baby_name']} 出生滿 {year} 年 {months} 個月 {days} 天"
            elif months > 0:
                author = f"🧸今天{baby_info['baby_name']} 出生滿 {months} 個月 {days} 天"
            else:
                author = f"🧸今天{baby_info['baby_name']} 出生滿 {days} 天"
        except Exception as e:
            print(f"Error parsing birthday: {e}")
            author = "恭喜寶寶出生！"

    # Check if mission_id exists in mission_instruction.json
    instruction_data = get_mission_instruction(mission_info['mission_id'], step_index=step_index, instruction_type='upload')
    if instruction_data:
        # Use custom instruction from mission_instruction.json
        title = f"📸 **{instruction_data['title']}**"
        desc = instruction_data.get('description', '')
    else:
        # Use original embed from API data
        title = f"📸**{mission_info['photo_mission']}**"
        desc = f"\n📎 點左下 **[+]** 上傳照片\n\n"

    if int(mission_info['mission_id']) < 100: # infancix_mission
        video_url = mission_info.get('mission_video_contents', '').strip()
        image_url = mission_info.get('mission_image_contents', '').strip()
        instruction = ""
        if video_url and image_url:
            instruction = f"▶️ [教學影片]({video_url})\u2003\u2003📂 [圖文懶人包]({image_url})\n"
        elif video_url:
            instruction = f"▶️ [教學影片]({video_url})\n"

        desc += (
            f"> **🧠 {mission_info['mission_title']}**\n"
            f"> {mission_info['mission_instruction']}\n"
            f"> \n"
            f"> {instruction} \n"
        )

    if int(mission_info['mission_id']) == 1003 and not instruction_data:
        desc += f"💡 也可以上傳寶寶與其他重要照顧者的合照喔！\n"

    embed = discord.Embed(
        title=title,
        description=desc,
        color=0xeeb2da
    )

    if step_index == 0:
        embed.set_author(name=author)

    if book_info and book_info.get('lang_version', 'zh') == 'en':
        if book_info.get('book_id') in [1, 3]:
            demo_baby_id = 2024000002
            demo_url = f"https://infancixbaby120.com/discord_image/{demo_baby_id}/{mission_info['mission_id']}.jpg"
            embed.set_image(url=demo_url)
        else:
            default_instruction_url = "https://infancixbaby120.com/discord_assets/photo_mission_instruction.png"
            embed.set_image(url=default_instruction_url)
    else:
        # zh
        demo_baby_id = 2024000001
        demo_url = f"https://infancixbaby120.com/discord_image/{demo_baby_id}/{mission_info['mission_id']}.jpg"
        embed.set_image(url=demo_url)

    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="若有任何問題，隨時聯絡社群客服「阿福」。"
    )

    files = []
    if step_index == 0 and '週' in mission_info.get('mission_milestone'):
        for url in mission_info['mission_image_contents'].split(','):
            if url.strip():
                file = await create_file_from_url(url.strip())
                if file:
                    files.append(file)

    return embed, files

def get_add_on_photo_embed(mission_info, student_info) -> discord.Embed:
    description = (
        "恭喜完成這個月的成長繪本 🎉\n"
        "想要放更多照片、留下更完整的回憶嗎？\n\n"
        "> **商品內容**\n"
        "> 📄 加購照片紀念頁（1 頁）\n"
        "> 🖼️ 可放 4 張照片\n> \n"
        "> **價格**\n"
        "> 社團金幣🪙 200元\n"
    )
    embed = discord.Embed(
        title="📸 加購繪本單頁",
        description=description,
        color=0xeeb2da,
    )
    demo_baby_id = 2024000001
    demo_url = f"https://infancixbaby120.com/discord_image/{demo_baby_id}/{mission_info['mission_id']}.jpg"
    embed.set_image(url=demo_url)
    embed.set_footer(
        text=f"您的金幣餘額： 🪙{student_info.get('gold', 0)}　|　若有任何問題，請聯絡客服「阿福」。"
    )
    return embed

def get_aside_text_embed():
    embed = discord.Embed(
        title="✏️ 寫下該照片的回憶",
        description="請於對話框輸入文字\n範例：第一次幫你按摩，就解決了你的便秘。\n\n(中文版限定30個字，英文版建議20個字以內，且最多兩行)",
        color=0xeeb2da,
    )
    return embed

def get_embed_from_instruction(mission_info, instruction_data):
    title_text = instruction_data.get('question', 'Question')
    embed = discord.Embed(
        title=title_text,
        description=instruction_data.get('description', ''),
        color=0xeeb2da,
    )
    embed.set_author(name=f"成長繪本｜{mission_info['mission_title']}")
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_confirmation_embed(mission_id, mission_result):
    """
    Create confirmation embed for missions with aside_text.
    Handles both single and multiple aside_texts with their corresponding questions.
    """
    aside_texts = mission_result.get('aside_texts', [])
    # Count non-empty aside_texts
    valid_aside_texts = [t for t in aside_texts if t]
    has_multiple = len(valid_aside_texts) > 1

    # Build description with multiple aside_texts
    description_parts = []

    for i, aside_text in enumerate(aside_texts):
        if aside_text:  # Skip None or empty aside_texts
            # Try to get question from mission_instruction.json
            instruction_data = get_mission_instruction(mission_id, step_index=i, instruction_type='question')

            if instruction_data and instruction_data.get('question'):
                question_title = instruction_data['question']
            else:
                # Default label if no question available
                # Only show number if there are multiple aside_texts
                if has_multiple:
                    question_title = f"回憶故事({i + 1})"
                else:
                    question_title = "回憶故事"

            # Format: Question followed by quoted answer
            description_parts.append(f"**{question_title}**")
            quoted_content = '\n'.join(f'> {line}' for line in aside_text.splitlines())
            description_parts.append(quoted_content)
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

def get_waiting_embed() -> discord.Embed:
    embed = discord.Embed(
        title="繪本製作中，請稍等30秒",
        color=0xeeb2da
    )
    embed.set_image(url=f"https://infancixbaby120.com/discord_assets/loading1.gif")
    return embed
