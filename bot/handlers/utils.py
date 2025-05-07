import re
import discord
import schedule
import asyncio
import datetime
import functools
import traceback

from bot.config import config
from bot.utils.message_tracker import (
    load_quiz_message_records,
    load_task_entry_records,
    load_photo_view_records,
    save_photo_view_record
)
from bot.views.task_select_view import TaskSelectView
from bot.views.growth_photo import GrowthPhotoView
from bot.views.quiz import QuizView

async def run_scheduler():
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

def scheduled_job(client):
    today = datetime.datetime.now()

    # Daily job
    asyncio.create_task(daily_job(client))

async def daily_job(client):
    client.logger.debug('Running job now...')

    target_channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if target_channel is None or not isinstance(target_channel, discord.TextChannel):
        raise Exception('Invalid channel')

    student_list = await client.api_utils.get_all_students_mission_notifications()
    for user_id in student_list:
        try:
            couser_info = student_list[user_id].get('todays_course', {})
            if couser_info and couser_info['mission_status'] != 'Completed':
                mission_id = couser_info['mission_id']
                await target_channel.send(f"START_MISSION_{mission_id} <@{user_id}>")
            await asyncio.sleep(2)
        except Exception as e:
            client.logger.error(f"Failed to send control panel to user: {user_id}, {str(e)}")

async def handle_greeting_job(client, user_id = None):
    hello_message = (
        "哈囉～新手爸媽們！我是「加一」🐾 任務佈告欄的助手\n"
        "等寶寶出生29天後, 會自動發送任務給你\n"
        "輸入 /任務佈告欄 可以查看任務進度🏆\n"
    )

    if user_id == None:
        student_list = await client.api_utils.fetch_student_list()
    else:
        student_list = [{'discord_id': user_id}]

    # start greeting
    client.logger.info(f"Start greeting job: {len(student_list)} student")
    for user in student_list:
        user_id = user['discord_id']
        user = await client.fetch_user(user_id)
        await user.send(hello_message)
        client.logger.info(f"Send hello message to user {user_id}")
        await asyncio.sleep(3)

    return

async def load_task_entry_messages(client):
    records = load_task_entry_records()
    for user_id, message_data in records.items():
        try:
            channel = await client.fetch_user(user_id)
            for record in message_data:
                message = await channel.fetch_message(int(record['message_id']))
                view = TaskSelectView(client, record['task_type'], int(record['mission_id']))
                await message.edit(view=view)
            client.logger.info(f"✅ Restore task-entry for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore task entry for {user_id}: {e}")

async def load_quiz_message(client):
    records = load_quiz_message_records()
    for user_id, (message_id, mission_id, current_round, correct_cnt) in records.items():
        try:
            channel = await client.fetch_user(user_id)
            student_mission_info = await client.api_utils.get_student_mission_status(user_id, mission_id)
            student_mission_info['user_id'] = user_id
            message = await channel.fetch_message(int(message_id))
            view = QuizView(client, mission_id, current_round, correct_cnt, student_mission_info)
            await message.edit(view=view)
            client.logger.info(f"✅ Restored quiz for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore quiz for {user_id}: {e}")

async def load_photo_view_messages(client):
    records = load_photo_view_records()
    for user_id, (message_id, mission_id, photo_info) in records.items():
        try:
            channel = await client.fetch_user(user_id)
            message = await channel.fetch_message(int(message_id))
            view = GrowthPhotoView(client, user_id, photo_info)
            await message.edit(view=view)
            client.logger.info(f"✅ Restored photo view for user {user_id}")
        except Exception as e:
            client.logger.warning(f"⚠️ Failed to restore photo view for {user_id}: {e}")

async def handle_add_photo_job(client, user_id, mission_id):
    student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)
    if not student_mission_info or student_mission_info['mission_status'] == 'Completed':
        await handle_notify_photo_ready_job(client, user_id, mission_id)
    else:
        if user_id not in client.growth_album:
            client.growth_album[user_id] = []
        client.growth_album[user_id].append(mission_id)
        client.logger.info(f"Add photo to growth album for user {user_id}")
        return

async def handle_notify_photo_ready_job(client, user_id, mission_id):
    notify_message = (
        f"👋 Hello 這是你製作的回憶相冊內頁，希望你喜歡 ❤️\n"
        f"如果修改的話，點選下方按鈕就可以囉!\n"
    )
    photo_info = await client.api_utils.get_baby_images(user_id, mission_id)
    file = discord.File(f"../canva_exports/{photo_info['design_id']}.png")
    try:
        view = GrowthPhotoView(client, user_id, photo_info)
        user = await client.fetch_user(user_id)
        message = await user.send(notify_message, file=file, view=view)
        save_photo_view_record(user_id, str(message.id), mission_id)
        client.logger.info(f"Send photo message to user {user_id}")
        await client.api_utils.store_message(user_id, 'assistant', notify_message)
    except Exception as e:
        client.logger.error(f"Failed to send photo message to user {user_id}: {e}")
    return

async def send_reward_and_log(client, user_id, mission_id, reward):
    target_channel = await client.fetch_user(user_id)
    is_photo_mission = mission_id in config.photo_mission_list

    ending_msg = (
        f"🎁 你獲得了以下獎勵：\n"
        f"> 🪙 金幣 Coin：+{reward}\n"
    )
    # Send the ending message to the user
    if is_photo_mission:
        mission = await client.api_utils.get_mission_info(int(mission_id))
        ending_msg += f"> 🧩 回憶碎片：1 片《{mission['photo_mission']}》\n" if is_photo_mission else ""

    embed = discord.Embed(
        title="🎉 任務完成！",
        description=ending_msg,
        color=discord.Color.green()
    )
    await target_channel.send(embed=embed)
    await client.api_utils.store_message(user_id, 'assistant', ending_msg)

    # Add gold to user
    await client.api_utils.add_gold(
        user_id,
        gold=int(reward)
    )

    # Send log to Background channel
    channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise Exception('Invalid channel')

    msg_task = f"MISSION_{mission_id}_FINISHED <@{user_id}>"
    await channel.send(msg_task)

    # Send growth photo results
    await send_growth_photo_results(client, user_id)

async def send_growth_photo_results(client, user_id):
    if client.growth_album.get(user_id, []):
        mission_id = client.growth_album[user_id].pop()
        await handle_notify_photo_ready_job(client, user_id, mission_id)

def add_task_instructions(client, mission, thread_id):
    mission_instructions = f"""
        這是這次課程的主題和課程影片字幕：
        ## 課程內容：{mission['mission_title']}
        ## 影片字幕: {mission['transcription']}
    """
    client.openai_utils.add_task_instruction(thread_id, mission_instructions)

def get_user_id(source: discord.Interaction | discord.Message) -> str:
    if isinstance(source, discord.Interaction):
        return str(source.user.id)
    else:
        return str(source.author.id)

def convert_image_to_preview(google_drive_url):
    match = re.search(r"https://drive\.google\.com/file/d/([^/]+)/preview", google_drive_url)
    if match:
        file_id = match.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    else:
        return google_drive_url
