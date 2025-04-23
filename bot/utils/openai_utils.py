import time
import re
import json
import os
from openai import OpenAI
from pathlib import Path
from pydub import AudioSegment
from bot.logger import setup_logger
from bot.config import config

class OpenAIUtils:
    def __init__(self, api_key: str):
        self.client = OpenAI(api_key=api_key)
        self.logger = setup_logger('OpenAIUtils')

        # check if audio folder exists
        if not os.path.exists('audio'):
            os.makedirs('audio')

    async def convert_audio_to_message(self, message):
        file_path = os.path.join('audio', f'{message.author.id}.ogg')
        await message.attachments[0].save(file_path)
        audio = AudioSegment.from_file(file_path)
        file_path = file_path.rsplit('.', 1)[0] + '.mp3'
        audio.export(file_path, format='mp3')

        transcription = self.client.audio.transcriptions.create(
            model="whisper-1",
            file=Path(file_path),
            prompt='請以台灣繁體中文',
            language='zh',
        )
        if transcription.text:
            return {"result": transcription.text}
        else:
            self.logger.error(f"Failed to parse audo message from {message.author.id}")
            return None

    def load_thread(self):
        return self.client.beta.threads.create().id

    def add_task_instruction(self, thread_id, instructions):
        _ = self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="assistant",
            content=instructions,
        )

    async def get_reply_message(self, assistant_id, thread_id, user_message):
        return await self.run(user_message, assistant_id, thread_id)

    async def run(self, message_content, assistant_id, thread_id, retry_count=2):
        if retry_count <= 0:
            return {
                'message': "抱歉，加一不太懂你的意思，請聯絡管理員協助喔。",
            }

        _ = self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message_content,
        )

        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id
        )

        messages = self.client.beta.threads.messages.list(thread_id=thread_id, order="desc")
        if not messages.data:
            self.logger.error("Message list is empty.")
            return {
                'message': (
                    "嗚嗚～加一跟你說，第三方AI系統…嗯，壞掉惹！😭\n"
                    "現在紀錄功能暫時不能用啦～拜託你稍微等一下下～真的抱歉捏！🐾🥹\n"
                    "請聯絡管理員協助喔。"
                ),
            }

        process_result = self.post_process(messages.data[0].content[0].text.value)
        if 'error' in process_result:
            self.logger.error(f"Error Type: {process_result['error']}, Raw Response: {process_result['raw_response']}")
            message_content += f"\n\n注意：{process_result['message']}，請根據提示重新調整。"
            return await self.run(message_content, assistant_id, thread_id, retry_count - 1)
        else:
            return process_result['result']

    def post_process(self, response):
        """Process GPT response to parse JSON and clean the message."""
        response = self.clean_message(response)
        start_index = response.find('{')
        end_index = response.rfind('}')
        if start_index == -1 or end_index == -1:
            self.logger.error(f"Wrong format in response: {response}")
            return {
                'error': 'format_error',
                'message': 'Response does not contain valid JSON format.',
                'raw_response': response
            }

        # clean message
        response = response[start_index:end_index + 1]

        # Attempt to parse JSON
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            return {
                'error': 'json_decode_error',
                'message': str(e),
                'raw_response': response
            }
        except Exception as e:
            self.logger.error(f"Receive unknown error: {e}")
            return {
                'error': 'unknown_error',
                'message': str(e),
                'raw_response': response
            }

        self.logger.debug(f"Final reuslts: {parsed}")
        return {
            'result': parsed
        }

    def clean_message(self, message):
        """
        清理訊息，移除中括號內容及 HTML 標籤，並修剪空白。
        """
        return re.sub(r'\【.*?\】', '', message).strip().replace('<br>', '\n')

    async def generate_quiz(self, mission, retry_count=1):
        if retry_count <= 0:
            return []

        quiz_prompt = self.generate_quiz_prompt(mission)
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": quiz_prompt}],
            temperature=0.7
        )
        response = response.choices[0].message.content.strip()
        process_result = self.post_process(response)
        if 'error' in process_result:
            self.logger.error(f"Error generating quiz: {process_result['message']} (Retry: {retry_count})")
            await self.generate_quiz(mission, retry_count-1)
        else:
            quiz = process_result['result'].get('quiz', [])
            return quiz

    def generate_quiz_prompt(self, mission):
        with open("bot/resource/quiz_prompt.txt", "r") as file:
            quiz_prompt = file.read()
            quiz_prompt = quiz_prompt.replace("{mission_title}", mission['mission_title'])
            quiz_prompt = quiz_prompt.replace("{transcription}", mission['transcription'])
            self.logger.info(f"Quiz prompt loaded: {quiz_prompt}")
        return quiz_prompt

    def generate_assistant_prompt(self):
        with open("bot/resource/assistent_prompt.txt", "r") as file:
            self.assistant_prompt = file.read()
            self.logger.info(f"Assistant prompt loaded: {self.assistant_prompt}")

        return self.assistant_prompt
