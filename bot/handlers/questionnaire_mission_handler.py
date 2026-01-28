import traceback
import discord
import os
import re
import json
from types import SimpleNamespace
from typing import Dict, Optional, List
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from bot.views.task_select_view import TaskSelectView
from bot.views.questionnaire import QuestionnaireView
from bot.utils.message_tracker import (
    load_questionnaire_records,
    save_questionnaire_record,
    delete_questionnaire_record,
    save_task_entry_record,
    get_mission_record,
    save_mission_record,
    delete_mission_record,
)
from bot.handlers.utils import get_user_id
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.utils.mission_instruction_utils import get_mission_instruction, get_current_mission_step, get_mission_total_steps
from bot.config import config

async def send_mission_step(client, user, mission_id, baby, step_data, student_mission_info, send_weekly_report=True):
    """
    Send a mission step to the user based on step type.

    Args:
        client: Discord client
        user: Discord user object
        step_data: Current step data from mission_questionnaire.json
        mission_id: Mission ID
        student_mission_info: Student mission status info
        send_weekly_report: Whether to send weekly report files (default: True)

    Returns:
        Discord message object or None
    """
    step_type = step_data.get('type')
    current_step = student_mission_info.get('current_step', 1)

    # Handle different step types
    if step_type in ['multiple_choice', 'single_choice']:
        # Multiple/Single choice - use QuestionnaireView
        current_round = 0 # Simplified: one question per view  
        questionnaire = client.mission_questionnaire[str(mission_id)][current_round]
        embed, files = await build_questionnaire_mission_embed(questionnaire, student_mission_info, baby, current_step)
        if send_weekly_report and files:
            await user.send(files=files)
        view = QuestionnaireView(client, mission_id, student_mission_info)
        view.message = await user.send(embed=embed, view=view)

    elif step_type == 'photo':
        # Photo - show upload instruction
        embed = await build_photo_mission_embed(step_data, student_mission_info)
        await user.send(embed=embed)

    saved_result = get_mission_record(str(user.id), mission_id)
    saved_result['previous_question'] = embed.description
    save_mission_record(str(user.id), mission_id, saved_result)

    return None

async def handle_questionnaire_mission_start(client, user_id, mission_id, send_weekly_report=1):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    baby = await client.api_utils.get_baby_profile(user_id)

    # Delete conversation cache
    delete_questionnaire_record(user_id, mission_id)
    delete_mission_record(user_id)
    if user_id in client.photo_mission_replace_index:
        del client.photo_mission_replace_index[user_id]

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': 1
    }
    # Get current step from mission_questionnaire.json
    current_step_data = get_current_mission_step(mission_id, student_mission_info)

    if not current_step_data:
        client.logger.warning(f"No current step found for mission {mission_id}")
        return
    else:
        student_mission_info['total_stpes'] = min(4, len(current_step_data) + 1)

    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    # Prepare next mission
    book_id = mission.get('book_id', 0)
    incomplete_missions = await client.api_utils.get_student_incomplete_photo_mission(user_id, book_id)
    next_mission_id = None
    for m in incomplete_missions:
        if m['mission_id'] != mission_id:
            next_mission_id = m['mission_id']
            student_mission_info['next_mission_id'] = next_mission_id
            break

    # Send the current step to user
    await send_mission_step(
        client, user, mission_id,
        baby, current_step_data, student_mission_info,
        send_weekly_report=bool(send_weekly_report)
    )

    return

async def handle_questionnaire_round(client, message, student_mission_info, current_round=0, restart=False):
    user_id = get_user_id(message)
    mission_id = int(student_mission_info['mission_id'])
    student_mission_info['current_step'] = 2
    await client.api_utils.update_student_mission_status(**student_mission_info)

    if current_round == 0:
        delete_questionnaire_record(user_id, mission_id)

    # Start questionnaire
    total_rounds = len(client.mission_questionnaire.get(str(mission_id), []))
    if total_rounds == 0 or current_round >= total_rounds:
        raise ValueError("題目設定錯誤，請洽社群客服「阿福 <@1272828469469904937>」協助。")
        await message.channel.send("題目設定錯誤，請洽社群客服「阿福 <@1272828469469904937>」協助。")
        return

    questionnaire = client.mission_questionnaire[str(mission_id)][current_round]
    view = QuestionnaireView(client, mission_id, student_mission_info)
    if current_round > 0 or restart:
        embed = get_questionnaire_embed(questionnaire)
        view.message = await message.channel.send(embed=embed, view=view)
    else:
        view.message = await message.channel.send(view=view)
    return

async def handle_questionnaire_next_mission(client, message, student_mission_info, saved_result):
    user_id = get_user_id(message)
    mission_id = student_mission_info['mission_id']

    # Check if mission is ready to finalize using the helper function
    if check_mission_ready(mission_id, saved_result):
        await submit_questionnaire_mission(client, user_id, mission_id, saved_result)
    else:
        # Get next step
        next_step_data = get_current_mission_step(mission_id, student_mission_info)
        mission = await client.api_utils.get_mission_info(mission_id)
        baby = await client.api_utils.get_baby_profile(user_id)
        user = message.author
        await send_mission_step(
            client, user, mission_id,
            baby, next_step_data, student_mission_info,
            send_weekly_report=False
        )

    return

async def process_questionnaire_mission_filling(client, message, student_mission_info):
    """
    Handle text input and photo uploads for questionnaire missions (multi-step support)
    """
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    request_info = prepare_api_request(client, message, student_mission_info)
    print(f"Request info: {request_info}")

    if request_info.get('direct_action') == 'error':
        await message.channel.send(request_info.get('context', '發生錯誤，請稍後再試。'))
        return

    elif request_info['needs_ai_prediction']:
        async with message.channel.typing():
            prompt_path = config.get_prompt_file(mission_id)
            conversations = [{'role': 'user', 'message': request_info['context']}] if request_info['context'] else None
            mission_result = client.openai_utils.process_user_message(
                prompt_path,
                request_info['user_message'],
                conversations=conversations,
                additional_context=request_info.get('current_question')
            )
            client.logger.info(f"Assistant response: {mission_result}")
    else:
        # Skip AI prediction, use direct response
        mission_result = request_info.get('direct_response', {})

    if mission_result is None:
        await message.channel.send(request_info.get('context', '發生錯誤，請稍後再試。'))
        return

    # Save updated mission result
    saved_result = get_mission_record(user_id, mission_id) or {}
    saved_result['message'] = mission_result['message']

    # Handle aside_text similar to attachments (support multiple text inputs)
    if 'aside_text' in mission_result and mission_result['aside_text']:
        required_text_count = config.get_required_aside_text_count(mission_id, 'questionnaire')

        if required_text_count > 1:
            # Multiple aside_texts required
            if not saved_result.get('aside_texts'):
                saved_result['aside_texts'] = []
            elif not isinstance(saved_result['aside_texts'], list):
                saved_result['aside_texts'] = [saved_result['aside_texts']]

            # Add new aside_text
            if len(saved_result['aside_texts']) < required_text_count:
                saved_result['aside_texts'].append(mission_result['aside_text'])
            else:
                saved_result['aside_texts'][request_info.get('question_index', 0)] = mission_result['aside_text']
        else:
            # Single aside_text requirement
            saved_result['aside_texts'] = mission_result['aside_text']

    # Update with remaining fields from mission_result
    save_mission_record(user_id, mission_id, saved_result)

    # Check if mission is ready to finalize using the helper function
    if check_mission_ready(mission_id, saved_result):
        mission_result['is_ready'] = True

    # Move to next step
    student_mission_info['current_step'] += 1
    await client.api_utils.update_student_mission_status(**student_mission_info)
    # Get next step
    next_step = get_current_mission_step(mission_id, student_mission_info)

    if mission_result.get('is_ready'):
        await submit_questionnaire_mission(client, user_id, mission_id, saved_result)
    elif next_step:
        await handle_questionnaire_next_mission(client, message, student_mission_info, saved_result)
    else:
        await message.channel.send(mission_result['message'])

    return

def prepare_api_request(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    saved_result = get_mission_record(user_id, mission_id) or {}

    required_count = config.get_required_attachment_count(mission_id, 'photo')
    if user_id in client.photo_mission_replace_index and message.attachments:
        photo_index = client.photo_mission_replace_index[user_id]
        attachments_list = saved_result.get('attachment', []) if isinstance(saved_result.get('attachment'), list) else [saved_result.get('attachment')] if saved_result.get('attachment') else []

        if not attachments_list or photo_index-1 >= len(attachments_list):
            return {
                'needs_ai_prediction': False,
                'direct_action': 'error',
                'context': "無法替換照片，請重新上傳照片或是尋求客服協助喔！"
            }

        replace_attachment = extract_attachment_info(message.attachments[0].url)
        attachments_list[photo_index-1] = replace_attachment
        saved_result['attachment'] = attachments_list if required_count > 1 else attachments_list[0]
        saved_result['message'] = "已收到您的照片"
        saved_result['is_ready'] = True
        save_mission_record(user_id, mission_id, saved_result)

        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_replacement',
            'direct_response': saved_result
        }

    elif message.attachments:
        # Handle multiple photos requirement
        if required_count > 1:
            if not saved_result.get('attachments'):
                saved_result['attachments'] = []
            elif not isinstance(saved_result['attachments'], list):
                saved_result['attachments'] = [saved_result['attachments']]

            # Add new attachments
            for att in message.attachments:
                if len(saved_result['attachments']) >= required_count:
                    break
                attachment = extract_attachment_info(att.url)
                saved_result['attachments'].append(attachment)
        else:
            # Single photo requirement (original behavior)
            attachment = extract_attachment_info(message.attachments[0].url)
            saved_result['attachments'] = attachment
            saved_result['message'] = "已收到您的照片"

        # Save mission result
        save_mission_record(user_id, mission_id, saved_result)

        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_upload',
            'direct_response': saved_result,
            'message': '已收到照片'
        }

    else:
        user_message = message.content
        current_step_index = student_mission_info.get('current_step', 1)

        temp_info = {'current_step': current_step_index}
        current_step_data = get_current_mission_step(mission_id, temp_info)

        current_question, question_index = None, None
        # Add current question to context (IMPORTANT for validation)
        if current_step_data and current_step_data.get('question'):
            current_question = f"Question: {current_step_data.get('question')}"
            question_index = current_step_data.get('index', 0)

        # Build context for AI prediction
        # For questionnaire text input validation, we don't need any context
        # Each question should be validated independently based only on the question and answer
        context = ""

        return {
            'needs_ai_prediction': True,
            'direct_action': None,
            'context': context,
            'user_message': user_message,
            'current_question': current_question,
            'question_index': question_index
        }

# --------------------- Helper Functions ---------------------
async def submit_questionnaire_mission(client, user_id, mission_id, saved_result):
    """
    Submit questionnaire mission to API and trigger book generation.

    Handles formatting of aside_texts and attachments before submission.

    Args:
        client: Discord client
        user_id: User ID (str)
        mission_id: Mission ID (int)
        saved_result: Dictionary containing 'aside_texts' and 'attachments'

    Returns:
        bool: True if submission successful, False otherwise
    """
    # Format aside_texts
    if not saved_result.get('aside_texts'):
        aside_texts = None
    elif isinstance(saved_result['aside_texts'], list):
        aside_texts = "|".join(saved_result['aside_texts'])
    else:
        aside_texts = saved_result['aside_texts'] if saved_result['aside_texts'] != '跳過' else None

    # Format attachments
    if not saved_result.get('attachments'):
        attachments = None
    elif isinstance(saved_result['attachments'], list):
        attachments = saved_result['attachments']
    else:
        attachments = [saved_result['attachments']]

    # Update mission content
    success = await client.api_utils.update_mission_image_content(
        user_id,
        mission_id,
        discord_attachments=attachments,
        aside_text=aside_texts if aside_texts else None
    )

    if success:
        client.logger.info(f"✅ 已更新任務內容，使用者 {user_id} 任務 {mission_id}")
        # Submit for book generation
        await client.api_utils.submit_generate_photo_request(user_id, mission_id)
        client.logger.info(f"送出繪本任務 {mission_id}")
        return True
    else:
        client.logger.error(f"❌ 更新任務內容失敗，使用者 {user_id} 任務 {mission_id}")
        return False

def check_mission_ready(mission_id, mission_result):
    """
    Check if questionnaire mission is ready to finalize.

    Validates that both aside_text and attachments meet the required counts
    for the mission. Handles both single values and lists.

    Args:
        mission_id: Mission ID (int or str)
        mission_result: Dictionary containing 'attachment(s)' and 'aside_text(s)' fields

    Returns:
        bool: True if mission has enough aside_text and attachments, False otherwise
    """
    # Get required counts from config
    required_attachment_count = config.get_required_attachment_count(mission_id, 'photo')
    required_aside_text_count = config.get_required_aside_text_count(mission_id)

    # Check attachments - support both 'attachment' and 'attachments' keys
    attachment = mission_result.get('attachments')
    if required_attachment_count > 0:
        if isinstance(attachment, list):
            current_attachment_count = len([a for a in attachment if a and a.get('url')])
        elif attachment and attachment.get('url'):
            current_attachment_count = 1
        else:
            current_attachment_count = 0

        if current_attachment_count < required_attachment_count:
            return False

    # Check aside_text - support both 'aside_text' and 'aside_texts' keys
    aside_text = mission_result.get('aside_texts') or mission_result.get('aside_text')
    if required_aside_text_count > 0:
        if isinstance(aside_text, list):
            # Count valid aside_text entries (not empty, not "跳過", and not placeholder)
            current_aside_text_count = len([t for t in aside_text if t and t != '跳過' and t != '[使用者選擇跳過]'])
        elif aside_text and aside_text != '跳過' and aside_text != '[使用者選擇跳過]':
            current_aside_text_count = 1
        else:
            current_aside_text_count = 0

        if current_aside_text_count < required_aside_text_count:
            return False

    return True

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

async def build_questionnaire_mission_embed(questionnaire_data, mission_info, baby_info=None, current_step=1):
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

    embed = discord.Embed(
        title=f"**{questionnaire_data['question']}**",
        description=mission_info['mission_instruction'] if mission_info.get('mission_instruction') else "\n💡回答請點選下方按鈕\n",
        color=0xeeb2da
    )
    if current_step <= 1:
        embed.set_author(name=author)
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="若有任何問題，隨時聯絡社群客服「阿福」。"
    )

    files = []
    if '週' in mission_info.get('mission_milestone'):
        for url in mission_info['mission_image_contents'].split(','):
            if url.strip():
                file = await create_file_from_url(url.strip())
                if file:
                    files.append(file)

    return embed, files

async def build_short_answer_mission_embed(answer_data, mission_info, baby_info=None, current_step=1):
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

    # Get title and description
    title = answer_data.get('title', answer_data.get('question', ''))
    description = f"**{answer_data.get('question', '')}**\n{answer_data.get('description', '')}"

    embed = discord.Embed(
        title=f"📝 **{title}**",
        description=description,
        color=0xeeb2da
    )
    if current_step <= 1:
        embed.set_author(name=author)

    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="若有任何問題，隨時聯絡社群客服「阿福」。"
    )

    files = []
    if '週' in mission_info.get('mission_milestone', ''):
        for url in mission_info.get('mission_image_contents', '').split(','):
            if url.strip():
                file = await create_file_from_url(url.strip())
                if file:
                    files.append(file)

    return embed, files

async def build_photo_mission_embed(step_data, mission_info, baby_info=None):
    # Get title and description
    title = step_data.get('title', step_data.get('question', ''))
    description = step_data.get('description', '')

    embed = discord.Embed(
        title=f"📝 **{title}**",
        description=description,
        color=0xeeb2da
    )
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="若有任何問題，隨時聯絡社群客服「阿福」。"
    )

    return embed

def get_questionnaire_embed(questionnaire):
    embed = discord.Embed(
        title=f"**{questionnaire['question']}**",
        description=f"\n💡回答請點選下方按鈕\n",
        color=0xeeb2da
    )
    return embed
