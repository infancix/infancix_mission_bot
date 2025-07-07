import discord
import random
from types import SimpleNamespace
from bot.config import config

class TaskSelectView(discord.ui.View):
    def __init__(self, client, task_type, mission_id, mission_result=None, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.message = None
        self.result = mission_result or {}
        self.use_image_date_string_replace_aside_text = False

        if task_type == "go_quiz":
            label = "挑戰任務 GO!"
            self.go_quiz_button = discord.ui.Button(
                custom_id="go_quiz_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_quiz_button.callback = self.go_quiz_button_callback
            self.add_item(self.go_quiz_button)
        
        if task_type == "go_skip":
            label = "跳過"
            self.go_skip_button = discord.ui.Button(
                custom_id="go_skip_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_skip_button.callback = self.go_skip_button_callback
            self.add_item(self.go_skip_button)

        if task_type == "go_submit":
            label = "送出"
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
    
    async def go_skip_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        self.use_image_date_string_replace_aside_text = True
        await self.submit_image_data(interaction)

    async def go_submit_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        await self.submit_image_data(interaction)

    async def submit_image_data(self, interaction):
        if self.result and self.mission_id in config.baby_intro_mission:
            payload = {
                'baby_name': self.result.get('baby_name'),
                'gender': self.result.get('gender'),
                'birthday': self.result.get('birthday'),
                'height': self.result.get('height'),
                'weight': self.result.get('weight'),
                'head_circumference': self.result.get('head_circumference'),
            }
            await self.client.api_utils.update_student_baby_profile(str(interaction.user.id), **payload)

        if self.result and self.result.get('image'):
            photo_result = await self.client.s3_client.process_discord_attachment(self.result.get('image'))
            if self.use_image_date_string_replace_aside_text:
                self.result['aside_text'] = f"拍攝日期: {photo_result.get('capture_date_string', '未知日期')}"
            update_status = await self.client.api_utils.update_mission_image_content(
                str(interaction.user.id), self.mission_id, image_url=photo_result.get('s3_url'), aside_text=self.result.get('aside_text'), content=self.result.get('content')
            )

            if bool(update_status):
                await self.client.api_utils.submit_generate_photo_request(str(interaction.user.id), self.mission_id)
                embed = discord.Embed(
                    title="繪本製作中，請稍等20秒"
                )
                embed.set_image(url=self.get_loading_image())
                await interaction.followup.send(embed=embed)

                # Store the message
                await self.client.api_utils.store_message(str(interaction.user.id), 'assistant', "繪本製作中，請稍等20秒")

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

    def get_loading_image():
        loading_gifs = [
            "https://infancixbaby120.com/discord_assets/loading1.gif",
            "https://infancixbaby120.com/discord_assets/loading2.gif",
            "https://infancixbaby120.com/discord_assets/loading3.gif",
            "https://infancixbaby120.com/discord_assets/loading4.gif",
            "https://infancixbaby120.com/discord_assets/loading5.gif"
        ]

        return random.choice(loading_gifs)

