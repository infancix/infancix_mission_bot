import discord
import os
import re
from pathlib import Path
from datetime import datetime
from loguru import logger
import schedule
import asyncio
from pydub import AudioSegment
from discord.ui import View
from discord.errors import Forbidden
from types import SimpleNamespace
from openai import OpenAI

from bot.views.buttons import TerminateButton
from bot.views.quiz import QuizView
from bot.views.reply_options import ReplyOptionView
from bot.config import config
from bot.utils.utils import (
    get_mission_info,
    store_message,
    get_baby_profile,
    get_baby_record,
    update_student_mission_status,
    get_student_is_in_mission,
    upload_baby_image
)

QUIZZES = {}

async def run_scheduler():
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

async def process_voice_message(gpt_client, message):
    try:
        voice_message = await gpt_client.convert_audio_to_message(message)
        if not voice_message:
            logger.error("辨識語音失敗")
            await message.channel.send("辨識語音失敗，請再說一次")
            return None
        else:
            return voice_message['result']

    except Exception as e:
        logger.error(f"語音處理錯誤: {e}")
        await message.channel.send("處理語音時發生錯誤，請再試一次")
        return None

async def greeting(client, user_id):
    greeting_message = """欸～哈囉，爸媽們，我是加一，你的「寶寶照護教室」導師，咱們今天一起穩穩的～ 💪

🍼 我是這麼幫你的：

量身打造：根據寶寶的日齡，給你最合適的養育方法，不多不少，剛剛好～

新手專屬：從換尿布到拍嗝，每一步都手把手教，這些事真的沒那麼難！

安心陪伴：別怕手忙腳亂，跟著我就行！咱們不追求完美，只求越做越好。

🐾 加一碎嘴：有啥不懂的記得問我，我知道你們忙，我來讓一切簡單點！

🌟 第一堂課馬上開始，交給我穩穩的～

關於任務佈告欄，以下我想等妳回來一起討論:
"""


async def handle_start_mission(client, user_id, mission_id):
    mission_id = int(mission_id)
    if mission_id in [32, 39, 45, 54, 67]:
        await handle_record_mission(client, user_id, mission_id)
    else:
        await handle_video_mission(client, user_id, mission_id)

async def handle_record_mission(client, user_id, mission_id):
    user = await client.fetch_user(user_id)
    mission = await get_mission_info(mission_id)
    user_data = {
        'mission_id': mission_id,
        'total_steps': 2,
        'reward': mission['reward']
    }
    current_step = 1
    hello_message = f"""親愛的家長，
讓加一🐾幫你確認一下，這兩週您是否有定期在寶寶檔案室紀錄寶寶的日常呢？
這樣我們可以更好地為您和寶寶提供貼心的支持喔💪
"""
    await user.send(hello_message)
    await store_message(str(user_id), 'assistant', datetime.now().isoformat(), hello_message)
    await update_student_mission_status(user_id, mission_id, user_data['total_steps'], current_step) # send message

    exists_baby_records = await get_baby_record(user_id)
    if exists_baby_records:
        msg = "很棒！過去兩週已有作息紀錄，繼續保持 !"
        view = View(timeout=None)
        view.add_item(
            TerminateButton(client, "結束諮詢", "諮詢結束，謝謝您的使用", user_data)
        )
        await user.send(msg, view=view)
        await store_message(str(user_id), 'assistant', datetime.now().isoformat(), msg)
    else:
        msg = "過去兩週未見寶寶作息紀錄，請至寶寶檔案室補上紀錄以完成任務。\n <@!1165875139553021995>"
        await user.send(msg)
        await store_message(str(user_id), 'assistant', datetime.now().isoformat(), msg)
    return

async def handle_video_mission(client, user_id, mission_id):
    mission = await get_mission_info(mission_id)
    user = await client.fetch_user(user_id)
    additional_info = await get_baby_profile(user_id)

    assistant_id = await client.gpt_client.load_assistant(mission)
    thread_id = client.gpt_client.load_thread()

    # Call API to store medal status
    if mission.get('reward') == 100:
        total_steps, current_step = 4, 0 # class, quiz, upload_image
    else:
        total_steps, current_step = 3, 0 # class, quiz

    await update_student_mission_status(user_id, mission_id, total_steps, current_step, thread_id, assistant_id)

    # Create quizzes for speed up mission
    QUIZZES[str(user_id)] = await client.gpt_client.generate_quiz(mission)
    print(QUIZZES)

    hello_response = await client.gpt_client.get_greeting_message(assistant_id, thread_id, additional_info)
    hello_message = f"""🎖育兒學習🎖

📑任務： {mission['mission_title']}
{mission['mission_type']}

{hello_response['message']}
"""

    # Store assistant message
    await store_message(str(user_id), 'assistant', datetime.now().isoformat(), additional_info)

    try:
        if not hello_response.get('reply_options', None):
            await user.send(hello_message)
            await store_message(str(user_id), 'assistant', datetime.now().isoformat(), hello_message)
            return

        else:
            view = ReplyOptionView(hello_response['reply_options'])
            await user.send(hello_message, view=view)
            await store_message(str(user_id), 'assistant', datetime.now().isoformat(), hello_message)
            await view.wait()
            if view.selected_option is not None:
                selected_reply = hello_response['reply_options'][view.selected_option]

                message = SimpleNamespace(
                    author=user,
                    content=selected_reply,
                    channel=user.dm_channel
                )

                user_data = {
                    'mission_id': str(mission_id),
                    'assistant_id': assistant_id,
                    'thread_id': thread_id,
                    'total_steps': str(total_steps),
                    'current_step': str(current_step)
                }
                await handle_interaction_response(client, message, selected_reply, user_data)
                return

    except Forbidden as e:
        err_msg = f'Forbidden to send DM to {user_id}: {e}\nThe user that the bot tried to message is no longer in the discord server or that they don\'t allow DM\'s'
        logger.error(err_msg)

        channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        await channel.send(err_msg)
        return

async def handle_dm(client, message):
    user_id = str(message.author.id)
    user_message = message.content

    student_in_mission = await get_student_is_in_mission(user_id)
    if student_in_mission.get('data') == {}:
        await message.channel.send("加一現在不在喔，有問題可以找 <@1287675308388126762>")
        return

    user_data = student_in_mission['data']
    if not user_data:
        return

    # 檢查是否為語音訊息 (ogg)
    if message.attachments and message.attachments[0].filename.endswith('ogg'):
        user_message = await process_voice_message(client.gpt_client, message)

    # 檢查是否為圖片檔案
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.heic', '.heif')):
        #image_bytes = await image_attachment.read()
        try:
            photo_url = await client.s3_client.process_discord_attachment(message.attachments[0])
            mission = await get_mission_info(user_data['mission_id'])
            await upload_baby_image(user_id, mission['mission_title'], photo_url, datetime.now().date())
            user_message = f"已收到任務照片"
        except Exception as e:
            logger.error(f"Failed to uplodad baby image: {str(e)}")
            await message.channel.send("上傳照片失敗，麻煩再試一次")
            return

    # 檢查是否為影片檔案
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
        user_message = '收到使用者傳送的影片'
        await message.channel.send("汪～影片太重啦～ 加一沒法幫你處理喔！")
        return

    if not user_message:
        await message.channel.send("f無法處理您上傳的檔案內容，請輸入文字訊息或確保檔案格式正確後再試一次。如需幫助，請聯絡客服。")
        return

    # Store user message
    logger.info(f'{message.author}: {user_message}')
    await store_message(user_id, 'user', datetime.now().isoformat(), user_message)

    async with message.channel.typing():
        response = await client.gpt_client.get_reply_message(user_data['assistant_id'], user_data['thread_id'], user_message)
    await handle_response(client, message, response, user_data)

async def handle_response(client, message, response, user_data):
    user_id = str(message.author.id)
    current_step = int(user_data['current_step'])
    if response['class_state'] in ['hello', 'in_class', 'in_video']:
        if response.get('reply_options', None):
            view = ReplyOptionView(response['reply_options'])
            await message.channel.send(response['message'], view=view)
            await store_message(user_id, 'assistant', datetime.now().isoformat(), response['message'])
            await view.wait()
            if view.selected_option is not None:
                selected_reply = response['reply_options'][view.selected_option]
                await handle_interaction_response(client, message, selected_reply, user_data)
        else:
            await message.channel.send(response['message'])
            await store_message(user_id, 'assistant', datetime.now().isoformat(), response['message'])

    elif response['class_state'] == 'quiz':
        await update_student_mission_status(user_id, user_data['mission_id'], user_data['total_steps'], current_step+1) # finish class
        await handle_quiz(client, message, user_data, response)

    elif response['class_state'] == 'image':
        await update_student_mission_status(user_id, user_data['mission_id'], user_data['total_steps'], current_step+1) # finish quiz
        await message.channel.send(response['message'])
        await store_message(user_id, 'assistant', datetime.now().isoformat(), response['message'])

    elif response['class_state'] == 'class_done':
        await update_student_mission_status(user_id, user_data['mission_id'], user_data['total_steps'], current_step+1) # finish quiz or image
        await handle_terminate_button(client, message, response, user_data)

    else:
        await message.channel.send(response['message'])
        await store_message(user_id, 'assistant', datetime.now().isoformat(), response['message'])

def image_check(m):
    # Ensure the message is in the same DM and has an attachment
    return (
        m.author == message.author
        and m.channel == message.channel
        and m.attachments
        and any(m.attachments[0].filename.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif'])
    )

async def handle_interaction_response(client, message, user_reply, user_data):
    user_id = str(message.author.id)

    await store_message(user_id, 'user', datetime.now().isoformat(), user_reply)

    async with message.channel.typing():
        response = await client.gpt_client.get_reply_message(
            user_data['assistant_id'],
            user_data['thread_id'],
            user_reply
        )
    await handle_response(client, message, response, user_data)

async def handle_quiz(client, message, user_data, response):
    user_id = str(message.author.id)
    mission_id = int(user_data['mission_id'])

    quizzes = QUIZZES.get(user_id, None)
    if not quizzes:
        mission = await get_mission_info(mission_id)
        async with message.channel.typing():
            quizzes = await client.gpt_client.generate_quiz(mission)

    print(f"{len(quizzes)}\n{quizzes}")
    total, correct = len(quizzes), 0
    for quiz in quizzes:
        question = quiz['question'].replace('？', ':grey_question:')
        embed = discord.Embed(
            title="小測驗",
            description=f"🌟 {question}",
            color=discord.Color.blue()
        )
        view = QuizView(quiz['options'], timeout=None)
        await message.channel.send(embed=embed, view=view)

        # wait user's response
        await view.wait()

        if quiz['options'][view.selected_option]['option'][0] == quiz['answer']:
            await message.channel.send("回答正確！ 🎉\n\n")
            correct += 1
        else:
            explanation = quiz['options'][view.selected_option]['explanation']
            msg = f"正確答案是：{quiz['answer']}\n{explanation}\n\n"
            await message.channel.send(msg)

    quiz_summary = f"測驗結束！🎉 \n答對 {correct}/{total} 題！🎓"
    await store_message(user_id, 'assistant', datetime.now().isoformat(), quiz_summary)
    await handle_interaction_response(client, message, quiz_summary, user_data)

async def handle_terminate_button(client, message, response, user_data):
    user_id = str(message.author.id)
    mission = await get_mission_info(user_data['mission_id'])
    user_data['reward'] = mission['reward']
    view = View(timeout=None)
    view.add_item(
        TerminateButton(client, "結束諮詢", "諮詢結束，謝謝您的使用", user_data)
    )
    # send bot response
    await message.channel.send(response['message'], view=view)
    await store_message(user_id, 'assistant', datetime.now().isoformat(), response['message'])

