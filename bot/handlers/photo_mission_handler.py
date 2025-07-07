import traceback
import discord
import os
import re
from types import SimpleNamespace
from datetime import datetime, date

from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import save_task_entry_record
from bot.utils.decorator import exception_handler
from bot.utils.drive_file_utils import create_file_from_url
from bot.config import config

async def handle_photo_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    baby = await client.api_utils.get_baby_profile(user_id)
    
    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'assistant_id': config.get_assistant_id(mission_id),
        'current_step': 1
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    embed, files = await build_photo_mission_embed(mission, baby)
    await user.send(embed=embed)
    if files:
        await user.send(files=files)

    return

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試一次喔！")
async def process_photo_mission_filling(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    if message.attachments:
        photo_url = await client.s3_client.process_discord_attachment(message.attachments[0].url)
        user_message = f"[mission_id: {mission_id}]: 收到使用者的照片: {photo_url}"
    else:
        user_message = message.content

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = client.openai_utils.load_thread()
            student_mission_info['thread_id'] = thread_id
            await client.api_utils.update_student_mission_status(**student_mission_info)
            # Add task instructions to the assistant's thread
            task_request = (
                f"這是這次的任務說明：\n"
                f"- mission_id: {mission_id}\n"
                f"- 照片任務: {student_mission_info['photo_mission']}\n"
            )
            default_content = await client.api_utils.get_mission_default_content_by_id(user_id, mission_id)
            if default_content:
                task_request += f"草稿：\n{default_content}"
            if mission_id in config.baby_intro_mission:
                get_baby_additional_info = await client.api_utils.get_baby_additional_info(user_id)
                task_request += get_baby_additional_info
            client.openai_utils.add_task_instruction(thread_id, task_request)

        # add user message
        mission_result = client.openai_utils.get_reply_message(assistant_id, thread_id, user_message)

    # Get enough information to proceed
    if mission_result.get('is_ready'):
        if mission_id in config.baby_intro_mission:
            embed = get_baby_data_confirmation_embed(mission_result)
        else:
            embed = get_comfirmation_embed(mission_result)
        view = TaskSelectView(client, "go_submit", mission_id, mission_result=mission_result)
        view.message = await message.channel.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "go_submit", mission_id, result=mission_result)
    else:
        if student_mission_info['current_step'] == 1:
            # Send mission introduction
            if mission_id in config.baby_intro_mission:
                embed = get_baby_registration_embed()
                await message.channel.send(embed=embed)
            elif mission_id in config.photo_mission_with_title_and_content:
                embed = get_content_embed(student_mission_info)
                await message.channel.send(embed=embed)
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

@exception_handler(user_friendly_message="照片上傳失敗了，請稍後再試一次喔！")
async def process_photo_upload_and_summary(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    photo_url = await client.s3_client.process_discord_attachment(message.attachments[0].url)
    user_message = f"[mission_id: {mission_id}]: 收到使用者的照片: {photo_url}"

    await client.api_utils.upload_baby_image(user_id, mission_id, student_mission_info['mission_title'], photo_url)
    await client.api_utils.store_message(user_id, 'user', f"收到任務照片: {photo_url}")

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = client.openai_utils.load_thread()
            student_mission_info['thread_id'] = thread_id
            await client.api_utils.update_student_mission_status(**student_mission_info)
        bot_response = client.openai_utils.get_reply_message(assistant_id, thread_id, user_message)

    await message.channel.send(bot_response['message'])
    await client.api_utils.store_message(user_id, assistant_id, bot_response['message'])
    client.logger.info(f"Assitant response: {bot_response}")

    # Mission Completed
    student_mission_info['current_step'] = 4
    student_mission_info['score'] = 1
    await client.api_utils.update_student_mission_status(**student_mission_info)
    await send_reward_and_log(client, user_id, mission_id, reward=100)

# --------------------- Helper Functions ---------------------
async def build_photo_mission_embed(mission_info=None, baby_info=None):
    # Prepare description based on style
    birthday = datetime.strptime(baby_info['birthdate'], '%Y-%m-%d').date()
    age = (date.today() - birthday).days
    author = f"🧸今天{baby_info['baby_name']}出生滿 {age} 天"

    title = f"📸[{mission_info['page_progress']}] **{mission_info['photo_mission']}**"
    desc = (
        f"📌 點選左下方「+」上傳照片\n"
        f"讓這一刻變成繪本的一頁🌠\n"
        f"_\n"
    )

    if int(mission_info['mission_id']) < 100: # infancix_mission
        desc += f"🧠 科學育兒知識： {mission_info['mission_title']}\n"
    elif mission_info.get('mission_introduction'):
        desc += f"**{mission_info['mission_type']}**\n{mission_info['mission_introduction']}\n"

    if int(mission_info['mission_id']) < 100:
        video_url = mission_info.get('mission_video_contents', '').strip()
        image_url = mission_info.get('mission_image_contents', '').strip()
        if video_url and image_url:
            desc += f"▶️ [教學影片]({video_url})\u2003\u2003📂 [圖文懶人包]({image_url})\n"
        elif video_url:
            desc += f"▶️ [教學影片]({video_url})\n"

    desc += "\n_\n❔輸入「 / 」 __補上傳照片__、__查看育兒里程碑__、__瀏覽繪本進度__"

    embed = discord.Embed(
        title=title,
        description=desc,
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    embed.set_author(name=author)
    embed.set_footer(text=mission_info['mission_type'])

    files = []
    if '成長週報' in mission_info['mission_type']:
        for url in mission_info['mission_image_contents'].split(','):
            if url.strip():
                file = await create_file_from_url(url.strip())
                if file:
                    files.append(file)

    return embed, files

def get_baby_registration_embed():
    embed = discord.Embed(
        title="📝 寶寶資料登記",
        description=(
            "🎂 出生日期（例如：2025-05-01）\n"
            "👤 性別（男/女）\n"
            "📏 身高（cm）\n"
            "⚖️ 體重（g）\n"
            "🧠 頭圍（cm）\n\n"
            "🤖 **繪本精靈AI 會協助您逐項填寫，請先輸入第一項即可！**"
        ),
        color=discord.Color.blue()
    )
    return embed

def get_aside_text_embed():
    embed = discord.Embed(
        title="請輸入照片的旁白文字",
        description="請直接於對話框輸入文字，限定30個字。\n✏️ 也可以寫下拍攝日期喔!\n💡 範例：第一次幫你按摩，你就拉了三次屎。",
        color=discord.Color.blue()
    )
    return embed

def get_content_embed(mission_info):
    embed = discord.Embed(
        title=mission_info['mission_introduction'] or "請輸入照片的內容",
        description="請直接於對話框輸入文字，限定200個字。\n",
        color=discord.Color.blue()
    )
    return embed

def get_comfirmation_embed(mission_result):
    content = mission_result.get('aside_text') or mission_result.get('content')
    embed = discord.Embed(
        title="確認您的任務內容",
        description=f"> {content}",
        color=discord.Color.blue()
    )
    embed.set_footer(text="如需修改，請直接輸入新內容")
    return embed

def get_baby_data_confirmation_embed(mission_result):
    embed = discord.Embed(
        title="📝 請確認寶寶資料",
        description="請確認以下資料是否正確，確認無誤後點擊「確認送出」",
        color=discord.Color.orange()
    )

    embed.add_field(
        name="👶 寶寶資料",
        value=(
            f"🎂 出生日期：{mission_result.get('birth_date', '未設定')}\n"
            f"👤 性別：{mission_result.get('gender', '未設定')}\n"
            f"📏 身高：{mission_result.get('height', '未設定')} cm\n"
            f"⚖️ 體重：{mission_result.get('weight', '未設定')} g\n"
            f"🧠 頭圍：{mission_result.get('head_circumference', '未設定')} cm"
        ),
        inline=False
    )

    embed.set_footer(text="如需修改，請直接輸入新的資料")
    return embed
