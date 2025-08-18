import discord
import time

from bot.config import config
from bot.utils.id_utils import encode_ids

class AlbumView(discord.ui.View):
    def __init__(self, client, albums_info, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.album_info = albums_info
        self.message = None
        self.current_page = 0
        self.total_pages = len(albums_info)

        # Add initial buttons
        if self.total_pages > 1:
            self.update_album()

    def update_album(self):
        for item in self.children[:]:
            if isinstance(item, (PreviousButton, NextButton)):
                self.remove_item(item)

        self.add_item(PreviousButton(self.current_page > 0))
        self.add_item(NextButton(self.current_page < self.total_pages - 1))

    def get_current_embed(self):
        album_info = self.album_info[self.current_page]
        image = None
        if album_info.get('purchase_status', '未購買') == '未購買':
            desc = f"👉 找社群客服「<@1272828469469904937>」購買繪本 "
            image = album_info['book_cover_url']
        elif album_info.get('design_id'):
            code = encode_ids(album_info['baby_id'], album_info['book_id'])
            link_target = f"https://infancixbaby120.com/babiary/{code}"
            desc = f"[👉點擊這裡瀏覽整本繪本]({link_target})\n_\n📖 最佳閱覽效果提示\n跳轉至Safari或Chrome，並將手機橫向觀看。"
            image = f"https://infancixbaby120.com/discord_image/{album_info['baby_id']}/{album_info['book_id']}/2.png?t={int(time.time())}"
        else:
            image = album_info['book_cover_url']
            desc = (
                "目前任務尚未開放～\n"
                "等時間到，系統會自動推播任務\n"
                "也可以 👉 點選 `指令` > `補上傳照片` 查看"
            )

        embed = discord.Embed(
            title=album_info['book_title'],
            description=desc,
            color=0xeeb2da,
        )
        if album_info.get('book_author'):
            embed.set_author(name=album_info['book_author'])
        if image:
            embed.set_image(url=image)

        return embed

class PreviousButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="◀️ 上一本",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page -= 1

        embed = view.get_current_embed()
        view.update_album()
        await interaction.response.edit_message(embed=embed, view=view)

class NextButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="下一本 ▶️",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page += 1

        embed = view.get_current_embed()
        view.update_album()
        await interaction.response.edit_message(embed=embed, view=view)
