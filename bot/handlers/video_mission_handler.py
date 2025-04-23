import discord
import os
import re
from types import SimpleNamespace
from datetime import datetime

from bot.views.quiz import QuizView
from bot.views.reply_options import ReplyOptionView
from bot.handlers.photo_mission_handler import handle_photo_mission, handle_photo_mission_start
from bot.handlers.utils import send_reward_and_log
from bot.utils.asset_downloader import download_drive_image
from bot.utils.message_tracker import (
    save_quiz_message_record,
    save_reply_option_record
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

    option = "進行小測驗 GO!"
    view = ReplyOptionView([option])
    view.message = await user.send(view=view)
    save_reply_option_record(user_id, str(view.message.id), [option])

    await view.wait()
    if view.selected_option is not None:
        student_mission_info['current_step'] = 3
        await client.api_utils.update_student_mission_status(**student_mission_info)
        message = SimpleNamespace(author=user, channel=user.dm_channel, content=None)
        await handle_quiz(client, message, student_mission_info)

async def handle_quiz(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = int(student_mission_info['mission_id'])
    mission = await client.api_utils.get_mission_info(mission_id)
    student_mission_info.update(mission)

    # Get quiz
    quizzes = client.openai_utils.mission_quiz[str(mission_id)]

    # Start quiz
    quiz_message = f"準備進行小測驗囉！讓我來看看你對「{student_mission_info['mission_title']}」的知識掌握得怎麼樣呢 🐾✨"
    await message.channel.send(quiz_message)
    await client.api_utils.store_message(user_id, 'assistant', quiz_message)

    print(f"{quizzes}")
    total, correct = len(quizzes), 0
    for quiz in quizzes:
        is_correct = await process_quiz_question(client, message, quiz)
        if is_correct in [0, 1]:
            correct += is_correct
        else:
            timeout_msg = f"⏰挑戰時間已到！\n下次再努力喔"
            await message.channel.send(timeout_msg)
            await client.api_utils.store_message(user_id, 'assistant', timeout_msg)
            await client.api_utils.update_student_mission_status(user_id, student_mission_info['mission_id'], is_paused=True)
            return

    # Quiz summary
    quiz_summary = f"測驗結束！🎉  答對 {correct}/{total} 題！🎓\n"
    score = float(correct) / float(total)
    if score >= 0.8:
        quiz_summary += "恭喜你！你已經掌握了這堂課的知識！"
    else:
        quiz_summary += "加油！還有一些地方需要加強，別氣餒！"

    await message.channel.send(quiz_summary)
    await client.api_utils.store_message(user_id, 'assistant', quiz_summary)

    # Update mission status
    student_mission_info['current_step'] = 4
    student_mission_info['score'] = score
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Next step
    await send_reward_and_log(client, user_id, mission_id, 20)
    await handle_mission_end(client, message, student_mission_info)

async def process_quiz_question(client, message, quiz):
    question = quiz['question'].replace('？', ':grey_question:')
    embed = discord.Embed(
        title="小測驗",
        description=f"🌟 {question}",
        color=discord.Color.blue()
    )

    view = QuizView(quiz['options'], quiz['answer'])
    view.message = await message.channel.send(embed=embed, view=view)
    save_quiz_message_record(str(message.author.id), str(view.message.id), quiz['options'], quiz['answer'])

    # wait user's response
    await view.wait()
    if view.selected_option:
        if view.is_correct:
            await message.channel.send("回答正確！ 🎉\n\n")
            return 1
        else:
            explanation = view.selected_option['explanation']
            msg = f"正確答案是：{quiz['answer']}\n{explanation}\n\n"
            await message.channel.send(msg)
            return 0

    else: # timeout
        return -1

async def handle_mission_end(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = int(student_mission_info['mission_id'])
    is_photo_mission = student_mission_info['mission_id'] in config.photo_mission_list
    ending_msg = "請問你對今天的課程還有疑問嗎？不要害羞，跟加一說喔🐾\n\n"
    await message.channel.send(ending_msg)

    if is_photo_mission:
        ending_msg = "這堂課的最後一步很特別，我們有個超可愛的照片任務，你一定不能錯過！"
        view = ReplyOptionView(["進入照片任務!"])
        view.message = await message.channel.send(ending_msg, view=view)
        save_reply_option_record(user_id, str(view.message.id), ["進入照片任務!"])
        await client.api_utils.store_message(user_id, 'assistant', ending_msg)

        # wait user's response
        await view.wait()
        if view.selected_option is not None:
            client.logger.info(f"User {user_id} 進入照片任務!")
            await handle_photo_mission_start(client, user_id, mission_id)

async def handle_follow_up(client, message, student_mission_info):
    user_id = str(message.author.id)
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

