import asyncio
import discord
import os
import re
import traceback

from bot.config import config
from bot.handlers.utils import send_reward_and_log

photo_timers = {}

async def handle_photo_mission_start(client, user_id, mission_id):
    student_mission_info = await client.api_utils.get_student_mission_status(user_id, mission_id)
    await client.api_utils.update_student_current_mission(user_id, mission_id)
    student_mission_info = {
        **student_mission_info,
        'user_id': user_id,
        'assistant_id': config.MISSION_BOT_ASSISTANT,
        'current_step': 4,
    }

    if not student_mission_info.get('thread_id'):
        student_mission_info['thread_id'] = client.openai_utils.load_thread()
    await client.api_utils.update_student_mission_status(**student_mission_info)

    thread_id = student_mission_info['thread_id']
    assistant_id = student_mission_info['assistant_id']
    user = await client.fetch_user(user_id)
    photo_task_request = (
        f"✨ 挑戰任務已經快完成囉，就差這一步了！\n"
        f"--------------------------\n\n"
        f"📸 請上傳「**{student_mission_info['photo_mission']}**」的照片！\n\n"
        f"🧩 這張回憶將化作【回憶碎片】，拼入寶寶的成長相冊 📖  \n"
    )
    if '你' in student_mission_info['photo_mission']:
        photo_task_request += "💡 拍照時記得讓自己也入鏡喔，這份回憶不能少了你 💖\n"
    else:
        photo_task_request += "📎 點左下角「➕」按鈕，上傳照片吧！ \n"

    embed = discord.Embed(
        title=student_mission_info['mission_title'],
        description=photo_task_request,
        color=discord.Color.orange()
    )

    message = await user.send(embed=embed)
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
        await send_reward_and_log(client, user_id, mission_id, 100)
        # Remove timer
        if (user_id, str(mission_id)) in photo_timers:
            photo_timers[(user_id, str(mission_id))].cancel()
            del photo_timers[(user_id, str(mission_id))]

    except Exception as e:
        error_traceback = traceback.format_exc()
        client.logger.error(f"Failed to uplodad baby image: {str(e)}\n{error_traceback}")
        await message.channel.send("上傳照片失敗，麻煩再試一次")
        return

