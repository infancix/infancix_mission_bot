import sys
import os
import requests
import aiohttp
import discord
import inspect
import traceback
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Any, Union

from bot.config import config
from bot.logger import setup_logger

class APIUtils:
    def __init__(self, api_host: str, api_port: str):
        """Initialize BotUtils with API configuration"""
        self.base_url = f"http://{api_host}:{api_port}/api/{{}}"
        self.logger = setup_logger('APIUtils')

    async def fetch_student_list(self):
        return await self._get_request('mission/greeting_student_list')

    async def fetch_baby_list(self):
        return await self._get_request('get_baby_list')

    async def get_mission_info(self, mission_id, endpoint='mission/mission_info'):
        return await self._get_request(f"{endpoint}?mission_id={mission_id}")

    async def get_student_is_in_mission(self, user_id):
        return await self._post_request('get_student_is_in_mission', {'discord_id': str(user_id)})

    async def get_mission_default_content_by_id(self, baby_id, mission_id, endpoint='photo_mission/default_mission_content'):
        return await self._get_request(f"{endpoint}?baby_id={baby_id}&mission_id={mission_id}")

    async def get_student_mission_status(self, user_id, mission_id):
        response = await self._get_request(f'get_student_mission_status?discord_id={user_id}&mission_id={mission_id}')
        if bool(response) == False:
            return None

        response['user_id'] = str(user_id)
        return response

    async def update_student_mission_status(self, user_id, mission_id, total_steps=4, current_step=0, score=None, thread_id=None, is_paused=False, **kwargs):
        # thread_id is none only if the status is complete
        if current_step == 0 and not isinstance(thread_id, str):
            raise Exception('thread_id is required for status Start')
        data = {
            'discord_id': str(user_id),
            'mission_id': mission_id,
            'total_steps': total_steps,
            'current_step': current_step,
            'is_paused': is_paused,
        }
        if thread_id:
            data['thread_id'] = thread_id
        if score:
            data['score'] = score

        response = await self._post_request('update_student_mission_status', data)
        return bool(response)

    async def update_student_current_mission(self, user_id, mission_id):
        data = {
            'discord_id': str(user_id),
            'channel_id': '照護教室',
            'class_id': mission_id,
        }
        response = await self._post_request('update_student_current_class', data)
        return bool(response)

    async def upload_baby_image(self, user_id, mission_id, milestone, image_url):
        data = {
            'discord_id': str(user_id),
            'mission_id': mission_id,
            'milestone': milestone,
            'image_url': image_url,
            'image_date': str(datetime.now().date())
        }
        response = await self._post_request('upload_baby_image', data)
        return bool(response)

    async def update_mission_image_content(self, user_id, mission_id, image_url=None, aside_text=None, content=None, endpoint='photo_mission/update_mission_image_content'):
        payload = {
            'discord_id': str(user_id),
            'mission_id': int(mission_id)
        }
        if image_url:
            payload['image_url'] = image_url
        if aside_text:
            payload['aside_text'] = aside_text
        if content:
            payload['content'] = content

        return await self._post_request(endpoint, payload)

    async def get_all_students_mission_notifications(self):
        return await self._get_request('get_student_mission_notification_list')

    async def get_student_mission_notifications_by_id(self, user_id):
        response = await self._get_request(f'get_student_mission_notification_list?discord_id={user_id}')
        if bool(response) == False:
            return None
        return response[user_id]

    async def get_student_milestones(self, user_id):
        return await self._get_request(f'get_student_milestones?discord_id={user_id}')

    async def get_student_profile(self, user_id):
        response = await self._post_request('get_student_profile', {'discord_id': str(user_id)})
        if bool(response) == False:
            return None
        return response

    async def get_baby_profile(self, user_id):
        response = await self._post_request('get_baby_profile', {'discord_id': str(user_id)})
        if bool(response) == False:
            return None
        return response

    async def get_student_babies(self, user_id, endpoint='get_student_babies'):
        return await self._get_request(f"{endpoint}?discord_id={user_id}")

    async def get_baby_additional_info(self, user_id):
        additional_info = "另外以下為內部資料，僅僅只為了這次的主題給你參考，請不要覆述以下內容：\n"

        baby = await self.get_baby_profile(user_id)
        if not baby:
            additional_info += '寶寶未登記資料，需要提醒家長用“寶寶檔案室”登記寶寶資料！'
            return additional_info

        birth_date = datetime.strptime(baby['birthdate'], '%Y-%m-%d').date()
        day_age = (datetime.today().date() - birth_date).days
        baby_name = baby['baby_name']
        baby_gender = '男' if baby['gender'] == 'm' else '女'

        additional_info += f'今天日期: {datetime.today().date()}'
        additional_info += f'\n寶寶姓名: {baby_name}'
        additional_info += f'\n寶寶性別: {baby_gender}'
        additional_info += f'\n寶寶生日: {birth_date}'
        additional_info += f'\n寶寶日齡: {day_age}天'
        return additional_info

    async def get_baby_images(self, discord_id, mission_id, endpoint='photo_mission/canva_result'):
        return await self._get_request(f"{endpoint}?discord_id={discord_id}&mission_id={mission_id}")

    async def check_student_mission_eligible(self, user_id):
        student = await self.get_student_profile(user_id)
        baby = await self.get_baby_profile(user_id)
        if not student and not baby:
            return 'lack_baby_profile'
        elif not baby and student.get('due_date', None) is not None:
            if student.get('due_date') >= datetime.today().date():
                return 'lack_baby_profile'
            else:
                return 'pregnancy_stage'
        else:
            return 'mission_eligible'

    async def check_baby_records_in_two_weeks(self, user_id):
        response = await self._post_request('get_baby_records', {'discord_id': str(user_id)})
        if bool(response) == False:
            return None

        records = [
            record
            for record in response
            if (datetime.today() - datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M')).days <= 14
        ]

        if len(records) > 0:
            return True
        else:
            return False

    async def check_user_photo_mission_status(self, user_id, mission_id):
        response = await self._post_request('get_student_photo_mission_status', {'discord_id': str(user_id), 'mission_id': mission_id})
        if bool(response) == False:
            return None

        return response.get('mission_status', 'Incompleted') == 'Completed'

    async def store_message(self, user_id, role, message, message_id=None):
        data = {
            'discord_id': str(user_id),
            'channel_id': '任務佈告欄',
            'message_timestamp': datetime.now().isoformat(),
            'message_author': role,
            'message_content': message,
        }
        if message_id:
            data['message_id'] = str(message_id)
        response = await self._post_request('add_student_chat_data', data)
        return bool(response)

    async def store_comment(self, user_id, channel_id, page_id, content):
        data = {
            'discord_id': str(user_id),
            'action': 'like',
            'channel_id': channel_id,
            'page_id': page_id,
            'content': content
        }
        response = await self._post_request('update_community_record', data)
        return bool(response)

    async def store_reaction(self, user_id, emoji):
        data = {
            'discord_id': str(user_id),
            'action': 'like',
            'channel_id': '任務佈告欄',
            'page_id': '1281123155489984529',
            'content': emoji
        }
        response = await self._post_request('update_community_record', data)
        return bool(response)

    async def add_gold(self, user_id, gold, endpoint='update_user_stats'):
        payload = {
            'discord_id': str(user_id),
            'gold': gold
        }
        self.logger.info(f"User {user_id} call {endpoint} {payload}.")
        return await self._post_request(endpoint, payload)

    async def send_dm_message(self, user_id, message, endpoint='send_dm_message'):
        payload = {
            'discord_id': str(user_id),
            'message': message
        }
        return await self._post_request(endpoint, payload)

    ## ------------------ API for generate photo / album request ----------------
    async def submit_generate_album_request(self, user_id, book_id, endpoint='process_album_and_autofill'):
        payload = {
            'discord_id': str(user_id),
            'book_id': int(book_id),
        }
        return await self._post_request(endpoint, payload)

    async def submit_generate_photo_request(self, user_id, mission_id, endpoint='process_and_autofill'):
        payload = {
            'discord_id': str(user_id),
            'mission_id': int(mission_id),
        }
        return await self._post_request(endpoint, payload)

    ## ----------------- Helper functions ----------------
    async def _get_request(self, endpoint: str) -> Any:
        """Generic method to handle GET requests to the API"""
        url = self.base_url.format(endpoint)
        self.logger.debug(f"Calling {url}.")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        return response_data.get('data')
                    else:
                        self.logger.error(f"API request failed with status (/api/{endpoint}): {response.status}")
                        return None
        except Exception as e:
            self.logger.error(f"API request failed - /api/{endpoint}: {str(e)}")
            return None

    async def _post_request(self, endpoint: str, data: Dict) -> Any:
        """Generic method to handle POST requests to the API"""
        url = self.base_url.format(endpoint)
        self.logger.debug(f"Calling {url} with data: {data}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        if endpoint == 'user_login':
                            return response_data.get('url')
                        elif endpoint == 'update_community_record':
                            return response_data
                        elif endpoint.startswith('get_'):
                            return response_data.get('data') or response_data.get('records')
                        else:
                            return response_data
                    else:
                        self.logger.error(f"API request failed /api/{endpoint} with status {response.status}, {response.text}")
                        return None
        except Exception as e:
            error_traceback = traceback.format_exc()
            caller_info = inspect.stack()[1]
            caller_function = caller_info.function
            caller_line = caller_info.lineno
            self.logger.error(f"API request failed: {str(e)}")
            self.logger.error(f"Error Traceback: {error_traceback}")
            self.logger.error(f"Caller Function: {caller_function}, Line: {caller_line}")
            return None