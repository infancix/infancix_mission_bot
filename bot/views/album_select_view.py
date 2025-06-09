import discord
from types import SimpleNamespace

from bot.config import config

class AlbumView(discord.ui.View):
    def __init__(self, client, albums_info, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.album_info = albums_info
        self.message = None
        self.current_page = 0
        self.total_pages = len(albums_info)
        print("total_pages", self.total_pages, "current_page", self.current_page)

        self.update_album()
    
    def update_album(self):
        self.clear_items()

        album_info = self.album_info[self.current_page]
        if album_info.get('design_id'):
            label = "預覽整本"
            link_target = f"https://infancixbaby120.com/babiary/{album_info['design_id']}"
        else:
            label = "點我購買"
            link_target = album_info['purchase_url']

        if self.total_pages > 0:
            self.add_item(PreviousButton(self.current_page > 0))

        self.add_item(discord.ui.Button(label=label, url=link_target, row=1))
        
        if self.total_pages > 0:
            self.add_item(NextButton(self.current_page < self.total_pages - 1))
            if self.current_page == self.total_pages - 1:
                self.add_item(discord.ui.Button(label="查看更多繪本", url=f"https://www.canva.com/design/DAGmqP-18Qc/KLdARiNs6hcxrQyVy1qWNg/view?utm_content=DAGmqP-18Qc&utm_campaign=designshare&utm_medium=link2&utm_source=uniquelinks&utlId=h772b8e1103", row=2))
    
    def get_current_embed(self):
        from bot.handlers.utils import convert_image_to_preview
        album_info = self.album_info[self.current_page]
        embed = discord.Embed(
            title=album_info['book_title'],
            color=discord.Color.blue()
        )
        embed.set_image(url=convert_image_to_preview(album_info['book_cover_url']))
        return embed

class PreviousButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="◀️",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page -= 1
        view.update_album()

        embed = view.get_current_embed()
        await interaction.response.edit_message(embed=embed, view=view)

class NextButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="▶️",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page += 1
        view.update_album()

        embed = view.get_current_embed()
        await interaction.response.edit_message(embed=embed, view=view)
