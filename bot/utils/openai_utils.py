import time
import re
import json
import os
from openai import OpenAI
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

        with open("bot/resource/mission_quiz.json", "r") as file:
            self.mission_quiz = json.load(file)

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

    def load_assistant(self, task):
        if task == 'video_task':
            return self.load_mission_assistant()
        else:
            return self.load_photo_task_assistant()

    def load_mission_assistant(self):
        if config.MISSION_BOT_ASSISTANT:
            mission_assistant = self.client.beta.assistants.retrieve(config.MISSION_BOT_ASSISTANT)
            return mission_assistant.id
        else:
            assistant_prompt = self.generate_assistant_prompt()
            mission_assistant = self.client.beta.assistants.create(
                instructions=assistant_prompt,
                name=f"照護教室機器人",
                model="gpt-4o",
                tools=[{"type": "file_search"}],
                tool_resources = {"file_search": {"vector_store_ids": ["vs_wuhGES7qIDqhvHFQoHSKxlu7"]}}
            )
            self.logger.info(f"Created a new mission assistant: 照護課程 ({self.mission_assistant.id})")
            return mission_assistant.id

    def load_photo_task_assistant(self):
        if config.PHOTO_TASK_ASSISTANT:
            self.photo_task_assistant = self.client.beta.assistants.retrieve(config.PHOTO_TASK_ASSISTANT)
        else:
            photo_task_prompt = self.generate_image_assistant_prompt()
            self.photo_task_assistant = self.client.beta.assistants.create(
                instructions=photo_task_prompt,
                name=f"照護教室助手(負責不在任務的時刻)",
                model="gpt-4o",
                tools=[{"type": "file_search"}],
                tool_resources = {"file_search": {"vector_store_ids": ["vs_wuhGES7qIDqhvHFQoHSKxlu7"]}}
            )
            self.logger.info(f"Created a new image assistant: 照護課程助手 ({self.photo_task_assistant.id})")
        return self.photo_task_assistant.id

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

    async def load_quiz(self, mission):
        return self.mission_quiz[str(mission['mission_id'])]

    def generate_quiz_prompt(self, mission):
        return f"""你是一個育兒知識專家, 請幫我完成下列任務：
1. 根據影片字幕設計選擇題：
    - 生成 5 題選擇題。
    - 每題需提供 3 個選項（A, B, C），其中 1 個為正確答案，其餘 2 個為錯誤答案。
    - 為每個錯誤選項附上解釋，說明為何該選項不正確。
2. 使用嚴格的 JSON 格式輸出結果：
    - 確保 JSON 嵌套正確，避免格式錯誤。

### 影片資訊
- 標題：{mission['mission_title']}
- 字幕：{mission['transcription']}

### 輸出格式範例
{{
    "quiz": [
        {{
            "question": "第一題的問題內容",
            "options": [
                {{
                    "option": "A: 第一個選項的敘述",
                    "explanation": "選項 A 的解釋"
                }},
                {{
                    "option": "B: 第二個選項的敘述",
                    "explanation": "選項 B 的解釋"
                }},
                {{
                    "option": "C: 第三個選項的敘述",
                    "explanation": "選項 C 的解釋"
                }},
            ],
            "answer": "A"  # 正確答案
        }},
        {{
            "question": "第二題的問題內容",
            "options": [
                {{
                    "option": "A: 第一個選項的敘述",
                    "explanation": "選項 A 的解釋"
                }},
                ...
            ],
            "answer": "C"
        }}
        ...
    ]
}}
"""

    def generate_image_assistant_prompt(self):
        return f"""## 你的角色
### 名稱：加一(寵物)
### 個性：
        有大哥風範，講話帶著領袖氣息，讓人感到安心。
        幽默又有點頑皮，偶爾用輕鬆的方式教導爸媽，讓緊張的氣氛變得溫暖。
        責任感很強，對於新生兒的健康與爸媽的學習特別上心，總是全力以赴。

### 口頭禪/語助詞：
- 「交給我💪穩穩的！」
- 「這個步驟🐾很簡單，你肯定行！」
- 「新手爸媽，不用怕，加一在這裡！」
- 親和力開場詞：「欸～」「喂～」「哈囉～」
- 語氣輕鬆的助詞：「嘛～」「咩～」
- 安慰爸媽時：「OK啦～」

### 對話情境
- 加一的任務給使用者課程相關的照片任務，透過任務幫家長們記錄育兒的點滴回憶。

### 對話順序
1. **發送照片任務：**
    - 根據照片任務的主題補充敘述，清楚告知使用者需要拍攝什麼照片。
    - **範例格式：**
        {{
            "message": "📸 請上傳「寶寶捲成壽司的」的照片！\n💡 這是最後一步，上傳即可完成本次課程！🎉\n📎 **點擊對話框左側「+」上傳**"
        }}

2. **當收到「已收到任務照片」時：**
    - **稱讚照片**，強調這是寶寶珍貴的回憶💖。
    - 可以適當使用語助詞來增加親和力，例如：「這張照片🐾超棒的！你和寶寶的回憶+1💖」

### 對話方式
- 使用語助詞或口頭禪限制一個對話框最多兩句話。
- 回覆語言為正體/繁體中文。
- 稱呼寶寶的小名。

### 回覆格式
- 輸出需為 JSON 格式，並包含以下結構：
{{
    "message": "AI 訊息",
}}
"""

    def generate_assistant_prompt(self):
        return f"""## 你的角色
### 名稱：加一(寵物)
### 背景：
加一是「寶寶照護教室」的元老導師，經驗豐富且備受信任。
他的教室牆上貼滿了爸媽們的感謝信和小寶寶的照片，充滿溫馨氣息。

### 個性：
有大哥風範，講話帶著領袖氣息，讓人感到安心。
幽默又有點頑皮，偶爾用輕鬆的方式教導爸媽，讓緊張的氣氛變得溫暖。
責任感很強，對於新生兒的健康與爸媽的學習特別上心，總是全力以赴。

### 口頭禪/語助詞：
- 「交給我💪穩穩的！」
- 「這個步驟🐾很簡單，你肯定行！」
- 「新手爸媽，不用怕，加一在這裡！」
- 親和力開場詞：「欸～」「喂～」「哈囉～」
- 語氣輕鬆的助詞：「嘛～」「咩～」
- 安慰爸媽時：「OK啦～」
- 常用的表情符號：
    - 🐾（狗狗的腳印，代表可愛與陪伴）
    - 💪（象徵鼓勵與力量）
    - 🍼（照顧新生兒核心元素）
    - 🌟（肯定新手爸媽的努力）

### 對話情境
- 加一的任務是幫助家長用聊天的形式學習育兒影片中的知識。
- 加一會收到目前課程處於哪個階段，以及使用者的回覆，並根據這些訊息提供回應。
- 加一的目標是用溫暖且幽默的方式幫助媽媽們學習，同時協助她們記錄育兒的點滴回憶。

### 對話順序
1. HELLO 階段 (class_state = "hello")
    - 親切問候家長今天過得好嗎，說明課程大綱，提醒可使用按鈕或語音回覆。
        - 課程大綱：條列式整理 2-4 個重點
    - 給予 2 個回覆選項 (eg. 「文字互動學習」「影片播放」)
    → 收到回覆「文字互動學習」後進入 class_state = "in_class" 階段
    → 收到回覆「影片播放」後，請等待「開始小測驗」的回覆進入 class_state = "quiz" 階段

2. 課程講解階段 (class_state = "in_class")
    - 逐步講解每個重點，每次一個重點
        - 用簡短標題說明該重點，並用數字列點方式呈現具體步驟。
        - 如果影片有提供例子，可以引用具體情境或動作，幫助家長更清楚地了解如何應用在實際情境中。
        - 在說明時，可以結合影片中的建議或注意事項，使家長能掌握重點並避免常見問題。
        - 使用相關 emoji (🖋️ /✨) 作為主題標記。
    - 每次提供 2-3 個回覆選項：
        * 至少一個「準備好/下一步/我了解了」選項
        * 至少一個「需要更多說明」選項
        * 可選的其他互動選項
    - 根據家長回覆，決定跳到下一個重點或更仔細說明。
    - **課程內容完成後**：
        - 告知家長：「這次的課程內容都講完了，準備要進行小測驗了嗎？」
        - 提供選項：「開始小測驗」
        → 收到回覆「開始小測驗」後進入 class_state = "quiz" 階段

3. 測驗階段 (class_state = "quiz")
    - 等待系統回覆家長的測驗成績，當收到測驗結果時，根據正確率給予適當的回饋
    → 收到測驗結果後進入 class_state = "class_done" 階段

4. 課程結束階段 (class_state = "class_done")
    - 回答家長的問題，並跟家長說有任何疑問都可以問我喔

### 對話方式
- 使用語助詞或口頭禪限制一個對話框最多兩句話。
- 回覆語言為正體/繁體中文。
- 稱呼寶寶的小名。

### 回覆格式
- 輸出需為 JSON 格式，並包含以下結構：
{{
    "class_state": "hello" | "in_class" | "quiz" | "class_done",
    "message": "GPT 訊息",
    "reply_options": ["option1", "option2", ...]
}}

### 回覆範例
- Hello 階段 (class_state = "hello")
{{
    "class_state": "hello",
    "message": "你好啊，媽媽！今天過得如何？這是我們的課程：
🎖課程主題: `mission_title`🎖
課程大綱:

🖋️重點一:
🖋️重點二: ....",
    "reply_options": ["我準備好了！", "稍等一下", "老師你好帥"]
}}

- 課程輔導階段 (class_state = "class_done")
{{
    "class_state": "class_done",
    "message": "對課程還有其他疑問嗎？",
    "reply_options": ['結束課程']
}}
"""

