from datetime import datetime

from loguru import logger
import requests
import aiohttp
import discord

from bot.constants import TASK_MEDAL
from bot.config import config


async def fetch_baby_list():
    api_url = f'http://{config.BABY_API_HOST}:{config.BABY_API_PORT}/api/get_baby_list'
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            return await response.json()


async def send_task_unfinished_notification(client, discord_id, last_task_title):
    user = await client.fetch_user(discord_id)

    await user.send(
        f'嗨，您好嗎？我知道您忙著照顧寶寶，"{last_task_title}"的諮詢還未結束，若您有空時請隨意回覆，我會隨時在這裡為您服務。'
    )


async def update_student_mission_status(user_id, mission_id, total_steps=0, current_step=0, thread_id=None, assistant_id=None):
    # thread_id is none only if the status is complete
    if current_step == 0 and not isinstance(thread_id, str) and not isinstance(assistant_id, str):
        raise Exception('thread_id is required for status Start')

    user_id = str(user_id)
    api_url = f'http://{config.BABY_API_HOST}:{config.BABY_API_PORT}/api/update_student_mission_status'
    data = {
        'discord_id': user_id,
        'mission_id': mission_id,
        'total_steps': str(total_steps),
        'current_step': str(current_step)
    }

    if current_step == 0:
        data['thread_id'] = thread_id
        data['assistant_id'] = assistant_id

    try:
        response = requests.post(
            api_url,
            json=data,
        )
        data = response.json()
        logger.debug(f'Update mission_status API response: {data}')
    except Exception as e:
        logger.error(f'Update mission_status API Error: {e}')

async def upload_baby_image(user_id, milestone, image_url, image_date):
    user_id = str(user_id)
    api_url = f'http://{config.BABY_API_HOST}:{config.BABY_API_PORT}/api/upload_baby_image'
    data = {
        'discord_id': user_id,
        'milestone': milestone,
        'image_url': image_url,
        'image_date': str(image_date)
    }

    try:
        response = requests.post(
            api_url,
            json=data,
        )
        data = response.json()
        logger.debug(f'Upload baby_image API response: {data}')
    except Exception as e:
        logger.error(f'Upload baby_image API Error: {e}')


async def job(client):
    logger.debug('Running job now...')

    channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise Exception('Invalid channel')

    data = await get_student_class_notification()

    tasks_to_be_pushed = data.get('notification_list', [])
    tasks_to_be_notified = data.get('incomplete_class_reminder_list', [])

    # Push tasks to students
    for task in tasks_to_be_pushed:
        discord_id = task['discord_id']
        task_id = task['registered_class_id']

        # Start task
        await channel.send(f'START_TASK_{task_id} <@{discord_id}>')

    # Notify the user if they haven't completed the previous task
    for task in tasks_to_be_notified:
        discord_id = task['discord_id']
        last_task_title = task['class_title']
        await send_task_unfinished_notification(client, discord_id, last_task_title)


async def get_student_class_notification():
    api_url = f'http://{config.BABY_API_HOST}:{config.BABY_API_PORT}/api/get_student_class_notification_list'
    try:
        response = requests.get(api_url)
        data = response.json()
    except Exception as e:
        logger.error(f'get_student_class_notification Error: {e}')
        data = {}

    return data


async def get_baby_record(discord_id):
    try:
        baby_list = (await fetch_baby_list())['data']
    except Exception as e:
        logger.error(f'Error: {e}')
        baby_list = []

    baby = next(
        (baby for baby in baby_list if baby['discord_id'] == str(discord_id)), None
    )

    if baby is None:
        return '寶寶未登記資料，需要提醒家長用“寶寶檔案室”登記寶寶資料！'

    birth_date = datetime.strptime(baby['birth_date'], '%Y.%m.%d').date()
    day_age = (datetime.today().date() - birth_date).days
    baby_name = baby['baby_name']
    baby_gender = '男' if baby['gender'] == 'm' else '女'

    api_url = (
        f'http://{config.BABY_API_HOST}:{config.BABY_API_PORT}/api/get_baby_records'
    )
    try:
        response = requests.post(api_url, json={'discord_id': str(discord_id)})
        data = response.json()
    except Exception as e:
        logger.error(f'Error: {e}')
        data = {'records': []}

    record_str = f'今天日期: {datetime.today().date()}'
    record_str += f'\n寶寶姓名: {baby_name}'
    record_str += f'\n寶寶性別: {baby_gender}'
    record_str += f'\n寶寶生日: {birth_date}'
    record_str += f'\n寶寶日齡: {day_age}天'

    #record_str += f'\n寶寶三天內歷史生理紀錄(分鐘):\n'

    #records = data.get('records', [])

    # take only records in the last 3 days
    #records = [
    #    record
    #    for record in records
    #    if (
    #        datetime.today() - datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M')
    #    ).days
    #    <= 4
    #]

    # remove current day record
    #records = [record for record in records if record['timestamp'] != datetime.today().date()]

    #for record in records:
    #    record_str += f'\n{record}'

    # if no records at all
    #if len(data.get('records', [])) == 0:
    #    record_str += 'NOTE: 沒有任何生理紀錄，需要提醒家長用“寶寶檔案室”AI語音紀錄功能記錄寶寶睡眠餵奶狀況！'

    # if no records in the last 3 days
    #if len(records) == 0:
    #    record_str += 'NOTE: 近三天沒有寶寶生理紀錄，需要提醒家長用“寶寶檔案室”AI語音紀錄功能記錄寶寶睡眠餵奶狀況！'

    return record_str


async def store_message(user_id, role, timestamp, message):
    api_url = f'http://{config.BABY_API_HOST}:{config.BABY_API_PORT}/api/add_student_chat_data'
    try:
        response = requests.post(
            api_url,
            json={
                'discord_id': user_id,
                'channel_id': '任務佈告欄',
                'message_timestamp': timestamp,
                'message_author': role,
                'message_content': message,
            },
        )
        data = response.json()
        logger.debug(f'Store message API response: {data}')
    except Exception as e:
        logger.error(f'Store message API Error: {e}')


async def get_student_is_in_mission(user_id):
    api_url = f'http://{config.BABY_API_HOST}:{config.BABY_API_PORT}/api/get_student_is_in_mission'
    try:
        response = requests.post(api_url, json={'discord_id': user_id})
        data = response.json()
        logger.debug(f'get_student_is_in_mission API response: {data}')
    except Exception as e:
        logger.error(f'get_student_is_in_mission Error: {e}')
        data = {}

    return data
