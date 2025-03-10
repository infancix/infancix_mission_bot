import discord
from bot.config import config
from bot.views.control_panel import ControlPanelView

class OpenPhotoTaskView(discord.ui.View):
    def __init__(self, client, student_mission_info, reward=20, timeout=86400):
        super().__init__(timeout=timeout)
        self.client = client
        self.student_mission_info = student_mission_info
        self.terminate_button = OpenPhotoTaskButton(client, student_mission_info, reward, label="進入照片任務", msg="稍等我一下喔")
        self.add_item(self.terminate_button)
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                print("✅ 按鈕已自動 disable")
            except discord.NotFound:
                print("❌ 訊息已刪除，無法更新")

        self.stop()

class OpenPhotoTaskButton(discord.ui.Button):
    def __init__(
        self, client, student_mission_info, reward, label, msg, style=discord.ButtonStyle.secondary
    ):
        super().__init__(label=label, style=style)
        self.client = client
        self.student_mission_info = student_mission_info
        self.mission_id = self.student_mission_info['mission_id']
        self.msg = msg
        self.reward = reward

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        self.disabled = True
        if interaction.message is None:
            return

        await interaction.message.edit(view=self.view)
        await interaction.response.send_message(self.msg)

        await interaction.user.send(
            f"🎉 恭喜完成{self.student_mission_info['mission_type']} - {self.student_mission_info['mission_title']} 第一階段的任務\n"
            f"獲得🪙{self.reward}金幣🎉\n"
            f"🐾不要忘了還有第二階段的照片任務喔💪"
        )
        await self.client.api_utils.add_gold(
            user_id,
            gold=self.reward
        )
        await self.client.api_utils.send_dm_message(
            user_id,
            f"🎉 恭喜完成{self.student_mission_info['mission_type']} - {self.student_mission_info['mission_title']} 第一階段的任務\n"
            f"獲得🪙{self.reward}金幣🎉\n"
            f"🐾不要忘了還有第二階段的照片任務喔💪"
        )

        from bot.handlers.photo_mission_handler import handle_photo_mission_start
        await handle_photo_mission_start(self.client, user_id, self.mission_id)

