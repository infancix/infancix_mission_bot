import discord
import time

from bot.config import config
from bot.utils.id_utils import encode_ids
from bot.utils.message_tracker import delete_theme_book_edit_record

PAGE_OFFSET_MAP = {
    0: 0,
    1: 2,
    2: 3,
    3: 4,
    4: 5,
    5: 6,
    6: 7
}

class ThemeBookView(discord.ui.View):
    def __init__(self, client, book_info, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.message = None
        self.book_info = book_info
        self.baby_id = book_info['baby_id']
        self.book_id = book_info['book_id']
        self.base_mission_id = int(book_info['mission_id'])
        self.current_page = 0
        self.total_pages = len(PAGE_OFFSET_MAP)

        # Update the book-page display
        self.update_buttons()

    def update_buttons(self):
        for item in self.children[:]:
            if isinstance(item, (PreviousButton, NextButton, SubmitButton)):
                self.remove_item(item)

        self.add_item(PreviousButton(self.current_page > 0))
        self.add_item(NextButton(self.current_page < self.total_pages - 1))
        self.add_item(SubmitButton())

    def get_current_embed(self, user_id):
        if self.current_page not in PAGE_OFFSET_MAP:
            raise ValueError(f"Invalid current_page: {self.current_page}")
        page_offset = PAGE_OFFSET_MAP[self.current_page]
        current_mission_id = self.base_mission_id + page_offset
        self.client.photo_mission_replace_index[user_id] = (page_offset, current_mission_id)
        current_page_url = f"https://infancixbaby120.com/discord_image/{self.baby_id}/{current_mission_id}.png?t={int(time.time())}"
        if page_offset == 0:
            title = "預覽：封面"
        else:
            title = "預覽：內頁"
        description = """🎯 **如何更換照片？**

**📋 操作步驟：**
`1.` 用 **[◀上一頁]** **[下一頁▶]** 瀏覽所有頁面

`2.` 看到想修改的頁面→直接上傳新照片即可自動更換

`3.` 不需修改的頁面→點 **[下一頁]** 繼續瀏覽

`4.` 全部看完滿意後→點 **[送出]** 完成製作 ✅

💡 **重點提醒：** 
- 只能修改照片，上傳即自動更換
- 不需要額外的更新或跳過按鈕
- 瀏覽完所有頁面確認滿意就送出！
- 文字為符合教育設定不可修改
"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=0xeeb2da,
        )
        embed.set_author(name=self.book_info['book_author'])
        embed.set_image(url=current_page_url)
        return embed

class PreviousButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="◀️ 上一頁",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page -= 1

        embed = view.get_current_embed(str(interaction.user.id))
        view.update_buttons()
        await interaction.response.edit_message(embed=embed, view=view)

class NextButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="下一頁 ▶️",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page += 1

        embed = view.get_current_embed(str(interaction.user.id))
        view.update_buttons()
        await interaction.response.edit_message(embed=embed, view=view)

class SubmitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="送出 (送出即無法修改)",
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view

        # clear status
        del view.client.photo_mission_replace_index[str(interaction.user.id)]

        mission_info = await view.client.api_utils.get_mission_info(view.base_mission_id)
        reward = mission_info.get('reward', 100)
        # Mission Completed
        student_mission_info = {
            'user_id': str(interaction.user.id),
            'mission_id': view.base_mission_id,
            'current_step': 4,
            'score': 1
        }
        await view.client.api_utils.update_student_mission_status(**student_mission_info)

        # Send completion message
        embed = discord.Embed(
            title="🎆 任務完成",
            description=f"已匯入繪本，可點選 `指令` > `瀏覽繪本進度` 查看整本",
            color=0xeeb2da,
        )
        await interaction.response.send_message(embed=embed)
        await view.client.api_utils.add_gold(str(interaction.user.id), gold=reward)

        # Send log to Background channel
        channel = view.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            # Log the error and return gracefully
            print(f"Error: Invalid channel for BACKGROUND_LOG_CHANNEL_ID: {config.BACKGROUND_LOG_CHANNEL_ID}")
            return

        msg_task = f"MISSION_{view.base_mission_id}_FINISHED <@{str(interaction.user.id)}>"
        await channel.send(msg_task)

        delete_theme_book_edit_record(str(interaction.user.id), view.base_mission_id)
