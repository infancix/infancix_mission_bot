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

async def handle_video_mission_start(client, user_id, mission_id, send_weekly_report=1):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    baby = await client.api_utils.get_baby_profile(user_id)

    # Delete conversion cache
    delete_mission_record(user_id)
    if user_id in client.photo_mission_replace_index:
        del client.photo_mission_replace_index[user_id]

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': 1
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

    embed, files = await build_video_mission_embed(mission, baby)
    if send_weekly_report and files:
        await user.send(files=files)

    view = TaskSelectView(client, "skip_mission", mission_id, mission_result=student_mission_info)
    view.message = await user.send(embed=embed, view=view)
    save_task_entry_record(user_id, str(view.message.id), "skip_mission", mission_id, result=student_mission_info)
    return

@exception_handler(user_friendly_message="影片上傳失敗了，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
async def process_video_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    request_info = await process_user_input(client, message, student_mission_info)
    print(f"Request info: {request_info}")

    if request_info.get('direct_action') == 'error':
        await message.channel.send(request_info.get('context', '發生錯誤，請稍後再試。'))
        return

    # Get mission_result from direct_response
    mission_result = request_info.get('direct_response', {})

    # Determine next step
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

    elif next_step_type == 'video':
        # Next step is to request video upload
        mission_result['current_video_index'] = step_index
        mission_result['show_next_video_instruction'] = True

    # Save the mission state
    save_mission_record(user_id, mission_id, mission_result)

    # Send response or submit mission
    if mission_result.get('is_ready'):
        await submit_video_mission(client, message, student_mission_info, mission_result)
    else:
        # Send next step message to user
        await send_mission_step(client, message, mission_id, student_mission_info, mission_result)

    return

# --------------------- Input Processing Functions ---------------------

def handle_video_upload(mission_id, saved_result, message, required_video_count, required_aside_text_count):
    """
    Handle video upload from the user.
    Returns updated saved_result with the new video.
    """
    # Initialize video storage if needed
    if not saved_result.get('attachments'):
        saved_result['attachments'] = []
    elif not isinstance(saved_result['attachments'], list):
        saved_result['attachments'] = [saved_result['attachments']]

    # Add new videos
    for att in message.attachments:
        if len(saved_result['attachments']) >= required_video_count:
            break
        attachment = extract_attachment_info(att.url)
        saved_result['attachments'].append(attachment)

    current_video_count = len(saved_result['attachments'])

    # Update message based on progress
    if current_video_count >= required_video_count:
        saved_result['message'] = f"已收到 {current_video_count} 個影片"
    else:
        saved_result['message'] = f"已收到 {current_video_count} 個影片，還需要 {required_video_count - current_video_count} 個影片"

    return {
        'needs_ai_prediction': False,
        'direct_action': 'video_upload',
        'direct_response': saved_result
    }

async def handle_text_input(client, mission_id, saved_result, message):
    """
    Handle text input from the user for aside_text questions.
    Uses AI to validate the response.
    """
    prompt_path = config.get_prompt_file(mission_id)
    user_message = message.content

    # Build context
    context = ""
    if saved_result.get('attachments'):
        context_parts = []
        if isinstance(saved_result['attachments'], list):
            context_parts.append(f"Current attachments: {len(saved_result['attachments'])} videos collected")
        context_parts.append(f"Attachments detail: {saved_result['attachments']}")
        context = "\n".join(context_parts)

    # Get current question
    current_question_index = saved_result.get('current_question_index', 0)
    instruction_data = get_mission_instruction(mission_id, step_index=current_question_index, instruction_type='question')

    if instruction_data and instruction_data.get('question'):
        context += f"\nCurrent question: {instruction_data['question']}"

    # Call AI to process the response
    async with message.channel.typing():
        conversations = [{'role': 'user', 'message': context}] if context else None
        mission_result = client.openai_utils.process_user_message(
            prompt_path,
            user_message,
            conversations=conversations
        )
        client.logger.info(f"AI response: {mission_result}")

    # Update saved_result with AI response
    if mission_result.get('aside_text'):
        # Initialize aside_texts list if needed
        if not saved_result.get('aside_texts'):
            saved_result['aside_texts'] = []

        # Add the new aside_text
        saved_result['aside_texts'].append(mission_result.get('aside_text'))
        saved_result['message'] = mission_result.get('message', '已記錄您的回答')
    else:
        # AI rejected the answer
        saved_result['message'] = mission_result.get('message', '請提供有效的回答')

    return {
        'needs_ai_prediction': False,
        'direct_action': 'text_input',
        'direct_response': saved_result
    }

async def process_user_input(client, message, student_mission_info):
    """
    Process user input (video or text) and return appropriate response.
    """
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    saved_result = get_mission_record(user_id, mission_id) or {}

    # Get required counts
    required_video_count = config.get_required_attachment_count(mission_id, 'video')
    required_aside_text_count = config.get_required_attachment_count(mission_id, 'aside_text')

    # Handle video upload
    if message.attachments:
        return handle_video_upload(mission_id, saved_result, message, required_video_count, required_aside_text_count)

    # Handle text input
    else:
        return await handle_text_input(client, mission_id, saved_result, message)

def determine_next_step(mission_id, mission_result):
    """
    Determine the next step in the mission flow.
    Only checks video_require_count and aside_text_require_count.

    Returns:
        tuple: (step_type, step_index) where step_type is 'video', 'question', or None
    """
    required_video_count = config.get_required_attachment_count(mission_id, 'video')
    required_aside_text_count = config.get_required_attachment_count(mission_id, 'aside_text')

    # Count current progress
    current_video_count = len(mission_result.get('attachments', []) or [])
    current_aside_text_count = len(mission_result.get('aside_texts', []) or [])

    # Check if we need more videos
    if current_video_count < required_video_count:
        return ('video', current_video_count)

    # Check if we need more aside_texts
    if current_aside_text_count < required_aside_text_count:
        return ('question', current_aside_text_count)

    # All requirements met
    return (None, None)

def check_mission_ready(mission_id, mission_result):
    """
    Check if mission has all required components.
    Returns True if ready to submit.
    """
    required_video_count = config.get_required_attachment_count(mission_id, 'video')
    required_aside_text_count = config.get_required_attachment_count(mission_id, 'aside_text')

    current_video_count = len(mission_result.get('attachments', []) or [])
    current_aside_text_count = len(mission_result.get('aside_texts', []) or [])

    has_all_videos = current_video_count >= required_video_count
    has_all_aside_texts = current_aside_text_count >= required_aside_text_count

    return has_all_videos and has_all_aside_texts

async def send_mission_step(client, message, mission_id, student_mission_info, mission_result):
    """
    Send the appropriate message based on mission state.
    If ready, submits the mission. Otherwise, sends next instruction.
    """
    if mission_result.get('show_next_video_instruction'):
        instruction_data = get_mission_instruction(mission_id, step_index=mission_result.get('current_video_index'), instruction_type='upload')
        if instruction_data:
            embed, _ = await build_video_mission_embed(student_mission_info, baby_info=None, step_index=mission_result.get('current_video_index'))
            message.channel.send(embed=embed)
        else:
            message.channel.send("請上傳下一個影片")
    else:
        # Send next step instruction
        await message.channel.send(mission_result.get('message', '請繼續完成任務'))

async def submit_video_mission(client, message, student_mission_info, mission_result):
    """
    Submit the completed video mission to the API.
    """
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # Get attachments and aside_texts
    attachments = mission_result.get('attachments', [])
    aside_texts = [str(aside_text) if aside_text else '' for aside_text in mission_result.get('aside_texts', [])]
    concated_aside_text = "|".join(aside_texts)

    # Update mission with all data
    update_status = await client.api_utils.update_mission_image_content(
        user_id,
        mission_id,
        discord_attachments=attachments,
        aside_text=concated_aside_text
    )

    if bool(update_status):
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

async def build_video_mission_embed(mission_info=None, baby_info=None, photo_mission=True, step_index=0):
    # Prepare description based on style
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
        title = f"🎬 **{instruction_data['title']}**"
        desc = instruction_data.get('description', '')
    else:
        # Use original embed from API data
        title = f"🎬**{mission_info['photo_mission']}**"
        desc = f"請上傳寶寶的影片 👇\n"
        desc += f"💡 支援的影片格式：MP4、MOV、AVI、MKV、WEBM\n"
        desc += f"💡 影片長度限制：每支影片最長 30 秒\n\n"

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

    embed = discord.Embed(
        title=title,
        description=desc,
        color=0xeeb2da
    )
    if step_index == 0:
        embed.set_author(name=author)
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

def get_waiting_embed():
    embed = discord.Embed(
        title="繪本製作中，請稍等30秒",
        color=0xeeb2da
    )
    embed.set_image(url=f"https://infancixbaby120.com/discord_assets/loading1.gif")
    return embed
