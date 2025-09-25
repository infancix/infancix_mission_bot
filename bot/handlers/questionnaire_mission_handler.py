import traceback
import discord
import os
import re
import json
from types import SimpleNamespace
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from bot.views.task_select_view import TaskSelectView
from bot.views.questionnaire import QuestionnaireView
from bot.utils.message_tracker import (
    load_questionnaire_records,
    save_questionnaire_record,
    delete_questionnaire_record
)
from bot.handlers.utils import get_user_id
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.config import config

async def handle_questionnaire_mission_start(client, user_id, mission_id, send_weekly_report=1, current_round=0):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    baby = await client.api_utils.get_baby_profile(user_id)

    # Delete conversion cache
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
    embed, files = await build_questionnaire_mission_embed(mission, baby)
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
        raise ValueError("題目設定錯誤，請聯絡管理員")
        await message.channel.send("題目設定錯誤，請聯絡管理員")
        return

    questionnaire = client.mission_questionnaire[str(mission_id)][current_round]
    view = QuestionnaireView(client, mission_id, current_round, student_mission_info)
    if current_round > 0 or restart:
        embed = get_questionnaire_embed(questionnaire)
        view.message = await message.channel.send(embed=embed, view=view)
    else:
        view.message = await message.channel.send(view=view)
    return

async def send_questionnaire_end(client, message, student_mission_info):
    user_id = get_user_id(message)
    mission_id = student_mission_info['mission_id']
    records = load_questionnaire_records().get(str(user_id), {}).get(str(mission_id), [])
    last_entry = records[-1] if records else None
    clicked_options = last_entry.get('clicked_options', []) if last_entry else []
    click_summary = "、".join(opt.split('.')[-1] for opt in clicked_options)

    update_status = await client.api_utils.update_mission_image_content(
        user_id, mission_id, discord_attachments=None, aside_text=click_summary
    )
    if bool(update_status):
        await client.api_utils.submit_generate_photo_request(user_id, mission_id)
        client.logger.info(f"送出繪本任務 {mission_id}")

# --------------------- Helper Functions ---------------------
async def build_questionnaire_mission_embed(mission_info=None, baby_info=None):
    baby_info['birthdate'] = baby_info.get('birthdate') or baby_info.get('birthday')
    # Prepare description based on style
    if baby_info is None:
        author = "恭喜寶寶出生！"
    else:
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

    title = f"❓**{mission_info['photo_mission']}**(請選擇三項)"
    desc = f"\n💡回答請點選下方按鈕\n\n"

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

def get_questionnaire_embed(questionnaire):
    embed = discord.Embed(
        title=f"❓**{questionnaire['question']}**(請選擇三項)",
        description=f"\n💡回答請點選下方按鈕\n",
        color=0xeeb2da
    )
    return embed
