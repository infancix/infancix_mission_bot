import discord
import os
import re

from discord.errors import Forbidden
from types import SimpleNamespace
from bot.views.quiz import QuizView
from bot.views.reply_options import ReplyOptionView
from bot.views.terminate_class import TerminateClassView
from bot.views.photo_task import OpenPhotoTaskView
from bot.handlers.photo_mission_handler import handle_photo_mission
from bot.handlers.utils import image_check, convert_image_to_preview
from bot.config import config

async def handle_video_mission_dm(client, message, student_mission_info):
    user_id = str(message.author.id)
    student_mission_info['user_id'] = user_id

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
        await handle_photo_mission(client, message, student_mission_info)
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
    if current_step <= 2:
        if message.content == "影片播放":
            await handle_video_played(client, message, student_mission_info)
        else:
            await handle_course_explanation(client, message, student_mission_info)
    elif current_step == 3:
        await handle_quiz(client, message, student_mission_info)
    else:
        await handle_follow_up(client, message, student_mission_info)

async def handle_video_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    mission_instructions = f"""
    這是這次課程的主題和課程影片字幕：
    ## 課程內容：{mission['mission_title']}
    ## 影片字幕:
    {mission['transcription']}
    """

    thread_id = client.openai_utils.load_thread()
    client.openai_utils.add_task_instruction(thread_id, mission_instructions)

    # Get baby info
    baby_info = await client.api_utils.get_baby_additional_info(user_id)
    client.openai_utils.add_task_instruction(thread_id, baby_info)

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
    message = SimpleNamespace(author=user, channel=user.dm_channel, content=None)

    hello_request = "現在是「Hello階段」，請親切的問候使用者"
    selected_option = await send_assistant_reply_with_button(client, message, student_mission_info, hello_request, reply_options=["文字互動學習", "影片播放"])
    if selected_option:
        await client.api_utils.store_message(user_id, 'user', selected_option)
        student_mission_info['current_step'] += 1
        await client.api_utils.update_student_mission_status(**student_mission_info)

        if selected_option == "影片播放":
            await handle_video_played(client, message, student_mission_info)
        else:
            message.content = selected_option
            await handle_course_explanation(client, message, student_mission_info)

async def handle_course_explanation(client, message, student_mission_info, options=['下一步', '不太懂欸？']):
    user_id = str(message.author.id)
    guidance_message = f"現在是「課程講解階段」，使用者的回答是：{message.content}"
    selected_option = await send_assistant_reply_with_button(client, message, student_mission_info, guidance_message, reply_options=options)

    if student_mission_info['class_state'] == 'quiz' or (selected_option and '測驗' in selected_option):
        student_mission_info['current_step'] = 3
        await client.api_utils.update_student_mission_status(**student_mission_info)
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

    reply_message = (
        f"好的，來看看吧！這是教學影片的連結: {mission_video_contents}\n"
        "看完後記得告訴我喔~ 我們再進行小測驗！🙌"
    )
    view = ReplyOptionView([option])
    view.message = await message.channel.send(reply_message, view=view)
    await client.api_utils.store_message(user_id, 'assistant', reply_message)
    await view.wait()

    if view.selected_option is not None:
        student_mission_info['current_step'] = 3
        client.user_viewed_video[(user_id, int(student_mission_info['mission_id']))] = 1
        await client.api_utils.store_message(user_id, 'user', view.selected_option)
        await client.api_utils.update_student_mission_status(**student_mission_info)
        await handle_interaction_response(client, message, student_mission_info)

async def handle_quiz(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = int(student_mission_info['mission_id'])

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
            await user.send(timeout_msg)
            await client.api_utils.store_message(user_id, 'assistant', timeout_msg)
            await client.api_utils.update_student_mission_status(user_id, student_mission_info['mission_id'], is_paused=True)
            return

    quiz_summary = f"測驗結束！🎉  答對 {correct}/{total} 題！🎓"
    await message.channel.send(quiz_summary)
    await client.api_utils.store_message(user_id, 'assistant', quiz_summary)
    student_mission_info['current_step'] = 4
    student_mission_info['score'] = float(correct) / float(total)
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Get assistant response
    quiz_summary_message = f"{quiz_summary}"
    await send_assistant_reply_with_button(client, message, student_mission_info, quiz_summary_message, reply_options=None)

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
        ending_msg += "請問你對今天的課程還有疑問嗎？不要害羞，跟加一說喔🐾\n\n"

    if student_mission_info['mission_id'] in config.photo_mission_list:
        ending_msg += "這堂課的最後一步很特別，我們有個超可愛的照片任務，你一定不能錯過！"
        view = OpenPhotoTaskView(client, student_mission_info)
    else:
        view = TerminateClassView(client, student_mission_info)

    view.message = await message.channel.send(ending_msg, view=view)
    await client.api_utils.store_message(user_id, 'assistant', ending_msg)

async def handle_follow_up(client, message, student_mission_info):
    user_id = str(message.author.id)
    guidance_message = f"目前是課程輔導階段，使用者的回答是：{message.content}"
    await send_assistant_reply_with_button(client, message, student_mission_info, guidance_message, reply_options=None)

    view = TerminateClassView(client, student_mission_info)
    view.message = await message.channel.send(view=view)

async def send_assistant_reply_with_button(client, message, student_mission_info, content, reply_options=None):
    """
    Sends a reply from the assistant with interactive buttons and stores the response.
    """
    thread_id = student_mission_info['thread_id']
    assistant_id = student_mission_info.get('assistant_id') if student_mission_info.get('assistant_id') else config.MISSION_BOT_ASSISTANT
    class_state = config.class_step[student_mission_info['current_step']] if student_mission_info['current_step'] in config.class_step else "課程結束階段"
    client.logger.info(f"(Mission-{student_mission_info['mission_id']}/User-{message.author.id}): [{class_state}] {content}")
    try:
        async with message.channel.typing():
            response = await client.openai_utils.get_reply_message(assistant_id, thread_id, content)
            client.logger.info(f"Assitant response: {response}")

        if 'message' in response:
            if reply_options is None:
                await message.channel.send(response['message'])
                await client.api_utils.store_message(str(message.author.id), 'assistant', response['message'])
            else:
                if 'reply_options' in response and len(response['reply_options']) > 0:
                    reply_options = response['reply_options']

                if 'class_state' in response:
                    student_mission_info['class_state'] = response['class_state']
                    if response['class_state'] == 'quiz':
                        student_mission_info['current_step'] = 3
                        reply_options = ['進入小測驗']

                view = ReplyOptionView(reply_options)
                view.message = await message.channel.send(response['message'], view=view)
                await client.api_utils.store_message(str(message.author.id), 'assistant', response['message'])

                # Wait for user interaction
                await view.wait()

                # Handle user selection
                if view.selected_option is not None:
                    return view.selected_option
                else:
                    client.logger.info(f"User did not select any option: {message.author.id}")
        else:
            await message.channel.send("加一不太懂，可以再試一次嗎？或是管理員協助處理。")

    except Exception as e:
        client.logger.error(f"Failed to get assistant reply with button: {str(e)}")
        await message.channel.send("加一不太懂，可以再試一次嗎？或是管理員協助處理。")

