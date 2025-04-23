import discord
from bot.config import config

class OpenPhotoTaskView(discord.ui.View):
    def __init__(self, client, user_id, mission_id, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.mission_id = mission_id
        self.terminate_button = OpenPhotoTaskButton(
            client,
            user_id,
            mission_id,
            label="進入照片任務",
            msg="稍等我一下喔"
        )
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
        self, client, user_id, mission_id, label, msg, style=discord.ButtonStyle.secondary
    ):
        super().__init__(label=label, style=style)
        self.client = client
        self.user_id = user_id
        self.mission_id = mission_id
        self.msg = msg

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        self.disabled = True
        if interaction.message is None:
            return

        await interaction.message.edit(view=self.view)
        await interaction.response.send_message(self.msg)
        from bot.handlers.photo_mission_handler import handle_photo_mission_start
        await handle_photo_mission_start(self.client, user_id, self.mission_id)
