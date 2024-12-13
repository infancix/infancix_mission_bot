import discord
from bot.config import config

class ReplyOptionView(discord.ui.View):
    def __init__(self, options):
        super().__init__(timeout=None)
        self.selected_option = None

        for idx, option in enumerate(options):
            button = discord.ui.Button(
                label=option,
                style=discord.ButtonStyle.secondary
            )
            button.callback = self.create_callback(idx)
            self.add_item(button)

    def create_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            try:
                self.selected_option = idx
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(view=self)

                self.stop()

            except Exception as e:
                # 如果有錯誤，延遲回應避免 Discord API 報錯
                await interaction.response.defer()
                raise e

        return callback


