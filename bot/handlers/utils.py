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

from bot.constants import MISSIONS
from bot.views.buttons import TerminateButton
from bot.views.quiz import QuizView
from bot.views.reply_options import ReplyOptionView
from bot.config import config
from bot.utils.utils import (
    store_message,
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
        user_message = await gpt_client.convert_audio_to_message(message)
        if not user_message:
            logger.error("辨識語音失敗")
            await message.channel.send("辨識語音失敗，請再說一次")
            return None
        return user_message
    except Exception as e:
        logger.error(f"語音處理錯誤: {e}")
        await message.channel.send("處理語音時發生錯誤，請再試一次")
        return None


async def handle_start_mission(client, user_id, mission_id):
    mission_id = int(mission_id)
    user = await client.fetch_user(user_id)
    additional_info = await get_baby_record(user_id)

    assistant_id = client.gpt_client.load_assistant(MISSIONS.get(mission_id))
    thread_id = client.gpt_client.load_thread()

    # Call API to store medal status
    if MISSIONS[mission_id].get('reward') == 100:
        total_steps, current_step = 4, 0 # class, quiz, upload_image
    else:
        total_steps, current_step = 3, 0 # class, quiz

    await update_student_mission_status(user_id, mission_id, total_steps, current_step, thread_id, assistant_id)

    # Create quizzes for speed up mission
    QUIZZES[user_id] = client.gpt_client.generate_quiz(MISSIONS[mission_id])

    hello_response = client.gpt_client.get_greeting_message(assistant_id, thread_id, additional_info)
    # Store assistant message
    await store_message(str(user_id), 'assistant', datetime.now().isoformat(), additional_info)

    try:
        if not hello_response.get('reply_options', None):
            await user.send(hello_response['message'])
            await store_message(str(user_id), 'assistant', datetime.now().isoformat(), hello_response['message'])
            return

        else:
            view = ReplyOptionView(hello_response['reply_options'])
            await user.send(hello_response['message'], view=view)
            await store_message(str(user_id), 'assistant', datetime.now().isoformat(), hello_response['message'])
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
                await handle_reply_option_message(client, message, selected_reply, user_data)
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
        return

    user_data = student_in_mission.get('data', {})
    if not user_data:
        return

    if message.attachments and message.attachments[0].filename.endswith('ogg'):
        user_message = await process_voice_message(client.gpt_client, message)
        if not user_message:
            return
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
        #image_bytes = await image_attachment.read()
        try:
            photo_url = await client.s3_client.process_discord_attachment(message.attachments[0])
            await upload_baby_image(user_id, MISSIONS[user_data['mission_id']]['mission_title'], photo_url, datetime.now().date())
            user_message = f"已收到任務照片"
        except Exception as e:
            logger.error(f"Failed to uplodad baby image: {str(e)}")
            await message.channel.send("上傳照片失敗，麻煩再試一次")
            return

    # Store user message
    logger.info(f'{message.author}: {user_message}')
    await store_message(user_id, 'user', datetime.now().isoformat(), user_message)

    async with message.channel.typing():
        response = client.gpt_client.get_reply_message(user_data['assistant_id'], user_data['thread_id'], user_message)
    await handle_response(client, message, response, user_data)

async def handle_response(client, message, response, user_data):
    user_id = str(message.author.id)

    if response['class_state'] in ['hello', 'in_class']:
        if response.get('reply_options', None):
            view = ReplyOptionView(response['reply_options'])
            await message.channel.send(response['message'], view=view)
            await store_message(user_id, 'assistant', datetime.now().isoformat(), response['message'])
            await view.wait()
            if view.selected_option is not None:
                selected_reply = response['reply_options'][view.selected_option]
                await handle_reply_option_message(client, message, selected_reply, user_data)
        else:
            await message.channel.send(response['message'])
            await store_message(user_id, 'assistant', datetime.now().isoformat(), response['message'])

    elif response['class_state'] == 'quiz':
        await update_student_mission_status(user_id, user_data['mission_id'], user_data['total_steps'], 1) # finish class
        await handle_quiz(client, message, user_data, response)

    elif response['class_state'] == 'image':
        await update_student_mission_status(user_id, user_data['mission_id'], user_data['total_steps'], 2) # finish quiz
        await handle_image(client, message, user_data, response)

    elif response['class_state'] == 'class_done':
        await update_student_mission_status(user_id, user_data['mission_id'], user_data['total_steps'], 3) # finish quiz or image
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

async def handle_reply_option_message(client, message, user_reply, user_data):
    user_id = str(message.author.id)

    await store_message(user_id, 'user', datetime.now().isoformat(), user_reply)

    async with message.channel.typing():
        response = client.gpt_client.get_reply_message(
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
        async with message.channel.typing():
            quizzes = client.gpt_client.generate_quiz(MISSIONS[mission_id])

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
            await message.channel.send("回答正確！ 🎉")
            correct += 1
        else:
            explanation = quiz['options'][view.selected_option]['explanation']
            await message.channel.send(explanation)

    quiz_summary = f"測驗結束！總題數: {total};\n回答正確題數: {correct} 🎓"

    # get gpt response after quiz
    quiz_response = client.gpt_client.get_reply_message(user_data['assistant_id'], user_data['thread_id'], quiz_summary)

    # send bot response
    await message.channel.send(quiz_summary + '\n\n' + quiz_response['message'])

    await store_message(user_id, 'assistant', datetime.now().isoformat(), quiz_summary)
    await store_message(user_id, 'assistant', datetime.now().isoformat(), quiz_response['message'])

async def handle_terminate_button(client, message, response, user_data):
    user_id = str(message.author.id)
    view = View(timeout=None)
    view.add_item(
        TerminateButton(client, "結束諮詢", "諮詢結束，謝謝您的使用", user_data)
    )

    # send bot response
    await message.channel.send(response['message'], view=view)
    await store_message(user_id, 'assistant', datetime.now().isoformat(), response['message'])

