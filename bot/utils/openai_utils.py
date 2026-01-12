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

def normalize_aside_text(aside_text: str, cn_limit=15, en_limit=65) -> str:
    """
    Line breaks:
     - If the input already contains `\n`, keep the user's original line breaks (do not modify).
     - If the input contains no `\n`:
         * For Chinese text: insert a line break after ~15 Chinese characters (using visual unit count).
         * For English text: insert a line break at the nearest space before 60~65 characters.
    """
    def insert_break_chinese(s: str, n=15) -> str:
        result = ""
        count = 0.0
        for ch in s:
            char_units = unit_length(ch)
            if count + char_units > n and count > 0:
                result += "\n"
                count = 0.0
            result += ch
            count += char_units
        return result

    def insert_break_english(s: str, n=65) -> str:
        # split by words and rebuild with line limit
        words = s.split(" ")
        line = ""
        lines = []
        for word in words:
            if len(line) + len(word) + 1 > n:
                lines.append(line.strip())
                line = word
            else:
                line += " " + word if line else word
        if line:
            lines.append(line.strip())
        return "\n".join(lines)

    if aside_text is None:
        return None
    aside_text = aside_text.rstrip("\r")

    # Decide language type: if mostly ASCII → English; else → Chinese
    ascii_ratio = sum(ch.isascii() for ch in aside_text) / len(aside_text)
    processed = []
    for l in aside_text.split("\n"):
        if l.strip() == "":
            continue
        elif ascii_ratio > 0.7:
            processed.append(insert_break_english(l, n=en_limit))
        else:
            processed.append(insert_break_chinese(l, n=cn_limit))
    processed = "\n".join(processed)
    return processed

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

    def process_aside_text_validation(self, assistant_result: Dict[str, Any], skip_aside_text: bool = False) -> Dict[str, Any]:
        aside_text = assistant_result.get("aside_text")
        aside_text = aside_text if aside_text != "null" and aside_text != '' else None
        att = assistant_result.get("attachment") or {}
        is_ready = bool(att.get("url") and (aside_text is not None))

        processed = normalize_aside_text(aside_text) if aside_text is not None else None
        print(f"Processed aside text: {processed}, line count: {line_count(processed)}")
        # revise message
        msg = assistant_result.get("message")
        if is_ready:
            msg = "✅ 已收到！"
            if processed is not None and line_count(processed) > 2:
                msg = "⚠️ 文字超過 2 行，請縮短或調整至 30 字或 2 行以內。"
                is_ready = False
        elif not is_ready and skip_aside_text:
            is_ready = bool(att.get("url"))

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

    def process_content_validation(self, assistant_result: Dict[str, Any]) -> Dict[str, Any]:
        content = assistant_result.get("content")
        content = content if content != "null" and content != '' else None
        att = assistant_result.get("attachment", {})
        is_attachment_ready = bool(att.get("url"))
        is_ready = bool(is_attachment_ready and content is not None)

        # revise message
        msg = assistant_result.get("message")
        if is_ready:
            msg = "✅ 已收到！"
        elif is_attachment_ready and not content:
            msg = "⚠️ 還差最後一步，請補上文字內容！"
        else:
            msg = "請依指示上傳照片或是補上文字內容呦！"

        return {
            "message": msg,
            "content": content,
            "attachment": {
                "id": att.get("id", ""),
                "url": att.get("url", ""),
                "filename": att.get("filename", "")
            },
            "is_ready": is_ready
        }

    def process_baby_profile_validation(self, mission_id, assistant_result, skip_growth_info=False) -> Dict[str, Any]:
        att = assistant_result.get("attachment") or {}
        step_1, step_2, step_3 = False, False, False
        for field in ["baby_name", "baby_name_en", "birthday", "gender", "height", "weight", "head_circumference"]:
            if assistant_result.get(field) in ["", "null", 'Null', 'None', None]:
                assistant_result[field] = None

        if mission_id in config.baby_pre_registration_mission:
            is_ready = bool(assistant_result.get("baby_name"))
        elif mission_id in config.baby_name_en_registration_missions:
            is_ready = bool(assistant_result.get("baby_name_en") and assistant_result.get("gender"))
        else:
            step_1 = bool(assistant_result.get("baby_name") and \
                assistant_result.get("birthday") and \
                assistant_result.get("gender")
            )
            step_2 = skip_growth_info or \
                assistant_result.get("height") or \
                assistant_result.get("weight") or \
                assistant_result.get("head_circumference")
            step_3 = bool(att.get("url"))
            is_ready = step_1 and step_2 and step_3

        # revise message
        if is_ready:
            msg = "✅ 已登記！"
        elif (step_1 or step_2) and not step_3:
            msg = "⚠️ 還差最後一步，請上傳寶寶照片呦！"
        else:
            msg = assistant_result.get("message") or "請依指示補上寶寶資料呦！"

        return {
            "message": msg,
            "baby_name": assistant_result.get("baby_name", None),
            "baby_name_en": assistant_result.get("baby_name_en", None),
            "birthday": assistant_result.get("birthday", None),
            "gender": assistant_result.get("gender", None),
            "height": assistant_result.get("height", None), 
            "weight": assistant_result.get("weight", None),
            "head_circumference": assistant_result.get("head_circumference", None),
            "attachment": {
                "id": att.get("id", ""),
                "url": att.get("url", ""),
                "filename": att.get("filename", "")
            },
            "is_ready": is_ready,
            "step_1_completed": step_1,
            "step_2_completed": step_2,
            "step_3_completed": step_3,
        }

    def process_relationship_validation(self, assistant_result: Dict[str, Any]) -> Dict[str, Any]:
        att = assistant_result.get("attachment") or {}
        relation_or_identity = assistant_result.get("relation_or_identity", None)
        is_ready = bool(att.get("url") and (relation_or_identity is not None))

        # revise message
        if is_ready:
            msg = "✅ 已登記！"
        elif not relation_or_identity:
            msg = "⚠️ 還差最後一步，請補上與寶寶的關係或照片裡的人是誰呦！"
        else:
            msg = "請依指示上傳照片呦！"
        return {
            "message": msg,
            "relation_or_identity": relation_or_identity or None,
            "attachment": {
                "id": att.get("id", ""),
                "url": att.get("url", ""),
                "filename": att.get("filename", "")
            },
            "is_ready": is_ready
        }

    def process_theme_book_validation(self, book_id: int, assistant_result: Dict[str, Any], previous_result=None) -> Dict[str, Any]:
        # merge previous result
        if previous_result:
            for key in ["cover", "attachments"]:
                if not assistant_result.get(key) and previous_result.get(key):
                    assistant_result[key] = previous_result[key]

        # All of books need baby_name and cover and 6 attachments
        step_1, step_2, step_3, step_4, ask_for_relation_or_identity = False, False, False, False, False
        if assistant_result.get("baby_name"):
            step_1 = True

        if assistant_result.get("cover") and assistant_result["cover"].get("url"):
            step_2 = True
            if book_id == 16 and not assistant_result.get("relation_or_identity"):
                ask_for_relation_or_identity = True
                step_2 = False

        attachments = [att for att in assistant_result.get("attachments", []) if att.get("url")]
        if len(attachments) >= 6:
            step_3 = True        

        aside_texts = [att for att in assistant_result.get("aside_texts", []) if att.get("aside_text") and att.get("aside_text") not in ["", "null"]]
        if book_id in [13, 14, 15, 16]:
            step_4 = step_3 and len(aside_texts) >= 6
        else:
            step_4 = step_3

        is_ready = step_1 and step_2 and step_3 and step_4 and not ask_for_relation_or_identity
        return {
            "is_ready": is_ready,
            "message": assistant_result.get("message", "請依指示上傳照片或補上文字內容呦！"),
            "baby_name": assistant_result.get("baby_name", None),
            "relation_or_identity": assistant_result.get("relation_or_identity", None),
            "cover": assistant_result.get("cover", {}),
            "attachments": attachments or [],
            "aside_texts": aside_texts or [],
            "step_1_completed": step_1,
            "step_2_completed": step_2,
            "step_3_completed": step_3,
            "step_4_completed": step_4,
            "ask_for_relation_or_identity": ask_for_relation_or_identity
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

    def process_identity_or_relation_translation(self, identity_or_relation: str) -> dict:
        """
        Translate identity/relationship or object names into natural English following specific rules.

        Rules:
        1. Family titles → English (Mommy, Daddy, Grandpa, etc.)
        2. Names → Hanyu Pinyin (capitalized, no tones)
        3. Fictional names → Transliterate with "Little" prefix if natural
        4. Objects → Concise 2-3 word English noun phrase
        5. Already English → Keep unchanged

        Args:
            identity_or_relation: Chinese text to translate

        Returns:
            dict with 'input' and 'translation' keys
        """
        try:
            prompt = """
Translate short Chinese identity/relationship or object names into natural English.

Rules:
1. Family titles → English:
   媽媽→Mommy, 爸爸→Daddy, 阿公→Grandpa, 阿嬤→Grandma,
   哥哥→Big Brother, 弟弟→Little Brother, 姊姊→Big Sister, 妹妹→Little Sister.
   若出現「哥哥們」或包含「大哥、二哥、三哥」等多位哥哥 → "Brothers".
   若出現「姊姊們」或包含「大姊、二姊、三姊」等多位姊姊 → "Sisters".
   若輸入同時包含「哥哥」與「姊姊」 → "Brother and Sister"；
   若為複數（多位）→ "Brothers and Sisters".
   若超過三位家庭成員（例如 媽媽,爸爸,阿公,阿嬤）→ "Family".

2. Names or pet names → Convert to Hanyu Pinyin (capitalize each word, no tones).
   Example: 加加→Jia Jia, 李花花→Li Huahua.

3. Fictional doll or mascot names (e.g. 小噗嚨、小咕咕) → Transliterate to cute Hanyu Pinyin with "Little" prefix if natural.
   Example: 小噗嚨→Little Pulong.

4. Objects → Translate into a concise 2–3 word English noun phrase.
   Example: 熊熊枕→Bear Hug Pillow, 龍蝦奶嘴→Lobster Pacifier.

5. If the input is already English (A–Z letters only), keep it unchanged.

6. Always keep the final result within 2–3 English words total.

Output JSON format (no list, only final string):
{
 "input": "<original>",
 "translation": "<final concise English translation>"
}
"""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": prompt
                    },
                    {
                        "role": "user",
                        "content": identity_or_relation
                    }
                ],
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            self.logger.info(f"Translated identity/relation: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Error processing identity/relation translation: {e}")
            return {"input": identity_or_relation, "translation": identity_or_relation, "error": str(e)}

    def format_bilingual_sentence(self, prompt_template: str, chinese_answer: str, use_identity_translation: bool = True) -> str:
        """
        Format a bilingual sentence template by filling in the answer.
        Uses AI to automatically handle grammar (singular/plural, verb agreement, etc.)

        Args:
            prompt_template: Template with placeholders like:
                - Simple: "當{answer}，就會不開心的哭鬧。|Cries unhappily when {answer}."
                - Complex: "我最好的朋友是{little_friend}！|My best friend is {little_friend_en}!"
            chinese_answer: User's answer in Chinese
            use_identity_translation: If True, use identity/relation translation rules

        Returns:
            Formatted bilingual sentence with Chinese and English separated by |

        Examples:
            Input: "當{answer}，就會不開心的哭鬧。|Cries unhappily when {answer}.", "肚子餓"
            Output: "當肚子餓，就會不開心的哭鬧。|Cries unhappily when hungry."

            Input: "我最好的朋友是{little_friend}！|My best friend is {little_friend_en}!", "媽媽,爸爸"
            Output: "我最好的朋友是媽媽,爸爸！|My best friends are Mommy and Daddy!"
        """
        try:
            # Split template into Chinese and English parts
            if '|' not in prompt_template:
                # No English part, just replace Chinese
                return prompt_template.replace('{answer}', chinese_answer)

            parts = prompt_template.split('|', 1)
            chinese_template = parts[0]
            english_template = parts[1]

            # Replace Chinese part with original answer
            chinese_sentence = chinese_template.replace('{answer}', chinese_answer).replace('{little_friend}', chinese_answer).replace('{yummy_food}', chinese_answer)

            # Use AI to translate and format the English sentence with proper grammar
            translation_instruction = """
You are a translator. Given a Chinese answer and an English sentence template with placeholders, complete the task:

1. Translate the Chinese answer to English following these rules:
   - For simple phrases (肚子餓, 看到爸爸): translate naturally and concisely
   - For identity/relations with special rules: follow family title translations (媽媽→Mommy, 爸爸→Daddy, etc.)

2. Fill the translated answer into the English template's placeholders.

3. IMPORTANT: Automatically adjust grammar for singular/plural agreement:
   - If the translated answer contains multiple items (e.g., "Mommy and Daddy"), adjust the sentence:
     * "friend" → "friends"
     * "is" → "are"
     * Any other necessary grammar changes
   - If the answer is singular, keep the template as-is

4. Return ONLY the completed English sentence, nothing else.
""" if use_identity_translation else """
You are a translator. Given a Chinese answer and an English sentence template with a {answer} placeholder:

1. Translate the Chinese answer to natural, concise English
2. Replace {answer} in the template with the translation
3. Return ONLY the completed English sentence, nothing else.
"""

            user_message = f"Chinese answer: {chinese_answer}\nEnglish template: {english_template}"

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": translation_instruction
                    },
                    {
                        "role": "user",
                        "content": user_message
                    }
                ]
            )

            english_sentence = response.choices[0].message.content.strip()
            result = f"{chinese_sentence}|{english_sentence}"
            self.logger.debug(f"Formatted bilingual sentence: {result}")
            return result

        except Exception as e:
            self.logger.error(f"Error formatting bilingual sentence: {e}")
            # Fallback: simple replacement
            fallback = prompt_template.replace('{answer}', chinese_answer)
            fallback = fallback.replace('{little_friend}', chinese_answer).replace('{little_friend_en}', chinese_answer)
            fallback = fallback.replace('{yummy_food}', chinese_answer)
            return fallback

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
