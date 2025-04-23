import discord
from types import SimpleNamespace

from bot.config import config
from bot.utils.message_tracker import delete_task_entry_record

class TaskSelectView(discord.ui.View):
    def __init__(self, client, task_type, mission_id, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.message = None

        if task_type == "go_quiz":
            label = "進行小測驗 GO!"
            self.go_quiz_button = discord.ui.Button(
                custom_id="go_quiz_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_quiz_button.callback = self.go_quiz_button_callback
            self.add_item(self.go_quiz_button)
        
        if task_type == "go_photo":
            label = "進入照片任務 GO!"
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
        delete_task_entry_record(str(interaction.user.id))

        mission = await self.client.api_utils.get_mission_info(self.mission_id)
        student_mission_info = {
            **mission,
            'user_id': str(interaction.user.id),
            'assistant_id': config.MISSION_BOT_ASSISTANT,
            'mission_id': self.mission_id,
            'current_step': 3
        }
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        await interaction.response.send_message(f"準備進行小測驗囉！讓我來看看你對「{mission['mission_title']}」的知識掌握得怎麼樣呢 🐾✨")
        
        from bot.handlers.video_mission_handler import handle_quiz
        await handle_quiz(self.client, message, student_mission_info)
    
    async def go_photo_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        delete_task_entry_record(str(interaction.user.id))

        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        await interaction.response.send_message(f"準備進入照片任務囉🐾")

        from bot.handlers.photo_mission_handler import handle_photo_mission_start
        await handle_photo_mission_start(self.client, str(interaction.user.id), self.mission_id)

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
