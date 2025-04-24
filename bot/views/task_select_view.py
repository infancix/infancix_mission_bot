import discord
from types import SimpleNamespace

from bot.config import config

class TaskSelectView(discord.ui.View):
    def __init__(self, client, task_type, mission_id, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.message = None

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
            label = "照片任務 GO!"
            self.go_photo_button = discord.ui.Button(
                custom_id="go_photo_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_photo_button.callback = self.go_photo_button_callback
            self.add_item(self.go_photo_button)

    async def go_quiz_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        student_mission_info = await self.client.api_utils.get_student_mission_status(str(interaction.user.id), self.mission_id)
        student_mission_info['user_id'] = str(interaction.user.id)
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        await interaction.channel.send(f"🔥 挑戰開始！讓我來看看你對「{student_mission_info['mission_title']}」的知識掌握得怎麼樣呢 🐾✨")
        
        from bot.handlers.video_mission_handler import handle_quiz_round
        await handle_quiz_round(self.client, message, student_mission_info)
    
    async def go_photo_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        student_mission_info = await self.client.api_utils.get_student_mission_status(str(interaction.user.id), self.mission_id)
        student_mission_info['user_id'] = str(interaction.user.id)
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)

        from bot.handlers.video_mission_handler import handle_photo_round
        await handle_photo_round(self.client, message, student_mission_info)

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
