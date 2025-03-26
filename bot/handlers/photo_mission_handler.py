import discord
import os
import re
import traceback

from bot.views.reply_options import ReplyOptionView
from bot.config import config
from bot.views.terminate_class import TerminateClassView
import asyncio

photo_timers = {}

async def handle_photo_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    student_mission_info = await client.api_utils.get_student_mission_status(user_id, mission_id)
    await client.api_utils.update_student_current_mission(user_id, mission_id)
    mission_instructions = f"""
        這是這次課程的主題和照片任務，請跟親切的提醒使用者，如果拍照的時候不要忘記把自己拍進去，這是你們共同的回憶喔!
        ## 課程內容：{student_mission_info['mission_title']}
        ## 照片任務: {student_mission_info['photo_mission']}

        f"📸 請上傳「**{student_mission_info['photo_mission']}**」的照片！\n"
        f"💡 這是最後一步，上傳即可完成本次課程！🎉\n"
        "📎 **點擊對話框左側「+」上傳**"
    """

    student_mission_info = {
        **student_mission_info,
        'user_id': user_id,
        'assistant_id': config.PHOTO_TASK_ASSISTANT,
        'current_step': 4,
    }
    if not student_mission_info.get('thread_id'):
        student_mission_info['thread_id'] = client.openai_utils.load_thread()
    await client.api_utils.update_student_mission_status(**student_mission_info)

    thread_id = student_mission_info['thread_id']
    assistant_id = student_mission_info['assistant_id']
    client.openai_utils.add_task_instruction(thread_id, mission_instructions)

    user = await client.fetch_user(user_id)
    photo_reminder = (
        "💡 拍照小提醒：記得自己也要入鏡，你是寶寶最珍貴的人，少了你，這份回憶就不完整。\n"
        if '你' in student_mission_info['photo_mission'] else ""
    )
    photo_task_request = (
        f"📸 請上傳「**{student_mission_info['photo_mission']}**」的照片！\n"
        f"💡 這是最後一步，上傳即可完成本次課程！🎉\n"
        f"{photo_reminder}"
        f"📎 **點擊對話框左側「+」上傳**"
    )

    message = await user.send(photo_task_request)
    await client.api_utils.store_message(user_id, 'assistant', photo_task_request)
    task = asyncio.create_task(photo_reminder_task(client, user_id, mission_id, message.id))
    photo_timers[(user_id, str(mission_id))] = task

    print("photo_timers: ", photo_timers)
    return

async def photo_reminder_task(client, user_id, mission_id, message_id):
    await asyncio.sleep(14400)
    student_mission_info = await client.api_utils.get_student_mission_status(user_id, mission_id)
    if student_mission_info['mission_status'] == "Incompleted":
        user = await client.fetch_user(user_id)

        original_message = await user.fetch_message(message_id)
        await original_message.reply("📸 還沒上傳照片嗎？你可以隨時透過儀表板補交哦！🎯")
        await client.api_utils.store_message(user_id, 'assistant', "📸 還沒上傳照片嗎？你可以隨時透過儀表板補交哦！🎯")

async def handle_photo_mission(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']
    try:
        photo_url = await client.s3_client.process_discord_attachment(message.attachments[0])
        if 'mission_title' not in student_mission_info:
            mission = await client.api_utils.get_mission_info(mission_id)
            student_mission_info.update(mission)

        await client.api_utils.upload_baby_image(user_id, mission_id, student_mission_info['mission_title'], photo_url)
        await client.api_utils.store_message(user_id, 'user', f"收到任務照片: {photo_url}")

        assistant_id = config.PHOTO_TASK_ASSISTANT
        thread_id = student_mission_info['thread_id']
        response = await client.openai_utils.get_reply_message(assistant_id, thread_id, "已收到任務照片")
        client.logger.info(f"Assitant response: {response}")

        if 'message' in response:
            view = TerminateClassView(client, student_mission_info, reward=100)
            view.message = await message.channel.send(response['message'], view=view)
            await client.api_utils.store_message(user_id, 'assistant', response['message'])

        # Remove timer
        if (user_id, str(mission_id)) in photo_timers:
            photo_timers[(user_id, str(mission_id))].cancel()
            del photo_timers[(user_id, str(mission_id))]

    except Exception as e:
        error_traceback = traceback.format_exc()
        client.logger.error(f"Failed to uplodad baby image: {str(e)}\n{error_traceback}")
        await message.channel.send("上傳照片失敗，麻煩再試一次")
        return

