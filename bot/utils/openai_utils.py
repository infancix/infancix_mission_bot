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

        self.logger.info(f"Final reuslts: {parsed}")
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
                    "role": "system",
                    "content": [{"type": "input_text", "text": prompt}]
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
                        "content": [{"type": "input_text", "text": str(msg)}]
                    })
                elif role == "assistant":
                    messages.append({
                        "role": role,
                        "content": [{"type": "output_text", "text": str(msg)}]
                    })

            # current input
            messages.append({
                "role": "user",
                "content": [{"type": "input_text", "text": str(user_input)}]
            })

            response = self.client.responses.create(
                model="gpt-4o-mini",
                input=messages
            )

            response_json = self.parsed_json(response.output_text)
            return response_json
        except json.JSONDecodeError as e:
            self.logger.error(f"Error parsing response JSON: {e}")
            return {"message": response.output_text}
        except Exception as e:
            self.logger.error(f"Error processing user message: {e}")
            return {"error": str(e)}

    def process_photo_info(self, prompt_path, image_url) -> dict:
        try:
            prompt = self.load_prompt(prompt_path)
            response = self.client.responses.create(
                model="gpt-4.1",
                input=[
                    {
                        "role": "system",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt,
                            }
                        ]
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": image_url
                            }
                        ]
                    }
                ],
            )
            return self.parsed_json(response.output_text)

        except Exception as e:
            print(f"Error processing photo info: {e}")
            return {"error": str(e)}
