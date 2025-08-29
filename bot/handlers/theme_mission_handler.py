import traceback
import discord
import os
import re
import json
from types import SimpleNamespace
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    save_task_entry_record,
    load_conversations_records,
    save_conversations_record,
    delete_conversations_record
)
from bot.utils.decorator import exception_handler
from bot.utils.drive_file_utils import create_file_from_url
from bot.config import config

async def handle_theme_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    
    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': 1,
        'total_steps': 5
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    embed = build_theme_mission_instruction_embed(mission)
    await user.dm_channel.send(embed=embed)
    embed = get_baby_registration_embed()
    await user.dm_channel.send(embed=embed)
    return

@exception_handler(user_friendly_message="照片上傳失敗了，或是尋求客服協助喔！")
async def process_theme_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    book_id = student_mission_info['book_id']
    mission_id = student_mission_info['mission_id']
    prompt_path = config.get_prompt_file(mission_id)

    # getting user message
    if student_mission_info.get('current_step', 1) == 1 and message.attachments:
        await message.channel.send("請先完成主角寶寶姓名登記，再上傳照片喔！")
        return

    if user_id in client.photo_mission_replace_index and message.attachments:
        offset = client.photo_mission_replace_index[user_id][0]
        if offset == 0:
            user_message = (
                f"User wants to replace cover page.\n"
                f"New uploaded cover page object: {message.attachments[0]}"
            )
        else:
            user_message = (
                f"User wants to replace photo #{offset}.\n"
                f"New uploaded attachment object: {message.attachments[0]}"
            )
    elif student_mission_info.get('current_step', 1) == 2 and len(message.attachments) == 1:
        user_message = f"New uploaded cover page object: {message.attachments[0]}"
    elif message.attachments:
        user_message = f"User uploaded {len(message.attachments)} photo(s). Attachment object: {message.attachments}"
    else:
        user_message = message.content

    # getting assistant reply
    async with message.channel.typing():
        records = load_conversations_records()
        conversations = records[user_id].get(str(mission_id), None) if user_id in records else None

        # get reply message
        mission_result = client.openai_utils.process_user_message(prompt_path, user_message, conversations=conversations)
        client.logger.info(f"Assistant response: {mission_result}")
        if mission_result.get('attachment') and len(mission_result.get('attachment')) < 6:
            mission_result['is_ready'] = False

    # log user message
    save_conversations_record(user_id, mission_id, 'user', user_message)

    # Get enough information to proceed
    if mission_result.get('is_ready'):
        embed = get_waiting_embed(watting_time='long')
        await message.channel.send(embed=embed)

        # re-submit single page
        if user_id in client.photo_mission_replace_index:
            offset, resubmit_mission_id = client.photo_mission_replace_index[user_id]
            success = await client.api_utils.update_mission_image_content(user_id, resubmit_mission_id, [mission_result['attachment'][offset-1]], aside_text=mission_result.get('aside_text'))
            if bool(success):
                await client.api_utils.submit_generate_photo_request(user_id, resubmit_mission_id)
                client.logger.info(f"送出繪本任務 {resubmit_mission_id}")
            else:
                client.logger.warning(f"送出繪本任務 {resubmit_mission_id} 失敗")
                await message.channel.send("照片上傳失敗了，請稍後再試，或是尋求客服協助喔！")
        # Submit multiple pages
        else:
            success = await client.api_utils.update_mission_multiple_image_content(user_id, mission_id, mission_result.get('attachment'))
            if bool(success):
                # start to generate album
                await client.api_utils.submit_generate_album_request(user_id, book_id)

    else:
        # Step1: baby name registration
        if student_mission_info.get('current_step', 1) == 1 and mission_result.get('baby_name'):
            success = await submit_baby_data(client, message, student_mission_info, mission_result)
            if bool(success):
                mission_info = await client.api_utils.get_mission_info(mission_id)
                embed = get_cover_instruction_embed(mission_info)
                await message.channel.send(embed=embed)
            
                # update mission status
                student_mission_info['current_step'] = 2
                await client.api_utils.update_student_mission_status(**student_mission_info)

        # Step2: cover photo upload
        elif student_mission_info.get('current_step', 1) == 2 and mission_result.get('cover', {}).get('id', None):
            success = await client.api_utils.update_mission_image_content(user_id, mission_id, [mission_result['cover']])
            if bool(success):
                mission_info = await client.api_utils.get_mission_info(mission_id+1)
                embed = get_story_pages_embed(mission_info)
                await message.channel.send(embed=embed)

                student_mission_info['current_step'] = 3
                await client.api_utils.update_student_mission_status(**student_mission_info)

        else:
            # Continue to collect additional information
            await message.channel.send(mission_result['message'])
            save_conversations_record(user_id, mission_id, 'assistant', mission_result['message'])

# --------------------- Event Handlers ---------------------
async def submit_baby_data(client, message, student_mission_info, mission_result):
    response = await client.api_utils.update_student_baby_name(str(message.author.id), mission_result.get('baby_name', None))
    if not bool(response):
        await message.channel.send("更新寶寶資料失敗，請稍後再試。")
        return False
    return True

# --------------------- Helper Functions ---------------------
def build_theme_mission_instruction_embed(mission_info):
    embed = discord.Embed(
        title=mission_info['mission_type'],
        description=mission_info['mission_instruction'],
        color=0xeeb2da
    )
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )
    return embed

def get_baby_registration_embed():
    embed = discord.Embed(
        title="📝 主角登記",
        description=(
            "🧸 暱稱（建議2-3字）\n"
        ),
        color=0xeeb2da,
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_cover_instruction_embed(mission_info):
    embed = discord.Embed(
        title="📤 請上傳封面照片",
        description=f"📸 {mission_info['photo_mission']}\n\n💡 請選擇寶寶頭部置中的照片\n",
        color=0xeeb2da,
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_story_pages_embed(mission_info):
    embed = discord.Embed(
        title="📤 請上傳內頁照片",
        description=f"💡 {mission_info['photo_mission']}",
        color=0xeeb2da,
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_waiting_embed(watting_time='short'):
    if watting_time == 'long':
        embed = discord.Embed(
            title=f"繪本準備中，請稍 3 ~ 5 分鐘喔 !",
            color=0xeeb2da
        )
    else:
        embed = discord.Embed(
            title=f"繪本準備中，請稍等一下",
            color=0xeeb2da
        )
    embed.set_image(url=f"https://infancixbaby120.com/discord_assets/loading2.gif")
    return embed
