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

async def handle_audio_mission_start(client, user_id, mission_id, send_weekly_report=1):
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

    embed, files = await build_audio_mission_embed(mission, baby)
    if send_weekly_report and files:
        await user.send(files=files)

    view = TaskSelectView(client, "skip_mission", mission_id, mission_result=student_mission_info)
    view.message = await user.send(embed=embed, view=view)
    save_task_entry_record(user_id, str(view.message.id), "skip_mission", mission_id, result=student_mission_info)
    return

@exception_handler(user_friendly_message="錄音檔上傳失敗了，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
async def process_audio_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    request_info = prepare_api_request(client, message, student_mission_info)
    print(f"Request info: {request_info}")

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

    # Validate mission result
    # Get required attachment count
    required_count = config.get_required_attachment_count(mission_id, 'audio')

    # Check if we have enough attachments
    attachment = mission_result.get('attachment')
    if required_count > 1:
        # Multiple attachments required
        current_count = len(attachment) if isinstance(attachment, list) else (1 if attachment else 0)
        has_enough_attachments = current_count >= required_count

        if has_enough_attachments:
            mission_result['is_ready'] = True
        else:
            mission_result['is_ready'] = False
            mission_result['message'] = f"目前已收到 {current_count} 個錄音檔，還需要 {required_count - current_count} 個錄音檔喔！"
    else:
        # Single attachment required (original behavior)
        if attachment and (attachment.get('url') if isinstance(attachment, dict) else True):
            mission_result['is_ready'] = True
        else:
            mission_result['is_ready'] = False
            mission_result['message'] = "請上傳錄音檔喔！"

    save_mission_record(user_id, mission_id, mission_result)

    if mission_result.get('is_ready'):
        embed = get_waiting_embed()
        await message.channel.send(embed=embed)
        await submit_audio_data(client, message, student_mission_info, mission_result)
    else:
        await message.channel.send(mission_result['message'])

    return

def prepare_api_request(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    saved_result = get_mission_record(user_id, mission_id) or {}

    # Get required attachment count for this mission
    required_count = config.get_required_attachment_count(mission_id, 'audio')

    if message.attachments:
        # Handle multiple audios requirement
        if required_count > 1:
            if not saved_result.get('attachment'):
                saved_result['attachment'] = []
            elif not isinstance(saved_result['attachment'], list):
                saved_result['attachment'] = [saved_result['attachment']]

            # Add new attachments
            for att in message.attachments:
                if len(saved_result['attachment']) >= required_count:
                    break
                attachment = extract_attachment_info(att.url)
                saved_result['attachment'].append(attachment)

            current_count = len(saved_result['attachment'])
            if current_count >= required_count:
                saved_result['message'] = f"已收到 {current_count} 個錄音檔"
            else:
                saved_result['message'] = f"已收到 {current_count} 個錄音檔，還需要 {required_count - current_count} 個錄音檔"
        else:
            # Single audio requirement (original behavior)
            attachment = extract_attachment_info(message.attachments[0].url)
            saved_result['attachment'] = attachment
            saved_result['message'] = "已收到您的錄音檔"

        return {
            'needs_ai_prediction': False,
            'direct_action': 'audio_upload',
            'direct_response': saved_result
        }
    else:
        user_message = message.content

    # Build full context for AI prediction
    context = ""
    if saved_result.get('attachment'):
        context_parts = []
        if isinstance(saved_result['attachment'], list):
            context_parts.append(f"Current attachments: {len(saved_result['attachment'])} audios collected")
        context_parts.append(f"Attachments detail: {saved_result['attachment']}")
        context = "\n".join(context_parts)
    else:
        return ""

    return {
        'needs_ai_prediction': True,
        'direct_action': None,
        'context': context,
        'user_message': user_message
    }

# --------------------- Event Handlers ---------------------
async def submit_audio_data(client, message, student_mission_info, mission_result):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # Process the audio attachment
    if isinstance(mission_result.get('attachment'), list):
        attachment_obj = mission_result.get('attachment')
    else:
        attachment_obj = [mission_result.get('attachment')]

    update_status = await client.api_utils.update_mission_image_content(
        user_id, mission_id, attachment_obj, aside_text=mission_result.get('aside_text'), content=mission_result.get('content')
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
        "url": attachment_url,
        "aside_text": None
    }

async def build_audio_mission_embed(mission_info=None, baby_info=None, photo_mission=True):
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
    instruction_data = get_mission_instruction(mission_info['mission_id'], step_index=0, instruction_type='upload')

    if instruction_data:
        # Use custom instruction from mission_instruction.json
        title = f"🎙️ **{instruction_data['title']}**"
        desc = instruction_data.get('description', '')
    else:
        # Use original embed from API data
        title = f"🎙️**{mission_info['mission_title']}**"
        desc = "長按對話框右側的🎙️即可錄音。\n"

    if mission_info.get('milestone_domain', None) in ['照護', '營養', '早教', '睡眠', '健康', '產後']:
        video_url = mission_info.get('milestone_video_contents', '').strip()
        image_url = mission_info.get('milestone_image_contents', '').strip()
        instruction = ""
        if video_url and image_url:
            instruction = f"▶️ [教學影片]({video_url})\u2003\u2003📂 [圖文懶人包]({image_url})\n"
        elif video_url:
            instruction = f"▶️ [教學影片]({video_url})\n"
        elif image_url:
            instruction = f"📂 [圖文懶人包]({image_url})\n"

        desc += (
            f"> **🧠 {mission_info['milestone_title']}**\n"
            f"> {mission_info['mission_instruction']}\n"
            f"> \n"
            f"> {instruction} \n"
        )

    embed = discord.Embed(
        title=title,
        description=desc,
        color=0xeeb2da
    )
    embed.set_author(name=author)
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="若有任何問題，隨時聯絡社群客服「阿福」。"
    )

    files = []
    if '週' in mission_info.get('development_week'):
        for url in mission_info['milestone_image_contents'].split(','):
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
