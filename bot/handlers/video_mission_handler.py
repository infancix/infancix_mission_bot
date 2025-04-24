import traceback
import discord
import os
import re
from types import SimpleNamespace
from datetime import datetime

from bot.views.quiz import QuizView
from bot.views.task_select_view import TaskSelectView
from bot.handlers.utils import get_user_id, send_reward_and_log
from bot.utils.message_tracker import (
    save_quiz_message_record,
    save_task_entry_record
)
from bot.config import config

async def handle_video_mission_dm(client, message, student_mission_info):
    user_id = str(message.author.id)
    student_mission_info['user_id'] = user_id
    if "收到使用者的照片" in message.content:
        await send_photo_summary(client, message, student_mission_info)
        return

    # Handle next step
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
        f"{mission['mission_type']}\n\n"
        f"🎥 影片教學\n"
        f"▶️ [{mission['mission_title']}]({mission['mission_video_contents']})\n\n"
    )
    image_urls = []
    if isinstance(mission.get('mission_image_contents'), str):
        image_urls = [s.strip() for s in mission['mission_image_contents'].split(',') if s.strip()]

    if image_urls:
        hello_message += f"🎥 影片教學\n ▶️"
        for url in image_urls:
            hello_message += f" [點擊]({url})"

    embed = discord.Embed(
        title=f"🎖{mission['mission_title']}🎖",
        description=hello_message,
        color=discord.Color.blue()
    )

    if is_photo_mission:
        view = TaskSelectView(client, "go_photo", mission_id)
        view.message = await user.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "go_photo", mission_id)
    else:
        view = TaskSelectView(client, "go_quiz", mission_id)
        view.message = await user.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "go_quiz", mission_id)
    
    await client.api_utils.store_message(user_id, 'assistant', hello_message)

async def handle_quiz_round(client, message, student_mission_info, current_round=0, correct=0):
    user_id = get_user_id(message)
    mission_id = int(student_mission_info['mission_id'])
    student_mission_info['current_step'] = 2
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Start quiz
    total_rounds = 3
    quiz = client.mission_quiz[str(mission_id)][current_round]
    question = quiz['question'].replace('？', ':grey_question:')
    task_request = f"🌟 **{question}**\n"
    for option in quiz['options']:
        task_request += f"{option['option']}\n"

    embed = discord.Embed(
        title=f"🏆 挑戰任務 - 第 {current_round+1} 題",
        description=task_request,
        color=discord.Color.purple()
    )

    view = QuizView(client, mission_id, current_round, correct, student_mission_info)
    view.message = await message.channel.send(embed=embed, view=view)

    # save record
    save_quiz_message_record(str(message.author.id), str(view.message.id), mission_id, current_round, correct)
    return

async def send_quiz_summary(interaction, correct, student_mission_info):
    user_id = get_user_id(interaction)
    mission_id = student_mission_info['mission_id']
    total = 3

    quiz_summary = (
        f"--------------------------\n\n"
        f"挑戰結束！🎉 答對 {correct}/{total} 題，"
    )
    if correct >= 2:
        quiz_summary += "恭喜掌握了這堂課的知識！🎓"
    else:
        quiz_summary += "加油！還有一些地方需要加強，別氣餒！"

    await interaction.channel.send(quiz_summary)
    await interaction.client.api_utils.store_message(user_id, 'assistant', quiz_summary)

    student_mission_info['current_step'] = 4
    student_mission_info['score'] = float(correct) / total
    await interaction.client.api_utils.update_student_mission_status(**student_mission_info)
    await send_reward_and_log(interaction.client, user_id, mission_id, 20)

async def handle_photo_round(client, message, student_mission_info):
    user_id = get_user_id(message)
    student_mission_info['current_step'] = 2
    await client.api_utils.update_student_mission_status(**student_mission_info)

    photo_task_request = (
        f"📸 請上傳「**{student_mission_info['photo_mission']}**」的照片！\n\n"
        f"🧩 這張回憶將化作【回憶碎片】，拼入寶寶的成長相冊 📖  \n"
    )

    embed = discord.Embed(
        title=student_mission_info['mission_title'],
        description=photo_task_request,
        color=discord.Color.orange()
    )
    message = await message.channel.send(embed=embed)
    await client.api_utils.store_message(user_id, 'assistant', photo_task_request)
    return

async def send_photo_summary(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    try:
        photo_url = await client.s3_client.process_discord_attachment(message.attachments[0].url)
        if 'mission_title' not in student_mission_info:
            mission = await client.api_utils.get_mission_info(mission_id)
            student_mission_info.update(mission)

        await client.api_utils.upload_baby_image(user_id, mission_id, student_mission_info['mission_title'], photo_url)
        await client.api_utils.store_message(user_id, 'user', f"收到任務照片: {photo_url}")

        assistant_id = config.MISSION_BOT_ASSISTANT
        thread_id = student_mission_info['thread_id']
        response = await client.openai_utils.get_reply_message(assistant_id, thread_id, "已收到任務照片")
        await message.channel.send(response['message'])
        await client.api_utils.store_message(user_id, assistant_id, response['message'])
        client.logger.info(f"Assitant response: {response}")

        # Mission Completed
        student_mission_info['current_step'] = 4
        student_mission_info['score'] = 1
        await client.api_utils.update_student_mission_status(**student_mission_info)
        await send_reward_and_log(client, user_id, mission_id, 100)

    except Exception as e:
        error_traceback = traceback.format_exc()
        client.logger.error(f"Failed to uplodad baby image: {str(e)}\n{error_traceback}")
        await message.channel.send("上傳照片失敗，麻煩再試一次")
        return

async def handle_follow_up(client, message, student_mission_info):
    user_id = get_user_id(message)
    mission_id = student_mission_info['mission_id']
    is_photo_mission = mission_id in config.photo_mission_list
    try:
        thread_id = student_mission_info['thread_id']
        assistant_id = config.MISSION_BOT_ASSISTANT
        async with message.channel.typing():
            response = await client.openai_utils.get_reply_message(assistant_id, thread_id, message.content)
            client.logger.info(f"Assitant response: {response}")

        if response.get('class_state') == 'done':
            await message.channel.send(response['message'])
        else:
            if is_photo_mission:
                view = TaskSelectView(client, "go_photo", mission_id)
                view.message = await message.channel.send(response['message'], view=view)
                save_task_entry_record(user_id, str(view.message.id), "go_photo", mission_id)
            else:
                view = TaskSelectView(client, "go_quiz", mission_id)
                view.message = await message.channel.send(response['message'], view=view)
                save_task_entry_record(user_id, str(view.message.id), "go_quiz", mission_id)

        await client.api_utils.store_message(user_id, 'assistant', response['message'])
            
    except Exception as e:
        await message.channel.send("加一不太懂，可以再試一次嗎？或是管理員協助處理。")

        