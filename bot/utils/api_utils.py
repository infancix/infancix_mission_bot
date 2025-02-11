import sys
import os
import requests
import aiohttp
import discord
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
                        self.logger.error(f"API request failed with status {response.status}")
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
                            return response_data.get('message')
                    else:
                        self.logger.error(f"API request failed /api/{endpoint} with status {response.status}")
                        return None
        except Exception as e:
            self.logger.error(f"API request failed: {str(e)}")
            return None

    async def fetch_student_list(self):
        return await self._get_request('get_student_list')

    async def fetch_baby_list(self):
        return await self._get_request('get_baby_list')

    async def get_mission_info(self, mission_id):
        missions = await self._get_request('get_mission_list')
        return missions[int(mission_id)-1]

    async def optin_class(self, user_id, channel_id='照護教室'):
        data = {
            'discord_id': str(user_id),
            'channel_id': channel_id
        }
        response = await self._post_request('optin_class', data)
        return bool(response)

    async def update_mission_assistant(self, mission_id, assistant_id):
        data = {
            'mission_id': int(mission_id),
            'assistant_id': assistant_id
        }
        response = await self._post_request('update_mission_assistant', data)
        return bool(response)

    async def get_student_is_in_mission(self, user_id):
        return await self._post_request('get_student_is_in_mission', {'discord_id': str(user_id)})

    async def update_student_mission_status(self, user_id, mission_id, total_steps=6, current_step=0, thread_id=None, assistant_id=None):
        # thread_id is none only if the status is complete
        if current_step == 0 and not isinstance(thread_id, str) and not isinstance(assistant_id, str):
            raise Exception('thread_id is required for status Start')

        data = {
            'discord_id': str(user_id),
            'mission_id': mission_id,
            'total_steps': str(total_steps),
            'current_step': str(current_step)
        }
        if thread_id:
            data['thread_id'] = thread_id
        if assistant_id:
            data['assistant_id'] = assistant_id

        response = await self._post_request('update_student_mission_status', data)
        return bool(response)

    async def upload_baby_image(self, user_id, milestone, image_url):
        data = {
            'discord_id': str(user_id),
            'milestone': milestone,
            'image_url': image_url,
            'image_date': str(datetime.now().date())
        }
        response = await self._post_request('upload_baby_image', data)
        return bool(response)

    async def get_student_mission_notification_list(self):
        return await self._get_request('get_student_mission_notification_list')

    async def get_student_incompleted_mission_list(self, user_id):
        return await self._post_request('get_student_incompleted_mission_list', {'discord_id': str(user_id)})

    async def get_student_profile(self, discord_id):
        response = await self._post_request('get_student_profile', {'discord_id': str(discord_id)})
        if bool(response) == False:
            return None
        return response

    async def get_baby_profile(self, discord_id):
        response = await self._post_request('get_baby_profile', {'discord_id': str(discord_id)})
        if bool(response) == False:
            return None
        return response

    async def get_baby_additional_info(self, discord_id):
        baby = await self.get_baby_profile(discord_id)
        if not baby:
            return '寶寶未登記資料，需要提醒家長用“寶寶檔案室”登記寶寶資料！'

        birth_date = datetime.strptime(baby['birthdate'], '%Y.%m.%d').date()
        day_age = (datetime.today().date() - birth_date).days
        baby_name = baby['baby_name']
        baby_gender = '男' if baby['gender'] == 'm' else '女'

        record_str = f'今天日期: {datetime.today().date()}'
        record_str += f'\n寶寶姓名: {baby_name}'
        record_str += f'\n寶寶性別: {baby_gender}'
        record_str += f'\n寶寶生日: {birth_date}'
        record_str += f'\n寶寶日齡: {day_age}天'
        return record_str

    async def check_student_mission_eligible(self, discord_id):
        student = await self.get_student_profile(discord_id)
        baby = await self.get_baby_profile(discord_id)
        if not student and not baby:
            return -1
        elif not baby and student.get('due_date', None) is not None:
            return 'pregnancy_or_newborn_stage'
        else:
            birth_date = datetime.strptime(baby['birthdate'], '%Y.%m.%d').date()
            day_age = (datetime.today().date() - birth_date).days
            if day_age >= 31:
                return 'over_31_days'
            else:
                return 'pregnancy_or_newborn_stage'

    async def check_baby_records_in_two_weeks(self, discord_id):
        response = await self._post_request('get_baby_records', {'discord_id': discord_id})
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

    async def store_message(self, user_id, role, message):
        data = {
            'discord_id': str(user_id),
            'channel_id': '任務佈告欄',
            'message_timestamp': datetime.now().isoformat(),
            'message_author': role,
            'message_content': message,
        }
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

