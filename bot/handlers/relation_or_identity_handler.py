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
    load_conversations_records,
    save_conversations_record,
    delete_conversations_record
)
from bot.utils.decorator import exception_handler
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.config import config

async def handle_relation_identity_mission_start(client, user_id, mission_id, send_weekly_report=1):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    baby = await client.api_utils.get_baby_profile(user_id)

    # Delete conversation cache
    delete_mission_record(user_id)
    delete_conversations_record(user_id, mission_id)

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

    embed, files = await build_photo_mission_embed(mission, baby)
    if send_weekly_report and files:
        await user.send(files=files)
    await user.send(embed=embed)
    return

@exception_handler(user_friendly_message="登記失敗，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
async def process_relation_identity_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    request_info = await prepare_api_request(client, message, student_mission_info)
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
    mission_result = client.openai_utils.process_relationship_validation(mission_result)
    save_mission_record(user_id, mission_id, mission_result)

    if mission_result.get('is_ready'):
        success = await submit_image_data(client, message, student_mission_info, mission_result)
        if success:
            await client.api_utils.submit_generate_photo_request(user_id, mission_id)
            client.logger.info(f"送出繪本任務 {mission_id}")
            return
    elif mission_result.get("relation_or_identity", None) is None:
        if int(mission_id) in config.relation_mission:
            embed = get_relation_embed(student_mission_info)
        else:
            embed = get_identity_embed(student_mission_info)
        await message.channel.send(embed=embed)
    else:
        await message.channel.send(mission_result['message'])
        save_conversations_record(user_id, mission_id, 'assistant', mission_result['message'])
    return

async def prepare_api_request(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    saved_result = get_mission_record(user_id, mission_id)
    if message.attachments:        
        attachment = extract_attachment_info(message.attachments[0].url)
        saved_result['attachment'] = attachment
        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_upload',
            'direct_response': saved_result
        }
    else:
        user_message = message.content

    # Build full context for AI prediction
    context_parts = []
    if saved_result.get('attachment') and saved_result['attachment'].get('url'):
        context_parts.append(f"Current attachments detail: {saved_result['attachment']}")
    context = "\n".join(context_parts)

    return {
        'needs_ai_prediction': True,
        'direct_action': None,
        'context': context,
        'user_message': user_message
    }

# --------------------- Event Handlers ---------------------
async def submit_image_data(client, message, student_mission_info, mission_result):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # Process the photo attachment
    if isinstance(mission_result.get('attachment'), list):
        attachment_obj = mission_result.get('attachment')
        aside_text = None
    else:
        attachment_obj = [mission_result.get('attachment')]
        aside_text = mission_result.get('relation_or_identity', None)

    update_status = await client.api_utils.update_mission_image_content(user_id, mission_id, attachment_obj, aside_text=aside_text)
    return update_status

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

async def build_photo_mission_embed(mission_info=None, baby_info=None):
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

    elif int(mission_info['mission_id']) == 1003:
        desc += f"💡 也可以上傳寶寶與其他重要照顧者的合照喔！\n"

    embed = discord.Embed(
        title=title,
        description=desc,
        color=0xeeb2da
    )
    embed.set_author(name=author)
    embed.set_image(url="https://infancixbaby120.com/discord_assets/photo_mission_instruction.png")
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )

    files = []
    if '成長週報' in mission_info['mission_type']:
        for url in mission_info['mission_image_contents'].split(','):
            if url.strip():
                file = await create_file_from_url(url.strip())
                if file:
                    files.append(file)

    return embed, files

def get_relation_embed(mission_info):
    embed = discord.Embed(
        title="📝 照片裡的人和寶寶關係是?",
        description="例如：媽媽、爸爸、阿公、阿嬤、兄弟姊妹⋯⋯",
        color=0xeeb2da,
    )
    embed.set_author(name=f"成長繪本｜{mission_info['mission_title']}")
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_identity_embed(mission_info):
    embed = discord.Embed(
        title="📝 這張照片裡的人是誰呢？",
        description="例如：媽媽、阿公、阿嬤、兄弟姊妹、寵物⋯⋯\n(也可以輸入名字喔！)",
        color=0xeeb2da,
    )
    embed.set_author(name=f"成長繪本｜{mission_info['mission_title']}")
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed
