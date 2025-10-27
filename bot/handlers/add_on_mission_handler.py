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

async def handle_add_on_mission_start(client, user_id, mission_id, send_weekly_report=1):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
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

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    embed = get_add_on_photo_embed(mission)
    view = TaskSelectView(client, "check_add_on", mission_id, mission_result=mission)
    view.message = await user.send(embed=embed, view=view)
    save_task_entry_record(user_id, str(view.message.id), "check_add_on", mission_id, result=mission)
    return

def prepare_api_request(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # Replace photo request
    if user_id in client.photo_mission_replace_index and message.attachments:
        photo_index = client.photo_mission_replace_index[user_id]
        saved_result = get_mission_record(user_id, mission_id)
        if not saved_result.get('attachment') or photo_index-1 >= len(saved_result['attachment']):
            return {
                'needs_ai_prediction': False,
                'direct_action': 'error',
                'context': "無法替換照片，請重新上傳照片或是尋求客服協助喔！"
            }

        replace_attachment = extract_attachment_info(message.attachments[0].url)
        saved_result['attachment'][photo_index-1] = replace_attachment
        saved_result['is_ready'] = True
        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_replacement',
            'direct_response': saved_result
        }
    elif message.attachments:
        saved_result = get_mission_record(user_id, mission_id)
        if len(saved_result.get('attachment') or []) + len(message.attachments) > 4:
            return {
                'needs_ai_prediction': False,
                'direct_action': 'error',
                'context': "已達到照片上限4張，請挑選後再上傳喔！"
            }

        if not saved_result.get('attachment'):
            saved_result['attachment'] = []
        for att in message.attachments:
            attachment = extract_attachment_info(att.url)
            saved_result['attachment'].append(attachment)
        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_upload',
            'direct_response': saved_result
        }
    else:
        user_message = message.content

    # Build full context for AI prediction
    context_parts = []
    saved_result = get_mission_record(user_id, mission_id)
    if saved_result.get('attachment'):
        context_parts.append(f"Previous attachments: {len(saved_result['attachment'])} photos collected")
        context_parts.append(f"Attachments detail: {saved_result['attachment']}")
    context = "\n".join(context_parts)

    return {
        'needs_ai_prediction': True,
        'direct_action': None,
        'context': context,
        'user_message': user_message
    }

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
async def process_add_on_photo_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    prompt_path = config.get_prompt_file(mission_id)

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

    # validate mission result
    if len(mission_result.get('attachment', [])) == 4:
        mission_result['is_ready'] = True
    elif len(mission_result.get('attachment', [])) < 4:
        mission_result['is_ready'] = False
        mission_result['message'] = f"目前已收到 {len(mission_result.get('attachment', []))} 張照片，還可以再上傳 {4 - len(mission_result.get('attachment', []))} 張喔！"
    save_mission_record(user_id, mission_id, mission_result)

    # Get enough information to proceed
    if mission_result.get('is_ready'):
        embed = get_waiting_embed()
        await message.channel.send(embed=embed)
        await submit_image_data(client, message, student_mission_info, mission_result)
    else:
        # Continue to collect additional information
        await message.channel.send(mission_result['message'])

# --------------------- Event Handlers ---------------------
async def submit_image_data(client, message, student_mission_info, mission_result):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # Process the image attachment
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

def get_add_on_photo_embed(mission):
    description = (
        "恭喜完成這個月成長繪本\n"
        "想要放更多照片留作紀念嗎?\n\n"
        "> **商品**\n"
        "> 照片紀念頁\n"
        "> \n"
        "> **內容說明**\n"
        "> 共 1 頁，內含 4 張照片\n"
        "> \n"
        "> **售價**\n"
        "> 🪙 $200\n"
    )
    embed = discord.Embed(
        title="📸 加購繪本單頁",
        description=description,
        color=0xeeb2da,
    )
    instruction_url = mission.get('mission_instruction_image_url', '').split(',')[0]
    if instruction_url:
        instruction_url = create_preview_image_from_url(instruction_url)
    else:
        instruction_url = "https://infancixbaby120.com/discord_assets/book1_add_on_photo_mission_demo.png"
    embed.set_image(url=instruction_url)
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )
    return embed

def get_waiting_embed():
    embed = discord.Embed(
        title="繪本製作中，請稍等30秒",
        color=0xeeb2da
    )
    embed.set_image(url=f"https://infancixbaby120.com/discord_assets/loading1.gif")
    return embed
