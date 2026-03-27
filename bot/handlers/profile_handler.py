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

async def handle_registration_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission_info = await client.api_utils.get_mission_info(mission_id)

    # Delete conversation cache
    delete_mission_record(user_id)
    if user_id in client.skip_growth_info:
        del client.skip_growth_info[user_id]

    # Mission start
    student_mission_info = {
        **mission_info,
        'user_id': user_id,
        'current_step': 1,
        'total_steps': 4
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    if int(mission_id) in config.baby_pre_registration_mission:
        # Check if user already has baby profile data
        baby_info = await client.api_utils.get_baby_profile(user_id)
        client.logger.info(f"baby_info: {baby_info}")
        birthdate = baby_info.get('birthdate') or baby_info.get('birthday') if baby_info else None
        if baby_info and baby_info.get('baby_name') and birthdate and baby_info.get('gender'):
            # User has data - show confirmation
            embed = get_baby_pre_registration_confirmation_embed(baby_info)
            mission_result = {
                'baby_name': baby_info.get('baby_name'),
                'baby_name_en': baby_info.get('baby_name_en'),
                'birthday': birthdate,  # Normalize to 'birthday'
                'gender': baby_info.get('gender')
            }
            view = TaskSelectView(client, "baby_pre_registration_confirm", mission_id, mission_result=mission_result)
            view.message = await user.send(embed=embed, view=view)
            save_task_entry_record(user_id, str(view.message.id), "baby_pre_registration_confirm", mission_id, result=mission_result)
        else:
            # No data - ask for input
            embed = get_baby_name_registration_embed(mission_info)
            await user.send(embed=embed)
    elif int(mission_id) in config.baby_name_en_registration_missions:
        baby_info = await client.api_utils.get_baby_profile(user_id)
        embed = get_baby_name_en_registration_embed(mission_info, baby_info.get('gender'))
        await user.send(embed=embed)
    else:
        embed = get_baby_registration_embed(client.reset_baby_profile.get(user_id, False))
        await user.send(embed=embed)

    return

async def handle_baby_photo_upload(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # Mission: photo upload instruction
    embed = await build_photo_instruction_embed(student_mission_info)
    await message.channel.send(embed=embed)

    student_mission_info['current_step'] = 3
    await client.api_utils.update_student_mission_status(**student_mission_info)
    return

@exception_handler(user_friendly_message="登記失敗，請稍後再試喔！\n若持續失敗，可私訊@社群管家( <@1272828469469904937> )協助。")
async def process_baby_profile_filling(client, message, student_mission_info):
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
    mission_result = client.openai_utils.process_baby_profile_validation(mission_id, mission_result, client.skip_growth_info.get(user_id, False))
    save_mission_record(user_id, mission_id, mission_result)

    if mission_result.get('is_ready'):
        success = await submit_baby_data(client, message, student_mission_info, mission_result)
        if success:
            if mission_id == config.baby_registration_mission:
                await submit_image_data(client, message, student_mission_info, mission_result)
            await client.api_utils.submit_generate_photo_request(user_id, mission_id)
            client.logger.info(f"送出繪本任務 {mission_id}")
            return
    elif mission_result.get('step_1_completed') and not mission_result.get('step_2_completed'):
        embed = get_baby_growth_registration_embed()
        view = TaskSelectView(client, "go_skip_growth_info", mission_id, mission_result=mission_result)
        view.message = await message.channel.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "baby_optin", mission_id, result=mission_result)
    elif mission_result.get('step_2_completed') and not mission_result.get('step_3_completed'):
        embed = get_baby_data_confirmation_embed(mission_result)
        # Save baby data to database
        view = TaskSelectView(client, "baby_optin", mission_id, mission_result=mission_result)
        view.message = await message.channel.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "baby_optin", mission_id, result=mission_result)
    else:
        await message.channel.send(mission_result['message'])
    return

async def prepare_api_request(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    saved_result = get_mission_record(user_id, mission_id)
    if message.attachments:        
        attachment = extract_attachment_info(message.attachments[0].url)
        saved_result['attachment'] = attachment
        saved_result['message'] = "已收到您的照片"
        return {
            'needs_ai_prediction': False,
            'direct_action': 'photo_upload',
            'direct_response': saved_result
        }
    else:
        user_message = message.content

    # Merge with existing saved result
    baby_info = await client.api_utils.get_baby_profile(user_id)
    if baby_info is None:
        baby_info = {}
    saved_result['baby_name'] = saved_result.get('baby_name', baby_info.get('baby_name', None))
    saved_result['baby_name_en'] = saved_result.get('baby_name_en', baby_info.get('baby_name_en', None))
    saved_result['gender'] = saved_result.get('gender', baby_info.get('gender', None))
    saved_result['birthday'] = saved_result.get('birthday', baby_info.get('birthday', None))

    # Build full context for AI prediction
    context_parts = []
    if saved_result.get('baby_name'):
        context_parts.append(f"Baby name: {saved_result['baby_name']}")
    if saved_result.get('baby_name_en'):
        context_parts.append(f"Baby English name: {saved_result['baby_name_en']}")
    if saved_result.get('gender'):
        context_parts.append(f"Gender: {saved_result['gender']}")
    if saved_result.get('birthday'):
        context_parts.append(f"Birthday: {saved_result['birthday']}")
    if saved_result.get('height'):
        context_parts.append(f"Height: {saved_result['height']} cm")
    if saved_result.get('weight'):
        context_parts.append(f"Weight: {saved_result['weight']} g")
    if saved_result.get('head_circumference'):
        context_parts.append(f"Head circumference: {saved_result['head_circumference']} cm")
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
    else:
        attachment_obj = [mission_result.get('attachment')]

    update_status = await client.api_utils.update_mission_image_content(user_id, mission_id, attachment_obj)
    return update_status

async def submit_baby_data(client, message, student_mission_info, mission_result):
    await client.api_utils.update_student_profile(
        str(message.author.id),
        str(message.author.name),
        '寶寶已出生'
    )

    # update baby profile
    payload = {
        'baby_name': mission_result.get('baby_name', None),
        'baby_name_en': mission_result.get('baby_name_en', 'Baby'),
        'gender': mission_result.get('gender', None),
        'birthday': mission_result.get('birthday', None),
        'height': mission_result.get('height', None),
        'weight': mission_result.get('weight', None),
        'head_circumference': mission_result.get('head_circumference', None),
    }

    response = await client.api_utils.update_student_baby_profile(str(message.author.id), **payload)
    if not response:
        await message.channel.send("更新寶寶資料失敗，請稍後再試。")
        return False

    return True


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

def get_baby_name_registration_embed(mission_info):
    embed = discord.Embed(
        title="📝 寶寶基本資料登記",
        description=(
            "請提供寶寶的基本資料：\n\n"
            "🧸 暱稱（建議2-3字）\n"
            "🧸 英文名字/暱稱（可選）\n"
            "🎂 出生日期（例如：2025-05-01）\n"
            "👤 性別（男/女）"
        ),
        color=0xeeb2da,
    )
    if mission_info['mission_id'] == 1000:
        embed.set_author(name="恭喜寶寶出生！")
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text=f"成長繪本｜{mission_info['book_month_label']} - {mission_info['mission_title']}"
    )
    return embed

def get_baby_pre_registration_confirmation_embed(baby_info):
    """確認寶寶基本資料的 embed"""
    embed = discord.Embed(
        title="✅ 確認寶寶資料",
        description="請確認以下資料是否正確：",
        color=0x5cb85c,
    )

    context = []
    if baby_info.get('baby_name'):
        context.append(f"🧸 暱稱：{baby_info['baby_name']}")
    if baby_info.get('baby_name_en'):
        context.append(f"🧸 英文名字：{baby_info['baby_name_en']}")
    # API returns 'birthdate', form uses 'birthday'
    birthday = baby_info.get('birthdate') or baby_info.get('birthday')
    if birthday:
        context.append(f"🎂 出生日期：{birthday}")
    # Display gender as Chinese
    gender = baby_info.get('gender')
    if gender:
        gender_text = '男生' if gender in ['男', 'm', 'male', 'M'] else '女生' if gender in ['女', 'f', 'female', 'F'] else gender
        context.append(f"👤 性別：{gender_text}")

    embed.add_field(
        name="👶 寶寶資料",
        value="\n".join(context) if context else "無資料",
        inline=False
    )

    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="請點選下方按鈕確認或重新填寫"
    )
    return embed

def get_baby_name_en_registration_embed(mission_info, gender=None):
    if gender is None:
        embed = discord.Embed(
            title="✏️ 製作翻譯對照表",
            description=(
                "請先告訴我們寶寶是 **男生** 還是 **女生**？\n"
                "請輸入寶寶的 [英文名字或暱稱]，\n"
                "我們將為寶寶建立專屬英文翻譯對照表，\n"
                "之後所有繪本都會自動使用這個名字喔!\n\n"
                "📝 範例：`男生 Alex` 或 `女生 Emma`"
            ),
            color=0xeeb2da,
        )
    else:
        embed = discord.Embed(
            title="✏️ 製作翻譯對照表",
            description=(
                "請輸入寶寶的 [英文名字或暱稱]，\n"
                "我們將為寶寶建立專屬英文翻譯對照表，\n"
                "之後所有繪本都會自動使用這個名字喔!"
                "📝 範例：`Alex` 或 `Emma`"
            ),
            color=0xeeb2da,
        )
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text=f"成長繪本｜{mission_info['book_month_label']} - {mission_info['mission_title']}"
    )
    return embed

def get_baby_registration_embed(reset=False):
    description_text = ""
    if reset:
        description_text += (
            "請重新輸入以下資訊，讓我們可以更新寶寶的資料喔！\n\n"
            "🧸 暱稱（建議2-3字）\n"
            "🧸 英文名字/暱稱（可選）\n"
        )
    description_text += (
        "🎂 出生日期（例如：2025-05-01）\n"
        "👤 性別（男/女）\n"
    )
    embed = discord.Embed(
        title="📝 寶寶出生資料登記",
        description=description_text,
        color=0xeeb2da,
    )
    embed.set_author(name="成長繪本｜寶寶人生第一張大頭貼 (1/3)")
    return embed

def get_baby_growth_registration_embed():
    embed = discord.Embed(
        title="📝 寶寶出生資料登記",
        description=(
            "📏 身高（cm）\n"
            "⚖️ 體重（g）\n"
            "🧠 頭圍（cm）\n"
        ),
        color=0xeeb2da,
    )
    embed.set_author(name="成長繪本｜寶寶人生第一張大頭貼 (2/3)")
    embed.set_image(url="https://infancixbaby120.com/discord_assets/mission_1001_instruction.png")
    embed.set_footer(text="可以先跳過這個步驟，之後在對話框輸入 */更新寶寶資料* 補上喔！")
    return embed

def get_baby_data_confirmation_embed(mission_result):
    embed = discord.Embed(
        title="確認寶寶資料",
        color=0xeeb2da,
    )

    context = []
    if mission_result.get('baby_name'):
        context.append(f"🧸 暱稱：{mission_result['baby_name']}")
    if mission_result.get('baby_name_en'):
        context.append(f"🧸 英文名字：{mission_result['baby_name_en']}")
    if mission_result.get('birthday'):
        context.append(f"🎂 出生日期：{mission_result['birthday']}")
    if mission_result.get('gender'):
        context.append(f"👤 性別：{mission_result['gender']}")
    if mission_result.get('height'):
        context.append(f"📏 身高：{mission_result['height']} cm")
    if mission_result.get('weight'):
        context.append(f"⚖️ 體重：{mission_result['weight']} g")
    if mission_result.get('head_circumference'):
        context.append(f"🧠 頭圍：{mission_result['head_circumference']} cm")

    embed.add_field(
        name="👶 寶寶資料",
        value="\n".join(context) if context else "無資料",
        inline=False
    )
    embed.set_footer(text="如需修改，請直接輸入新的資料")
    return embed

async def build_photo_instruction_embed(mission_info):
    title = f"**{mission_info['mission_title']}**"
    description = f"\n📎 點左下 **[+]** 上傳照片\n"
    embed = discord.Embed(
        title=title,
        description=description,
        color=0xeeb2da
    )
    embed.set_author(name="成長繪本｜寶寶人生第一張大頭貼 (3/3)")
    embed.set_image(url="https://infancixbaby120.com/discord_assets/photo_mission_instruction.png")
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )
    return embed
