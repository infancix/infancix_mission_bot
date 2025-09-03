import time
import re
import json
import os
from openai import OpenAI
from pathlib import Path
from pydub import AudioSegment
from typing import Dict, Any
from bot.logger import setup_logger
from bot.config import config

_CH = re.compile(r'[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]')

def count_chinese(s: str) -> int:
    return len(_CH.findall(s or ""))

def unit_length(ch: str) -> float:
    """中文字算 1，英文/數字/空格/符號算 0.5"""
    if _CH.match(ch):
        return 1.0
    return 0.5

def line_count(s: str) -> int:
    return 1 if not s else s.count("\n") + 1

def normalize_aside_text(aside_text: str) -> str:
    """
    Line breaks:  
     - If the input already contains `\n`, keep the user’s original line breaks (do not modify).  
     - If the input contains no `\n`, and the text length exceeds **15 Chinese characters**, automatically insert a line break after the 15th character.  
     - The text must not exceed **2 lines**.
     """
    def _insert_break(s: str, n = 15) -> str:
        result = ""
        line_unit_count = 0.0
        for ch in s:
            char_units = unit_length(ch)
            if line_unit_count + char_units > n and line_unit_count > 0:
                result += "\n"
                line_unit_count = 0.0
            result += ch
            line_unit_count += char_units
        return result

    if aside_text is None:
        return None
    aside_text = aside_text.rstrip("\r")
    if "\n" in aside_text:
        return aside_text
    return _insert_break(aside_text)

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

    def get_reply_message(self, assistant_id, thread_id, user_message):
        _ = self.client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message,
        )

        run = self.client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id
        )

        messages = self.client.beta.threads.messages.list(thread_id=thread_id)
        process_result = self.post_process(messages.data[0].content[0].text.value)
        return process_result

    def post_process(self, response):
        response = self.clean_message(response)
        if '{' in response and '}' in response:
            return self.parsed_json(response)
        else:
            return {
                'is_ready': False,
                'message': response
            }

    def process_aside_text_validation(self, assistant_result: Dict[str, Any]) -> Dict[str, Any]:
        aside_text = assistant_result.get("aside_text")
        att = assistant_result.get("attachment") or {}
        is_ready = bool(att.get("id") and att.get("url") and att.get("filename") and (aside_text is not None))

        processed = normalize_aside_text(aside_text) if aside_text is not None else None

        # revise message
        msg = "✅ 已收到！"
        if processed is not None and line_count(processed) > 2:
            msg = "⚠️ 文字超過 2 行，請縮短或調整至 30 字或 2 行以內。"
            is_ready = False

        return {
            "message": msg,
            "aside_text": processed,
            "attachment": {
                "id": att.get("id", ""),
                "url": att.get("url", ""),
                "filename": att.get("filename", "")
            },
            "is_ready": is_ready
        }

    def parsed_json(self, response):
        start_index = response.find('{')
        end_index = response.rfind('}')
        if start_index == -1 or end_index == -1:
            self.logger.error(f"Wrong format in response: {response}")
            return {
                'error': 'format_error',
                'message': f'Response does not contain valid JSON format. {response}'
            }

        response = response[start_index:end_index + 1]
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}")
            return {
                'error': 'json_decode_error',
                'message': f"{str(e)}\n{response}"
            }
        except Exception as e:
            self.logger.error(f"Receive unknown error: {e}")
            return {
                'error': 'unknown_error',
                'message': f"{str(e)}\n{response}"
            }

        self.logger.debug(f"Final reuslts: {parsed}")
        return parsed

    def clean_message(self, message):
        message = re.sub(r'\【.*?\】', '', message).strip().replace('<br>', '\n')
        if '{{' in message and '}}' in message:
            message = message.replace('{{', '{')
            message = message.replace('}}', '}')
        return message

    def load_prompt(self, file_path):
        with open(file_path, "r") as file:
            return file.read()

    def process_user_message(self, prompt_path, user_input, conversations=None, additional_context=None) -> dict:
        try:
            prompt = self.load_prompt(prompt_path)
            if additional_context:
                prompt = f"{additional_context}\n\n{prompt}"

            # system prompt
            messages = [
                {
                    "role": "developer",
                    "content": prompt
                }
            ]

            # history conversation
            for turn in conversations or []:
                role = turn.get("role")
                msg = turn.get("message")
                if not role or msg is None:
                    continue
                if role == "user":
                    messages.append({
                        "role": role,
                        "content": str(msg)
                    })
                elif role == "assistant":
                    messages.append({
                        "role": role,
                        "content": str(msg)
                    })

            # current input
            messages.append({
                "role": "user",
                "content": str(user_input)
            })

            response = self.client.responses.create(
                model="gpt-4o-mini",
                input=messages,
                text={
                    "format": {
                        "type": "json_object",
                    }
                }
            )
            response_json = self.parsed_json(response.output_text)
            return response_json
        except Exception as e:
            self.logger.error(f"Error processing user message: {e}")
            return {"error": str(e)}
