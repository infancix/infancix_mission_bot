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

async def handle_photo_mission_start(client, user_id, mission_id, send_weekly_report=1):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    baby = await client.api_utils.get_baby_profile(user_id)

    # Delete conversation cache
    delete_mission_record(user_id)
    delete_conversations_record(user_id, mission_id)
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

    if int(mission_id) in config.add_on_photo_mission:
        embed = get_add_on_photo_embed(mission)
        view = TaskSelectView(client, "check_add_on", mission_id, mission_result=mission)
        view.message = await user.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "check_add_on", mission_id, result=mission)
        save_conversations_record(user_id, mission_id, 'assistant', f"請使用者上傳[mission{'photo_mission'}]的照片")
    else:
        embed, files = await build_photo_mission_embed(mission, baby)
        if send_weekly_report and files:
            await user.send(files=files)
        await user.send(embed=embed)
    return

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試喔！\n若持續失敗，可尋求社群客服「阿福 <@1272828469469904937>」協助。")
async def process_photo_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    prompt_path = config.get_prompt_file(mission_id)

    if message.attachments:
        if user_id not in client.photo_mission_replace_index:
            user_message = f"User uploaded {len(message.attachments)} photo(s). Attachment object: {message.attachments[0]}"
            client.photo_mission_replace_index[user_id] = 1
        else:
            user_message = f"User wants to replace photo.\n New uploaded attachment: {message.attachments[0]}"
    else:
        if student_mission_info.get('current_step', 1) == 2 and mission_id in config.photo_mission_with_aside_text:
            user_message = f"User provided aside text: {message.content}"
            client.skip_aside_text[user_id] = False
        elif student_mission_info.get('current_step', 1) == 2 and mission_id in config.photo_mission_with_title_and_content:
            user_message = f"User provide the content: {message.content}"
        else:
            user_message = message.content

    async with message.channel.typing():
        records = load_conversations_records()
        conversations = records[user_id].get(str(mission_id), None) if user_id in records else None

        # get reply message
        mission_result = client.openai_utils.process_user_message(prompt_path, user_message, conversations=conversations)
        client.logger.info(f"Assistant response: {mission_result}")
        if student_mission_info.get('current_step', 1) == 2 and mission_id in config.photo_mission_with_aside_text:
            mission_result = client.openai_utils.process_aside_text_validation(mission_result, skip_aside_text=client.skip_aside_text.get(user_id, False))
            client.logger.info(f"Processed aside text validation: {mission_result}")

    # Get enough information to proceed
    save_conversations_record(user_id, mission_id, 'user', user_message)

    if mission_result.get('is_ready'):
        if  mission_id in config.photo_mission_without_aside_text or client.skip_aside_text.get(user_id, False):
            await submit_image_data(client, message, student_mission_info, mission_result)
            return
        else:
            embed = get_confirmation_embed(mission_result)
            view = TaskSelectView(client, "go_submit", mission_id, mission_result=mission_result)
            view.message = await message.channel.send(embed=embed, view=view)
            save_task_entry_record(user_id, str(view.message.id), "go_submit", mission_id, result=mission_result)
    else:
        if student_mission_info['current_step'] == 1:
            if mission_id in config.photo_mission_with_title_and_content:
                embed = get_letter_embed()
            else:
                embed = get_aside_text_embed()
            view = TaskSelectView(client, 'go_skip_aside_text', mission_id, mission_result=mission_result)
            view.message = await message.channel.send(embed=embed, view=view)
            save_task_entry_record(user_id, str(view.message.id), "go_skip_aside_text", mission_id, result=mission_result)

            # Update mission status
            student_mission_info['current_step'] = 2
            await client.api_utils.update_student_mission_status(**student_mission_info)
        else:
            # Continue to collect additional information
            await message.channel.send(mission_result['message'])
            save_conversations_record(user_id, mission_id, 'assistant', mission_result['message'])

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
    context = ""
    saved_result = get_mission_record(user_id, mission_id)
    if saved_result.get('attachment'):
        context_parts = []
        context_parts.append(f"Previous attachments: {len(saved_result['attachment'])} photos collected")
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

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試喔！\n若持續失敗，可尋求社群客服「阿福 <@1272828469469904937>」協助。")
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
        save_conversations_record(user_id, mission_id, 'assistant', mission_result['message'])

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

async def build_photo_instruction_embed(mission_info):
    title = f"**{mission_info['photo_mission']}**"
    description = f"\n📎 點左下 **[+]** 上傳照片\n"
    embed = discord.Embed(
        title=title,
        description=description,
        color=0xeeb2da
    )
    embed.set_image(url="https://infancixbaby120.com/discord_assets/photo_mission_instruction.png")
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )
    return embed

def get_aside_text_embed():
    embed = discord.Embed(
        title="✏️ 寫下該照片的回憶",
        description="請於對話框輸入文字(限定30個字)\n_範例：第一次幫你按摩，就解決了你的便秘。_",
        color=0xeeb2da,
    )
    return embed

def get_letter_embed():
    embed = discord.Embed(
        title="✏️ 寫一封信給寶寶",
        description="請於對話框輸入文字(不限定字數)\n",
        color=0xeeb2da,
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_confirmation_embed(mission_result):
    content = mission_result.get('content') or mission_result.get('aside_text')
    quoted_content = '\n'.join(f'> {line}' for line in content.splitlines())
    embed = discord.Embed(
        title="🔍 確認內容",
        description=quoted_content,
        color=0xeeb2da,
    )
    embed.set_footer(text="如需修改，請直接輸入新內容")
    return embed

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
