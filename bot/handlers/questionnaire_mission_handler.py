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
from bot.config import config

async def handle_questionnaire_mission_start(client, user_id, mission_id, send_weekly_report=1, current_round=0):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    baby = await client.api_utils.get_baby_profile(user_id)

    # Delete conversation cache
    delete_questionnaire_record(user_id, mission_id)
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

    # Send weekly report
    questionnaire = client.mission_questionnaire[str(mission_id)][current_round]
    embed, files = await build_questionnaire_mission_embed(questionnaire, mission, baby)
    if send_weekly_report and files:
        await user.send(files=files)

    # Start questionnaire
    view = QuestionnaireView(client, mission_id, current_round, student_mission_info)
    view.message = await user.send(embed=embed, view=view)
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
    view = QuestionnaireView(client, mission_id, current_round, student_mission_info)
    if current_round > 0 or restart:
        embed = get_questionnaire_embed(questionnaire)
        view.message = await message.channel.send(embed=embed, view=view)
    else:
        view.message = await message.channel.send(view=view)
    return

async def handle_questionnaire_completion(client, message, student_mission_info):
    user_id = get_user_id(message)
    mission_id = student_mission_info['mission_id']
    saved_result = get_mission_record(user_id, mission_id) or {}
    records = load_questionnaire_records().get(str(user_id), {}).get(str(mission_id), [])
    last_entry = records[-1] if records else None
    clicked_options = last_entry.get('clicked_options', []) if last_entry else []
    click_summary = "、".join(opt.split('.')[-1] for opt in clicked_options)

    if click_summary != "跳過":
        saved_result['aside_text'] = click_summary
        attachments = [saved_result.get('attachment')] if saved_result.get('attachment') else None
        save_mission_record(user_id, mission_id, saved_result)
        success = await client.api_utils.update_mission_image_content(
            user_id, mission_id, discord_attachments=attachments, aside_text=click_summary
        )

    if click_summary == "跳過" or success:
        client.logger.info(f"✅ 已更新任務附加文字，使用者 {user_id} 任務 {mission_id} 內容 {click_summary}")
        if mission_id in config.questionnaire_without_image_mission:
            await client.api_utils.submit_generate_photo_request(user_id, mission_id)
            client.logger.info(f"送出繪本任務 {mission_id}")
        elif saved_result.get('attachment') and saved_result['attachment'].get('url') and click_summary:
            await client.api_utils.submit_generate_photo_request(user_id, mission_id)
            client.logger.info(f"送出繪本任務 {mission_id}")
        else:
            mission_info = await client.api_utils.get_mission_info(mission_id)
            # call upload_image embedded function
            embed = get_image_embed(mission_info)
            await message.channel.send(embed=embed)
    return

async def process_questionnaire_photo_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    prompt_path = config.get_prompt_file(mission_id)

    request_info = prepare_api_request(client, message, student_mission_info)
    client.logger.info(f"Prepared request info for user {user_id}, mission {mission_id}: {request_info}")

    if request_info.get('direct_action') == 'error':
        await message.channel.send(request_info.get('context', '發生錯誤，請稍後再試。'))
        return
    elif request_info['needs_ai_prediction']:
        async with message.channel.typing():
            conversations = [{'role': 'user', 'message': request_info['context']}] if request_info['context'] else None
            mission_result = client.openai_utils.process_user_message(prompt_path, request_info['user_message'], conversations=conversations)
            client.logger.info(f"Assistant response: {mission_result}")
    else:
        # Skip AI prediction, use direct response
        mission_result = request_info.get('direct_response', {})

    # Save mission result
    save_mission_record(user_id, mission_id, mission_result)

    # validate mission result
    if mission_result.get('attachment') and mission_result['attachment'].get('url') and mission_result.get('aside_text') is not None:
        mission_result['is_ready'] = True

    if mission_result.get('is_ready'):
        aside_text = mission_result.get('aside_text') if mission_result.get('aside_text') and mission_result.get('aside_text') != '跳過' else None
        success = await client.api_utils.update_mission_image_content(
            user_id, mission_id, discord_attachments=[mission_result['attachment']], aside_text=aside_text
        )
        if success:
            await client.api_utils.submit_generate_photo_request(user_id, mission_id)
            client.logger.info(f"送出繪本任務 {mission_id}")
    else:
        # Continue to collect additional information
        await message.channel.send(mission_result['message'])

    return

def prepare_api_request(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    saved_result = get_mission_record(user_id, mission_id) or {}
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

    return {
        'needs_ai_prediction': True,
        'direct_action': None,
        'context': "",
        'user_message': user_message
    }


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

async def build_questionnaire_mission_embed(questionnaire_info, mission_info, baby_info=None):
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
        title=f"**{questionnaire_info['question']}**",
        description=mission_info['mission_instruction'] if mission_info.get('mission_instruction') else "\n💡回答請點選下方按鈕\n",
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

def get_questionnaire_embed(questionnaire):
    embed = discord.Embed(
        title=f"**{questionnaire['question']}**",
        description=f"\n💡回答請點選下方按鈕\n",
        color=0xeeb2da
    )
    return embed

def get_image_embed(mission_info):
    embed = discord.Embed(
        title = f"📸**{mission_info['photo_mission']}**",
        description=f"\n📎 點左下 **[+]** 上傳照片",
        color=0xeeb2da
    )
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="若有任何問題，隨時聯絡社群客服「阿福」。"
    )
    return embed
