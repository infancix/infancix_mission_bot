import discord
from bot.config import config

class ReplyOptionView(discord.ui.View):
    def __init__(self, options, timeout=86400):
        super().__init__(timeout=timeout)
        self.selected_option = None
        self.options = options
        self.message = None

        for idx, option in enumerate(options):
            button = discord.ui.Button(
                label=option,
                style=discord.ButtonStyle.primary
            )
            button.callback = self.create_callback(idx)
            self.add_item(button)

    def create_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            try:
                self.selected_option = self.options[idx]
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(view=self)
                self.stop()
            except Exception as e:
                await interaction.response.defer()
                raise e

        return callback

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

