import discord
import os
import re

from discord.ui import View
from discord.errors import Forbidden
from types import SimpleNamespace
from bot.views.buttons import TerminateButton
from bot.views.quiz import QuizView
from bot.views.reply_options import ReplyOptionView, SingleReplyButtonView
from bot.handlers.utils import image_check, convert_image_to_preview, send_assistant_reply, send_assistant_reply_with_button
from bot.config import config

QUIZZES = {}

async def handle_video_mission(client, user_id, mission_id):
    user_id = str(user_id)
    client.logger.info(f"Start mission-{mission_id} (video) for user {user_id}.")
    # Get mission info
    mission = await client.api_utils.get_mission_info(mission_id)
    QUIZZES[user_id] = await client.openai_utils.generate_quiz(mission)

    # Load openai assistant and thread
    assistant_id = await client.openai_utils.load_assistant(mission)
    await client.api_utils.update_mission_assistant(mission_id, assistant_id)
    thread_id = client.openai_utils.load_thread()
    student_mission_info = mission
    student_mission_info['assistant_id'] = assistant_id
    student_mission_info['thread_id'] = thread_id
    student_mission_info['current_step'] = 1
    await client.api_utils.update_student_mission_status(
        user_id, mission_id, current_step=student_mission_info['current_step'], thread_id=student_mission_info['thread_id']
    )

    # Get baby info
    additional_info = await client.api_utils.get_baby_additional_info(user_id)
    await client.api_utils.store_message(user_id, 'assistant', additional_info)

    # Get greeting message
    hello_response = await client.openai_utils.get_greeting_message(assistant_id, thread_id, additional_info)
    hello_message = (
        "🎖育兒學習🎖\n"
        f"📑任務： {mission['mission_title']}\n"
        f"{mission['mission_type']}\n\n"
        f"{hello_response['message']}"
    )
    options = ["快速瀏覽文字重點", "影片播放"]

    # Send greeting message to user
    user = await client.fetch_user(user_id)
    view = ReplyOptionView(options)
    await user.send(hello_message, view=view)
    await client.api_utils.store_message(user_id, 'user', hello_message)
    await client.api_utils.update_student_mission_status(
        user_id, mission_id, current_step=student_mission_info['current_step']
    )

    # Wait for user reply
    await view.wait()
    if view.selected_option is not None:
        await client.api_utils.store_message(user_id, 'user', view.selected_option)
        student_mission_info['current_step'] += 1
        await client.api_utils.update_student_mission_status(
            user_id, mission_id, current_step=student_mission_info['current_step']
        )

        # Proceed to the next interaction
        selected_option = options[view.selected_option]
        message = SimpleNamespace(
            author=user,
            content=selected_option,
            channel=user.dm_channel
        )
        await handle_interaction_response(client, message, student_mission_info)

async def handle_video_mission_dm(client, message, student_mission_info):
    user_id = str(message.author.id)

    # 檢查是否為語音訊息 (ogg)
    if message.attachments and message.attachments[0].filename.endswith('ogg'):
        try:
            voice_message = await client.openai_utils.convert_audio_to_message(message)
            if not voice_message:
                client.logger.error(f"辨識語音失敗: {message}")
                await message.channel.send("辨識語音失敗，請再說一次")
                return
            else:
                message.content = voice_message['result']
        except Exception as e:
            client.logger.error(f"語音處理錯誤: {str(e)}")
            await message.channel.send("語音訊息處理時發生錯誤，請稍後再試")
            return

    # 檢查是否為圖片檔案
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.heic', '.heif')):
        try:
            photo_url = await client.s3_client.process_discord_attachment(message.attachments[0])
            mission = await client.api_utils.get_mission_info(student_mission_info['mission_id'])
            await client.api_utils.upload_baby_image(user_id, mission['mission_title'], photo_url)
            message.content = f"已收到任務照片"
        except Exception as e:
            client.logger.error(f"Failed to uplodad baby image: {str(e)}")
            await message.channel.send("上傳照片失敗，麻煩再試一次")
            return

    # 檢查是否為影片檔案
    elif message.attachments and message.attachments[0].filename.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.webm')):
        await message.channel.send("汪～影片太重啦～ 加一沒法幫你處理喔！")
        return

    if not message.content.strip():
        await message.channel.send("f無法處理您上傳的檔案內容，請輸入文字訊息或確保檔案格式正確後再試一次。如需幫助，請聯絡客服。")
        return

    # Store user message
    client.logger.info(f'{message.author}: {message.content}')
    await client.api_utils.store_message(user_id, 'user', message.content)

    await handle_interaction_response(client, message, student_mission_info)

async def handle_interaction_response(client, message, student_mission_info):
    user_id = str(message.author.id)
    current_step = student_mission_info['current_step']
    assistant_id = student_mission_info['assistant_id']
    thread_id = student_mission_info['thread_id']

    if current_step <= 2:
        student_mission_info['class_state'] = 'in_class'
        if message.content == "影片播放":
            await handle_video_played(client, message, student_mission_info)
        else:
            await handle_course_explanation(client, message, student_mission_info)
    elif (current_step == 3) or (student_mission_info.get('class_state') == 'quiz'):
        await handle_quiz(client, message, student_mission_info)
    elif (current_step == 4) or (student_mission_info['class_state'] == 'image'):
        await handle_photo_mission(client, message, student_mission_info)
    elif (current_step >= 5) or (student_mission_info['class_state'] == 'class_done'):
        await handle_follow_up(client, message, student_mission_info)
        return
    else:
        await handle_follow_up(client, message, student_mission_info)
        return

async def handle_course_explanation(client, message, student_mission_info):
    user_id = str(message.author.id)
    guidance_message = f"現在是「課程講解階段」，使用者的回答是：{message.content}"
    selected_option = await send_assistant_reply_with_button(client, message, student_mission_info, guidance_message)

    if student_mission_info['class_state'] == 'quiz' or (selected_option and '測驗' in selected_option):
        # Update mission stage
        student_mission_info['current_step'] += 1
        student_mission_info['class_state'] = 'quiz'
        await client.api_utils.update_student_mission_status(
            user_id, student_mission_info['mission_id'], current_step=student_mission_info['current_step']
        )
        await handle_interaction_response(client, message, student_mission_info)
    elif selected_option:
        message.content = selected_option
        await handle_course_explanation(client, message, student_mission_info)

async def handle_video_played(client, message, student_mission_info, option="我看完了"):
    user_id = str(message.author.id)
    if 'mission_video_contents' not in student_mission_info:
        mission = await client.api_utils.get_mission_info(student_mission_info['mission_id'])
        mission_video_contents = mission['mission_video_contents']
    else:
        mission_video_contents = student_mission_info['mission_video_contents']
    msg = (
        f"好的，來看看吧！這是教學影片的連結: {mission_video_contents}\n"
        "看完後記得告訴我喔~ 我們再進行小測驗！🙌"
    )
    view = SingleReplyButtonView(option)
    await message.channel.send(msg, view=view)
    await client.api_utils.store_message(user_id, 'assistant', msg)
    await view.wait()

    if view.selected is not None:
        student_mission_info['current_step'] += 1
        student_mission_info['class_state'] = 'quiz'
        client.user_viewed_video[(user_id, int(student_mission_info['mission_id']))] = 1
        await client.api_utils.store_message(user_id, 'user', option)
        await client.api_utils.update_student_mission_status(
            user_id, student_mission_info['mission_id'], current_step=student_mission_info['current_step']
        )
        await handle_interaction_response(client, message, student_mission_info)

async def handle_quiz(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = int(student_mission_info['mission_id'])

    # Get quiz
    if user_id not in QUIZZES:
        quizzes = client.openai_utils.mission_quiz[str(mission_id)]
    else:
        quizzes = QUIZZES[user_id]

    # Start quiz
    msg = f"準備進行小測驗囉！讓我來看看你對「{student_mission_info['mission_title']}」的知識掌握得怎麼樣呢 🐾✨"
    await message.channel.send(msg)
    await client.api_utils.store_message(user_id, 'assistant', msg)

    print(f"{quizzes}")
    total, correct = len(quizzes), 0
    for quiz in quizzes:
        correct += await process_quiz_question(client, message, quiz)

    quiz_summary = f"測驗結束！🎉  答對 {correct}/{total} 題！🎓"
    await message.channel.send(quiz_summary)
    await client.api_utils.store_message(user_id, 'assistant', quiz_summary)

    # Get assistant response
    quiz_summary_message = f"現在是「測驗階段」，{quiz_summary}"
    await send_assistant_reply(client, message, student_mission_info, quiz_summary_message)

    # Update mission stage
    student_mission_info['current_step'] += 1
    student_mission_info['class_state'] = 'image'
    await client.api_utils.update_student_mission_status(
        user_id, mission_id, current_step=student_mission_info['current_step']
    )

    # Proceed to the next interaction
    await handle_photo_mission(client, message, student_mission_info)

async def process_quiz_question(client, message, quiz):
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
        return 1
    else:
        explanation = quiz['options'][view.selected_option]['explanation']
        msg = f"正確答案是：{quiz['answer']}\n{explanation}\n\n"
        await message.channel.send(msg)
        return 0

async def handle_photo_mission_start(client, message, student_mission_info):
    user_id = str(message.author.id)
    if student_mission_info['reward'] == 20:
        # Skip photo mission if reward is 20
        student_mission_info['current_step'] += 1
        student_mission_info['class_state'] = 'class_done'
        await client.api_utils.update_student_mission_status(
            user_id, student_mission_info['mission_id'], current_step=student_mission_info['current_step']
        )
        # Proceed to the next interaction
        await handle_mission_end(client, message, student_mission_info)
    else:
        # Request assistant to create a photo task
        photo_task_request = "現在是「上傳照片階段」，請幫根據課程內容設計一個分享照片的任務"
        await send_assistant_reply(client, message, student_mission_info, photo_task_request)

async def handle_photo_mission(client, message, student_mission_info):
    user_id = str(message.author.id)
    if student_mission_info['reward'] == 20:
        # Skip photo mission if reward is 20
        student_mission_info['current_step'] += 1
        student_mission_info['class_state'] = 'class_done'
        await client.api_utils.update_student_mission_status(
            user_id, student_mission_info['mission_id'], current_step=student_mission_info['current_step']
        )
        await handle_mission_end(client, message, student_mission_info)
        return

    if message.content == "已收到任務照片":
        photo_task_feedback = "現在是「上傳照片階段」，已收到任務照片"
        await send_assistant_reply(client, message, student_mission_info, photo_task_feedback)

        student_mission_info['current_step'] += 1
        student_mission_info['class_state'] = 'class_done'
        await client.api_utils.update_student_mission_status(
            user_id, student_mission_info['mission_id'], current_step=student_mission_info['current_step']
        )

        # Proceed to the next interaction
        await handle_mission_end(client, message, student_mission_info)
    else:
        guidance_message = "目前是上傳照片階段哦！請上傳寶寶的照片，這樣我們可以一起完成這次任務！💪"
        await send_assistant_reply(client, message, student_mission_info, guidance_message)

async def handle_mission_end(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = int(student_mission_info['mission_id'])
    viewed_video = client.user_viewed_video.get((user_id, mission_id), False)
    if 'mission_video_contents' not in student_mission_info or 'mission_image_contents' not in student_mission_info:
        mission = await client.api_utils.get_mission_info(student_mission_info['mission_id'])
        student_mission_info.update(mission)

    ending_msg = ""
    if not viewed_video or student_mission_info['mission_image_contents'] != '':
        ending_msg += "\n我把這次的課程內容圖片和影片連結提供給妳，如果之後想再回味一下可以隨時查看喔！\n"
        if student_mission_info['mission_image_contents'] != '':
            for url in student_mission_info['mission_image_contents'].split(','):
                ending_msg += f"教學圖片: {convert_image_to_preview(url)}\n"
        if not viewed_video:
            ending_msg += f"影片 👉 {student_mission_info['mission_video_contents']}\n\n"

    ending_msg += "請問你對今天的課程還有疑問嗎？不要害羞，跟加一說喔🐾"
    view = View(timeout=None)
    view.add_item(
        TerminateButton(client, "結束課程", "結束課程，謝謝您的使用", student_mission_info)
    )
    await message.channel.send(ending_msg, view=view)
    await client.api_utils.store_message(user_id, 'assistant', ending_msg)

async def handle_follow_up(client, message, student_mission_info):
    user_id = str(message.author.id)
    guidance_message = f"目前是課程輔導階段，使用者的回答是：{message.content}"
    await send_assistant_reply(client, message, student_mission_info, guidance_message)

    view = View(timeout=None)
    view.add_item(
        TerminateButton(client, "結束課程", "結束課程，謝謝您的使用", student_mission_info)
    )
    # send bot response
    await message.channel.send(view=view)


