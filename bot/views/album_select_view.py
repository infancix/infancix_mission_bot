import discord
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
        self.clear_items()

        self.add_item(PreviousButton(self.current_page > 0))
        self.add_item(NextButton(self.current_page < self.total_pages - 1))
        if self.current_page == self.total_pages - 1:
            self.add_item(discord.ui.Button(label="查看更多繪本", url=f"https://www.canva.com/design/DAGmqP-18Qc/KLdARiNs6hcxrQyVy1qWNg/view?utm_content=DAGmqP-18Qc&utm_campaign=designshare&utm_medium=link2&utm_source=uniquelinks&utlId=h772b8e1103", row=2))

    def get_current_embed(self):
        album_info = self.album_info[self.current_page]
        thumbnail = None
        if album_info.get('purchase_status', '未購買') == '未購買':
            link_target = album_info['purchase_url']
            desc = f"[點擊官網連結，購買繪本]({link_target})"
            thumbnail = album_info['book_cover_url']
        elif album_info.get('design_id'):
            code = encode_ids(album_info['baby_id'], album_info['book_id'])
            link_target = f"https://infancixbaby120.com/babiary/{code}"
            desc = f"[👉點擊這裡瀏覽整本繪本]({link_target})"
            thumbnail = f"https://infancixbaby120.com/discord_image/{album_info['baby_id']}/{album_info['book_id']}/2.png"
        else:
            desc = "繪本尚未生成，請透過「_/補上傳照片_」指令製作專屬繪本喔"

        embed = discord.Embed(
            title=album_info['book_title'],
            description=desc,
            color=discord.Color.blue()
        )
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
            embed.set_footer(text=album_info['page_progress'])

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