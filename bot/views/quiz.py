import discord
from bot.config import config

class QuizView(discord.ui.View):
    def __init__(self, options, timeout=60):
        super().__init__(timeout=timeout)
        self.selected_option = None

        for idx, option in enumerate(options):
            button = discord.ui.Button(label=option['option'], custom_id=str(idx))
            button.callback = self.create_callback(idx)
            self.add_item(button)

    def create_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            self.selected_option = idx
            self.stop()
            if not interaction.response.is_done():
                await interaction.response.defer()
            else:
                print("互動已經完成，無法再次回覆。")
        return callback

