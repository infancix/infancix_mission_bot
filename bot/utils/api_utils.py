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

    async def get_student_is_in_mission(self, user_id, endpoint='get_student_is_in_mission'):
        response = await self._post_request(endpoint, {'discord_id': str(user_id)})
        if bool(response) == False:
            return {}
        return response

    async def get_mission_default_content_by_id(self, user_id, mission_id, endpoint='photo_mission/default_mission_content'):
        return await self._get_request(f"{endpoint}?discord_id={user_id}&mission_id={mission_id}")

    async def get_student_album_purchase_status(self, user_id, book_id=None, endpoint='growth_album/get_browse_growth_albums'):
        response = await self._get_request(f'{endpoint}?discord_id={user_id}'+ (f'&book_id={book_id}' if book_id else ''))
        if bool(response) == False:
            return None
        return response

    async def get_student_mission_status(self, user_id, mission_id, endpoint='get_student_mission_status'):
        response = await self._get_request(f'{endpoint}?discord_id={user_id}&mission_id={mission_id}')
        if bool(response) == False:
            return None

        response['user_id'] = str(user_id)
        return response

    async def get_all_students_mission_notifications(self):
        return await self._get_request('get_student_mission_notification_list')

    async def get_student_mission_notifications_by_id(self, user_id, endpoint='get_student_mission_notification_list'):
        response = await self._get_request(f'{endpoint}?discord_id={user_id}')
        if bool(response) == False:
            return None
        return response[user_id]

    async def get_student_milestones(self, user_id):
        return await self._get_request(f'get_student_milestones?discord_id={user_id}')

    async def get_student_incomplete_photo_mission(self, user_id, book_id=None):
        response = await self._get_request(f'photo_mission/incompleted_mission_list?discord_id={user_id}' + (f'&book_id={book_id}' if book_id else ''))
        if bool(response) == False:
            return []
        return response

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

    async def get_baby_height_records(self, user_id):
        response = await self._post_request('get_baby_height', {'discord_id': str(user_id)})
        if bool(response) == False:
            return None

        return sorted(response, key=lambda x: x["day_id"])[0]

    async def get_baby_weight_records(self, user_id):
        response = await self._post_request('get_baby_weight', {'discord_id': str(user_id)})
        if bool(response) == False:
            return None

        return sorted(response, key=lambda x: x["day_id"])[0]

    async def get_baby_head_circumference_records(self, user_id):
        response = await self._post_request('get_baby_head_circumference', {'discord_id': str(user_id)})
        if bool(response) == False:
            return None

        return sorted(response, key=lambda x: x["day_id"])[0]

    async def get_student_babies(self, user_id, endpoint='get_student_babies'):
        return await self._get_request(f"{endpoint}?discord_id={user_id}")

    async def get_baby_additional_info(self, user_id):
        baby = await self.get_baby_profile(user_id)
        if not baby:
            return '寶寶資料未登記，需要和家長詢問寶寶的暱稱、性別、生日、出生時的身高、體重、頭圍等資料'

        height_records = await self.get_baby_height_records(user_id)
        weight_records = await self.get_baby_weight_records(user_id)
        head_circumference_records = await self.get_baby_head_circumference_records(user_id)

        birth_date = datetime.strptime(baby['birthdate'], '%Y-%m-%d').date()
        day_age = (datetime.today().date() - birth_date).days
        baby_name = baby['baby_name']
        baby_gender = '男' if baby['gender'] == 'm' else '女'

        additional_info = (
            f"以下資料提供給你參考:\n"
            f'寶寶暱稱: {baby_name}\n'
            f'寶寶出生日期: {birth_date}\n'
            f'寶寶性別: {baby_gender}\n'
            f'寶寶身高紀錄: {height_records}\n'
            f'寶寶體重紀錄: {weight_records}\n'
            f'寶寶頭圍紀錄: {head_circumference_records}\n'
        )
        return additional_info

    async def get_baby_images(self, discord_id, mission_id, endpoint='photo_mission/canva_result'):
        return await self._get_request(f"{endpoint}?discord_id={discord_id}&mission_id={mission_id}")

    async def update_student_mission_status(self, user_id, mission_id, total_steps=4, current_step=0, score=None, thread_id=None, is_paused=False, **kwargs):
        # thread_id is none only if the status is complete
        if current_step == 0 and not isinstance(thread_id, str):
            raise Exception('thread_id is required for status Start')
        data = {
            'discord_id': str(user_id),
            'mission_id': int(mission_id),
            'total_steps': total_steps,
            'current_step': current_step,
            'is_paused': is_paused,
        }
        if thread_id:
            data['thread_id'] = thread_id
        if score:
            data['score'] = float(score)

        print(data)
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

    async def update_mission_image_content(self, user_id, mission_id, discord_attachments=None, aside_text=None, content=None, endpoint='photo_mission/update_mission_image_content'):
        payload = {
            'discord_id': str(user_id),
            'mission_id': int(mission_id)
        }
        if discord_attachments:
            payload['attachments'] = []
            for attachment in discord_attachments:
                payload['attachments'].append({
                    'id': attachment['id'],
                    'url': attachment['url'],
                    'filename': attachment['filename']
                })
        if aside_text:
            payload['aside_text'] = aside_text
        if content:
            payload['content'] = content

        self.logger.info(f"User {user_id} call {endpoint} with payload: {payload}.")
        return await self._post_request(endpoint, payload)

    async def update_student_profile(self, user_id, student_name, pregnancy_status, due_date=None, endpoint='student_optin'):
        payload = {
            'discord_id': str(user_id),
            'student_name': student_name,
            'pregnancy_status': pregnancy_status,
        }
        if due_date:
            payload['due_date'] = due_date

        self.logger.info(f"User {user_id} call {endpoint} {payload}.")
        return await self._post_request(endpoint, payload)

    async def update_student_registration_done(self, user_id, endpoint='update_student_data'):
        payload = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M'),
            "discord_id": str(user_id),
            "action": {
                "type": "profile_update_status",
                "status": '已完成'
            }
        }
        return await self._post_request(endpoint, payload)

    async def update_student_baby_profile(self, user_id, baby_name, baby_name_en, gender, birthday, height, weight, head_circumference, endpoint='baby_optin'):
        if gender and gender in ['男孩', '女孩']:
            gender = 'f' if gender == '女孩' else 'm'
        else:
            gender = None

        payload = {
            'discord_id': str(user_id),
            'baby_name': baby_name if baby_name else None,
            'baby_name_en': baby_name_en if baby_name_en else None,
            'gender': gender if gender else None,
            'birthdate': birthday if birthday else None,
            'height': str(float(height)) if height else None,
            'weight': str(round(float(weight)/1000, 4)) if weight else None, # convert to kg
            'head_circumference': str(float(head_circumference)) if head_circumference else None,
        }

        self.logger.info(f"User {user_id} call {endpoint} {payload}.")
        return await self._post_request(endpoint, payload)

    async def update_student_baby_name(self, user_id, baby_name, endpoint='baby_optin'):
        payload = {
            'discord_id': str(user_id),
            'baby_name': baby_name
        }
        self.logger.info(f"User {user_id} call {endpoint} {payload}.")
        return await self._post_request(endpoint, payload)

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
            'channel_id': '繪本工坊',
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
                        if endpoint == "baby_optin":
                            return response_data
                        elif endpoint.startswith('get_'):
                            return response_data.get('data') or response_data.get('records')
                        elif endpoint == "update_mission_image_content":
                            if response_data.get('status') == 'success':
                                return True
                            else:
                                return False
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

