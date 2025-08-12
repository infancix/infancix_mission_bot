import traceback
import discord
import os
import re
import json
from types import SimpleNamespace
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import save_task_entry_record
from bot.utils.decorator import exception_handler
from bot.utils.drive_file_utils import create_file_from_url
from bot.utils.get_intro import get_baby_intro, get_family_intro
from bot.config import config

async def handle_photo_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    baby = await client.api_utils.get_baby_profile(user_id)
    
    # Mission start
    thread_id = await init_thread_and_add_task_instructions(client, mission)
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'assistant_id': config.get_assistant_id(mission_id),
        'current_step': 1,
        'thread_id': thread_id
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    if int(mission_id) == config.baby_register_mission:
        embed = get_baby_registration_embed()
        await user.send(embed=embed)
    elif int(mission_id) in config.photo_mission_with_title_and_content:
        embed = get_add_on_photo_embed(mission)
        view = TaskSelectView(client, "check_add_on", mission_id, mission=mission)
        view.message = await user.send(embed=embed, view=view)
    else:
        embed, files = await build_photo_mission_embed(mission, baby)
        await user.send(embed=embed)
        if files:
            await user.send(files=files)

    return

async def handle_photo_upload_instruction(client, message, student_mission_info):
    user_id = str(message.author.id)

    # Mission: photo upload instruction
    embed = await build_photo_instruction_embed(mission)
    await message.channel.send(embed=embed)

    student_mission_info['current_step'] = 3
    student_mission_info['assistant_id'] = config.get_assistant_id(student_mission_info['mission_id'], student_mission_info['current_step'])
    await client.api_utils.update_student_mission_status(**student_mission_info)
    return

@exception_handler(user_friendly_message="登記失敗，請稍後再試一次！或是尋求客服協助喔！")
async def process_baby_registration_message(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    if message.attachments:
        user_message = f"[mission_id: {mission_id}]: 收到使用者的照片: {message.attachments[0].url}"
    else:
        user_message = message.content

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = student_mission_info.get('assistant_id', None) or config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = await init_thread_and_add_task_instructions(client, student_mission_info)
            student_mission_info['thread_id'] = thread_id
            await client.api_utils.update_student_mission_status(**student_mission_info)

        # get reply message
        mission_result = client.openai_utils.get_reply_message(assistant_id, thread_id, user_message)
        if not mission_result.get('image'):
            mission_result['step2'] = False

    if mission_result.get('step1') and mission_result.get('step2'):
        mission_result['content'] = get_baby_intro(
            mission_result.get('baby_name', '小寶貝'),
            mission_result.get('gender', '女孩'),
            mission_result.get('birthday', datetime.now().date().strftime('%Y-%m-%d')),
            lang_version=student_mission_info.get('lang_version', 'zh')
        )
        await submit_image_data(client, message, student_mission_info, mission_result)
    elif mission_result.get('step1') and not mission_result.get('step2'):
        embed = get_baby_data_confirmation_embed(mission_result)
        # Save baby data to database
        view = TaskSelectView(client, "baby_optin", mission_id, mission_result=mission_result)
        view.message = await message.channel.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "baby_optin", mission_id, result=mission_result)
    else:
        await message.channel.send(mission_result['message'])
        await client.api_utils.store_message(user_id, assistant_id, mission_result['message'])
        client.logger.info(f"Assistant response: {mission_result}")

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試一次喔！")
async def process_photo_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    if message.attachments:
        user_message = f"[mission_id: {mission_id}]: 收到使用者的照片: {message.attachments[0].url}"
    else:
        user_message = message.content

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = student_mission_info.get('assistant_id', None) or config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = await init_thread_and_add_task_instructions(client, student_mission_info)
            student_mission_info['thread_id'] = thread_id
            await client.api_utils.update_student_mission_status(**student_mission_info)

        # get reply message
        mission_result = client.openai_utils.get_reply_message(assistant_id, thread_id, user_message)
        if mission_result.get('is_ready') and not mission_result.get('image'):
            mission_result['is_ready'] = False  # Ensure we don't proceed if no image is provided

    # Get enough information to proceed
    if mission_result.get('is_ready'):
        if mission_id in config.family_intro_mission:
            mission_result['aside_text'] = mission_result.get('relation', '家人')
            mission_result['content'] = get_family_intro(mission_id, mission_result['aside_text'], lang_version=student_mission_info.get('lang_version', 'zh'))
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
            elif mission_id in config.family_intro_mission:
                embed = get_relationship_embed()
            else:
                embed = get_aside_text_embed()
            view = TaskSelectView(client, 'go_skip', mission_id, mission_result=mission_result)
            view.message = await message.channel.send(embed=embed, view=view)
            save_task_entry_record(user_id, str(view.message.id), "go_skip", mission_id, result=mission_result)

            # Update mission status
            student_mission_info['current_step'] = 2
            await client.api_utils.update_student_mission_status(**student_mission_info)
        else:
            # Continue to collect additional information
            await message.channel.send(mission_result['message'])

    return

@exception_handler(user_friendly_message="照片上傳失敗了，或是尋求客服協助喔！")
async def process_add_on_photo_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    if message.attachments:
        photo_urls = [attachment.url for attachment in message.attachments]
        user_message = f"[mission_id: {mission_id}]: 收到使用者的照片: {', '.join(photo_urls)}"
    else:
        user_message = message.content

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = student_mission_info.get('assistant_id', None) or config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = await init_thread_and_add_task_instructions(client, student_mission_info)
            student_mission_info['thread_id'] = thread_id
            await client.api_utils.update_student_mission_status(**student_mission_info)

        # get reply message
        mission_result = client.openai_utils.get_reply_message(assistant_id, thread_id, user_message)
        if len(mission_result.get('image', [])) < 4:
            mission_result['is_ready'] = False

    # Get enough information to proceed
    if mission_result.get('is_ready'):
        await message.channel.send("照片上傳成功，正在處理中...")
    else:
        # Continue to collect additional information
        await message.channel.send(mission_result['message'])

# --------------------- Event Handlers ---------------------
async def submit_image_data(self, client, message, student_mission_info, mission_result):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # Process the image attachment
    photo_result = await client.s3_client.process_discord_attachment(mission_result.get('image'))
    update_status = await client.api_utils.update_mission_image_content(
        user_id, mission_id, image_url=photo_result.get('s3_url'), aside_text=mission_result.get('aside_text'), content=mission_result.get('content')
    )

    if bool(update_status):
        await client.api_utils.submit_generate_photo_request(user_id, mission_id)
        client.logger.info(f"送出繪本任務 {mission_id}")
        embed = discord.Embed(title="繪本製作中，請稍等30秒")
        embed.set_image(url="https://infancixbaby120.com/discord_assets/loading1.gif")
        await message.channel.send(embed=embed)

# --------------------- Helper Functions ---------------------
async def build_photo_mission_embed(mission_info=None, baby_info=None):
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
        url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
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

async def build_photo_instruction_embed(mission_info=None):
    title = f"**上傳{mission_info['photo_mission']}**"
    description = f"\n📎 點左下 **[+]** 上傳照片\n"
    embed = discord.Embed(
        title=title,
        description=description,
        color=0xeeb2da
    )
    embed.set_image(url="https://infancixbaby120.com/discord_assets/photo_mission_instruction.png")
    embed.set_footer(
        url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )

    return embed

def get_baby_registration_embed():
    embed = discord.Embed(
        title="📝 寶寶出生資料登記",
        description=(
            "🧸 寶寶暱稱\n"
            "🎂 出生日期（例如：2025-05-01）\n"
            "👤 性別（男/女）\n"
            "📏 身高（cm）\n"
            "⚖️ 體重（g）\n"
            "🧠 頭圍（cm）\n"
        ),
        color=0xeeb2da,
    )
    embed.set_author(name="成長繪本｜第 1 個月 - 恭喜寶寶出生了")
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_relationship_embed():
    embed = discord.Embed(
        title="📝 請問你和寶寶的關係是什麼呢?",
        description="例如：媽媽、爸爸、阿嬤、姑姑、叔叔⋯⋯",
        color=0xeeb2da,
    )
    embed.set_author(name="成長繪本｜第 1 個月 - 紀錄家人")
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    return embed

def get_aside_text_embed():
    embed = discord.Embed(
        title="請輸入照片的旁白文字",
        description="請直接於對話框輸入文字，限定30個字。\n✏️ 也可以寫下拍攝日期喔!\n💡 範例：第一次幫你按摩，你就拉了三次屎。",
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

def get_baby_data_confirmation_embed(mission_result):
    embed = discord.Embed(
        title="確認您的任務內容",
        color=0xeeb2da,
    )

    embed.add_field(
        name="👶 寶寶資料",
        value=(
            f"🧸 寶寶暱稱：{mission_result.get('baby_name', '未設定')}\n"
            f"🎂 出生日期：{mission_result.get('birthday', '未設定')}\n"
            f"👤 性別：{mission_result.get('gender', '未設定')}\n"
            f"📏 身高：{mission_result.get('height', '未設定')} cm\n"
            f"⚖️ 體重：{mission_result.get('weight', '未設定')} g\n"
            f"🧠 頭圍：{mission_result.get('head_circumference', '未設定')} cm"
        ),
        inline=False
    )

    embed.set_footer(text="如需修改，請直接輸入新的資料")
    return embed

def get_add_on_photo_embed(mission):
    description = (
        "恭喜完成這個月成長繪本\n"
        "想要放更多照片留作紀念嗎?\n\n"
        ">**商品**\n"
        ">照片紀念頁\n"
        "> \n"
        ">**內容說明**\n"
        ">共 1 頁，內含 4 張照片\n"
        "> \n"
        ">**售價**\n"
        ">🪙 $200\n"
    )
    embed = discord.Embed(
        title="📸 加購繪本單頁",
        description=description,
        color=0xeeb2da,
    )
    embed.set_image(url=self.mission.get('mission_introduction_image_url', 'https://infancixbaby120.com/discord_assets/book1_add_on_photo_mission_demo.png'))
    embed.set_footer(
        url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )
    return embed

async def init_thread_and_add_task_instructions(client, student_mission_info):
    thread_id = client.openai_utils.load_thread()

    # Add task instructions to the assistant's thread
    if student_mission_info['mission_id'] == config.baby_register_mission:
        mission_instructions = f"請使用者輸入寶寶的出生資料，包含寶寶暱稱、出生日期、性別、身高、體重和頭圍。\n"
    else:
        mission_instructions = (
            f"請使用者上傳照片，並根據任務要求提供相關的描述或旁白。\n"
            f"任務名稱: {student_mission_info['photo_mission']}\n"
        )

    # Add task instructions to the thread
    client.openai_utils.add_task_instruction(thread_id, mission_instructions)
    return thread_id
