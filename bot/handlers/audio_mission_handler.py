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
    await client.api_utils.add_to_testing_whiltlist(user_id)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    embed, files = await build_audio_mission_embed(mission, baby)
    if send_weekly_report and files:
        await user.send(files=files)
    await user.send(embed=embed)
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
    if mission_result.get('attachment') and mission_result['attachment'].get('url'):
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

    if message.attachments:
        saved_result = get_mission_record(user_id, mission_id)
        attachment = extract_attachment_info(message.attachments[0].url)
        saved_result['attachment'] = attachment
        return {
            'needs_ai_prediction': False,
            'direct_action': 'audio_upload',
            'direct_response': saved_result
        }
    else:
        user_message = message.content

    # Build full context for AI prediction
    context = ""
    saved_result = get_mission_record(user_id, mission_id)
    if saved_result.get('attachment'):
        context_parts = []
        context_parts.append(f"Current attachments detail: {saved_result['attachment']}")
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

async def build_audio_mission_embed(mission_info=None, baby_info=None):
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

    title = f"🎙️**{mission_info['photo_mission']}**"
    desc = f"此任務有兩種方式，爸媽可擇一完成 👇\n"
    if mission_info['mission_id'] == 14:
        desc += (
            f"① 哄睡話語 — 可直接用 Discord 錄音功能。\n"
            f"💡 長按對話框右側的🎙️即可錄音。\n\n"
            f"② 噓噓聲 — Discord 錄不到噓噓聲，請用手機錄音後再上傳檔案。\n"
            f"💡 不確定怎麼\"噓\"？可點下方影片查看教學。\n\n"
        )

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
    embed.set_author(name=author)
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="若有任何問題，隨時聯絡社群客服「阿福」。"
    )

    files = []
    if '成長週報' in mission_info['mission_type']:
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
