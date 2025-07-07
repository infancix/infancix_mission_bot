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
        bot_response = client.openai_utils.get_reply_message(assistant_id, thread_id, user_message)
        
    if bot_response.get('is_ready'):
        # Handle mission status update
        book_data = {
            'mission_id': mission_id,
            'image_url': bot_response.get('image'),
            'aside_text': bot_response.get('aside_text'),
            'content': bot_response.get('content')
        }

        if int(mission_id) in config.baby_intro_mission:
            baby_data = bot_response
        else:
            baby_data = None

        content = bot_response.get('aside_text') or bot_response.get('content')
        if bot_response.get('image') and content:
            confirmation_message = (
                f"請確認您即將送出的內容，如果一切無誤，請點擊「送出」按鈕來提交！\n"
                f"> {content}\n\n"
                ""
            )
            view = TaskSelectView(client, "go_submit", mission_id, book_data=book_data, baby_data=baby_data)
            view.message = await message.channel.send(confirmation_message, view=view)
            save_task_entry_record(user_id, str(view.message.id), "go_submit", mission_id, book_data=book_data, baby_data=baby_data)

    else:
        await message.channel.send(bot_response['message'])
        if message.attachments:
            embed = discord.Embed(
                title="幫這張照片寫下一句回憶",
                description="請直接於對話框輸入文字，限定30個字。\n✏️ 也可以寫下拍攝日期喔!\n💡 範例：第一次幫你按摩，你就拉了三次屎。",
                color=discord.Color.blue()
            )
            view = TaskSelectView(client, 'go_skip', mission_id)
            view.message = await message.channel.send(view=view)
            save_task_entry_record(user_id, str(view.message.id), "go_skip", mission_id)

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
