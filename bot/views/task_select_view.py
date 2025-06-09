import discord
from types import SimpleNamespace

from bot.config import config

class TaskSelectView(discord.ui.View):
    def __init__(self, client, task_type, mission_id, book_data, baby_data=None, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.message = None
        self.book_data = book_data
        self.baby_data = baby_data

        if task_type == "go_quiz":
            label = "挑戰任務 GO!"
            self.go_quiz_button = discord.ui.Button(
                custom_id="go_quiz_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_quiz_button.callback = self.go_quiz_button_callback
            self.add_item(self.go_quiz_button)
        
        if task_type == "go_photo":
            label = "製作繪本 GO!"
            self.go_photo_button = discord.ui.Button(
                custom_id="go_photo_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_photo_button.callback = self.go_photo_button_callback
            self.add_item(self.go_photo_button)

        if task_type == "go_aside_text":
            label = "寫下內心故事 GO!"
            self.go_aside_text_button = discord.ui.Button(
                custom_id="go_aside_text_button",
                label=label,
                style=discord.ButtonStyle.success
            )
            self.go_aside_text_button.callback = self.go_aside_text_callback
            self.add_item(self.go_aside_text_button)

        if task_type == "go_submit":
            label = "確認送出 GO!"
            self.go_submit_button = discord.ui.Button(
                custom_id="go_submit_button",
                label=label,
                style=discord.ButtonStyle.success
            )
            self.go_submit_button.callback = self.go_submit_button_callback
            self.add_item(self.go_submit_button)

    async def go_quiz_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        student_mission_info = await self.client.api_utils.get_student_mission_status(str(interaction.user.id), self.mission_id)
        student_mission_info['user_id'] = str(interaction.user.id)
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        await interaction.channel.send(f"🔥 挑戰開始！讓我來看看你對「{student_mission_info['mission_title']}」的知識掌握得怎麼樣呢 🐾✨")
        
        from bot.handlers.quiz_mission_handler import handle_quiz_round
        await handle_quiz_round(self.client, message, student_mission_info)
    
    async def go_photo_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        student_mission_info = await self.client.api_utils.get_student_mission_status(str(interaction.user.id), self.mission_id)
        student_mission_info['user_id'] = str(interaction.user.id)
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)

        from bot.handlers.photo_mission_handler import send_photo_mission_instruction
        await send_photo_mission_instruction(self.client, message, student_mission_info)

    async def go_aside_text_callback(self, interaction):
        for item in self.children:
            item.disabled = True

        description = (
            "如何寫下內心故事:\n"
            "1. 請簡短描述這張照片的故事，或是有趣的故事\n"
            "2. 最多兩行，每行20字以內\n"
        )

        await interaction.response.edit_message(
            content=description,
            view=self  # Keep the buttons disabled in the view
        )

    async def go_submit_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        payload = {}
        if int(self.mission_id) in config.baby_intro_mission:
            payload.update({
                'baby_name': self.baby_data.get('baby_name'),
                'gender': self.baby_data.get('gender'),
                'birthday': self.baby_data.get('birthday'),
                'height': self.baby_data.get('height'),
                'weight': self.baby_data.get('weight'),
                'head_circumference': self.baby_data.get('head_circumference'),
            })

        if payload:
            await self.client.api_utils.update_student_baby_profile(str(interaction.user.id), **payload)

        photo_url = await self.client.s3_client.process_discord_attachment(self.book_data.get('image_url'))
        update_status = await self.client.api_utils.update_mission_image_content(
            str(interaction.user.id), self.mission_id, image_url=photo_url, aside_text=self.book_data.get('aside_text'), content=self.book_data.get('content')
        )

        if bool(update_status):
            file = discord.File(f"bot/resource/please_waiting.gif")
            await self.client.api_utils.submit_generate_photo_request(str(interaction.user.id), self.mission_id)
            msg = "製作繪本內頁預覽會需要一點時間喔，請耐心等候一下！"
            await interaction.followup.send(msg, file=file)

            # Store the message
            await self.client.api_utils.store_message(str(interaction.user.id), 'assistant', msg)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                print("✅ 24 小時後按鈕已自動 disable")
            except discord.NotFound:
                print("❌ 訊息已刪除，無法更新")

        self.stop()
