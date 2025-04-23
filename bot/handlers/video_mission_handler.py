import discord
import os
import re
from types import SimpleNamespace
from datetime import datetime

from bot.views.quiz import QuizView
from bot.views.task_select_view import TaskSelectView
from bot.handlers.photo_mission_handler import handle_photo_mission
from bot.handlers.utils import get_user_id, send_reward_and_log
from bot.utils.asset_downloader import download_drive_image
from bot.utils.message_tracker import (
    save_quiz_message_record,
    save_task_entry_record
)
from bot.config import config

async def handle_video_mission_dm(client, message, student_mission_info):
    user_id = str(message.author.id)
    student_mission_info['user_id'] = user_id
    if "收到使用者的照片" in message.content:
        await handle_photo_mission(client, message, student_mission_info)
        return

    # Handle next step
    current_step = student_mission_info['current_step']
    if current_step <= 2:
        await message.channel.send(f"請先看影片，再進行測驗喔，如果影片連結有問題，請找管理員協助處理。")
    elif current_step == 3:
        await handle_quiz(client, message, student_mission_info)
    else:
        await handle_follow_up(client, message, student_mission_info)

async def handle_video_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    baby_info = await client.api_utils.get_baby_profile(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    is_photo_mission = mission_id in config.photo_mission_list
    mission_instructions = (
        f"這是這次課程的主題和課程影片字幕：\n"
        f"## 課程內容： {mission['mission_title']}\n"
        f"## 影片字幕: {mission['transcription']}\n"
    )
    if is_photo_mission:
        mission_instructions += f"## 照片任務: {mission['photo_mission']}"

    thread_id = client.openai_utils.load_thread()
    client.openai_utils.add_task_instruction(thread_id, mission_instructions)

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'assistant_id': config.MISSION_BOT_ASSISTANT,
        'thread_id': thread_id,
        'current_step': 1
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    hello_message = (
        f"✨ 今天是 {datetime.now().strftime('%Y-%m-%d')}，歡迎回來！\n"
        f"👶 寶寶今天是出生第 {calculate_age(baby_info['birthdate'])} 天。\n\n"
        f"🎖 **{mission['mission_title']}** 🎖\n"
        f"{mission['mission_type']}\n\n"
        f"🎥 影片教學\n"
        f"> {mission['mission_video_contents']}\n\n"
        f"📖 圖文教學內容\n"
        f"> 見附檔\n\n"
        f"看完之後記得告訴我，我們就能開始小測驗囉！🙌"
    )

    files = []
    for url in mission['mission_image_contents'].split(','):
        file = await download_drive_image(url)
        files.append(file)

    await user.send(hello_message, files=files)
    await client.api_utils.store_message(user_id, 'assistant', hello_message)

    view = TaskSelectView(client, "go_quiz", mission_id)
    view.message = await user.send(view=view)
    save_task_entry_record(user_id, str(view.message.id), "go_photo", mission_id)

async def handle_quiz(client, message, student_mission_info, current_round=0, score=0):
    user_id = get_user_id(message)
    mission_id = int(student_mission_info['mission_id'])

    # Start quiz
    total_rounds = 5
    quiz = client.mission_quiz[str(mission_id)][current_round]
    question = quiz['question'].replace('？', ':grey_question:')

    embed = discord.Embed(
        title=f"🧠 小測驗 - 第 {current_round+1} 題",
        description=f"🌟 {question}",
        color=discord.Color.blue()
    )

    view = QuizView(client, mission_id, current_round, score, student_mission_info)
    view.message = await message.channel.send(embed=embed, view=view)

    # save record
    save_quiz_message_record(str(message.author.id), str(view.message.id), mission_id, current_round, score)

async def send_quiz_summary(interaction, correct, student_mission_info):
    user_id = get_user_id(interaction)
    mission_id = student_mission_info['mission_id']
    total = 5
    score = float(correct) / total

    quiz_summary = f"測驗結束！🎉 答對 {correct}/{total} 題！🎓\n"
    if score >= 0.8:
        quiz_summary += "恭喜你！你已經掌握了這堂課的知識！"
    else:
        quiz_summary += "加油！還有一些地方需要加強，別氣餒！"

    await interaction.channel.send(quiz_summary)
    await interaction.client.api_utils.store_message(user_id, 'assistant', quiz_summary)

    student_mission_info['current_step'] = 4
    student_mission_info['score'] = score
    await interaction.client.api_utils.update_student_mission_status(**student_mission_info)
    await send_reward_and_log(interaction.client, user_id, mission_id, 20)
    await handle_mission_end(interaction.client, interaction, student_mission_info)

async def handle_mission_end(client, message, student_mission_info):
    user_id = get_user_id(message)
    mission_id = int(student_mission_info['mission_id'])
    is_photo_mission = student_mission_info['mission_id'] in config.photo_mission_list
    if is_photo_mission:
        ending_msg = "這堂課的最後一步很特別，我們有個超可愛的照片任務，你一定不能錯過！"
        view = TaskSelectView(client, "go_photo", mission_id)
        view.message = await message.channel.send(view=view)
        save_task_entry_record(user_id, str(view.message.id), "go_photo", mission_id)

async def handle_follow_up(client, message, student_mission_info):
    user_id = get_user_id(message)
    try:
        thread_id = student_mission_info['thread_id']
        assistant_id = student_mission_info.get('assistant_id') if student_mission_info.get('assistant_id') else config.MISSION_BOT_ASSISTANT
        async with message.channel.typing():
            response = await client.openai_utils.get_reply_message(assistant_id, thread_id, message.content)
            client.logger.info(f"Assitant response: {response}")

        if response.get('class_state') == 'quiz':
            student_mission_info['current_step'] = 3
            await client.api_utils.update_student_mission_status(**student_mission_info)
            await handle_quiz(client, message, student_mission_info)
        else:
            student_mission_info['current_step'] = 4
            await client.api_utils.update_student_mission_status(**student_mission_info)
            await message.channel.send(response['message'])
            await handle_mission_end(client, message, student_mission_info)

    except Exception as e:
        await message.channel.send("加一不太懂，可以再試一次嗎？或是管理員協助處理。")

def calculate_age(birthdate):
    today = datetime.today().date()
    birthdate = datetime.strptime(birthdate, '%Y-%m-%d').date()
    age = today - birthdate
    return age.days
