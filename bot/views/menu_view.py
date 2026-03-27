import discord
from bot.config import config

from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url

AGE_RANGES = [
    ("1–12 個月", "1-12"),
    #("13–24 個月", "13-24"),
    #("25–36 個月", "25-36"),
]

def months_in_bucket(selected_age_range: str) -> list[int]:
    if selected_age_range == "1-12":
        return list(range(1, 5))      # 1~12
    if selected_age_range == "13-24":
        return list(range(13, 25))     # 13~24
    if selected_age_range == "25-36":
        return list(range(25, 37))     # 25~36
    return []

def calculate_spacer(label_text: str, max_spaces: int = 40) -> str:
    label_text_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in label_text)
    spaces = max_spaces - label_text_length - 1
    return '\u2000' * max(1, spaces)

class KnowledgeMenuView(discord.ui.View):
    def __init__(self, client, user_id, timeout: float = 3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.selected_age_range: str | None = None
        self.selected_month: int | None = None
        self.selected_category: str | None = None
        self.selected_page: int = 0
        self.knowledge_group = None
        self.knowledge_list = None
        self.page_size = 4
        self.build_level1()

    # 小工具
    def clear_items(self):
        for c in list(self.children):
            self.remove_item(c)

    async def update_view(self, itx: discord.Interaction):
        await itx.response.edit_message(view=self, embed=None, attachments=[])

    # Level 1：選年齡區間
    def build_level1(self):
        self.clear_items()
        self.selected_age_range: str | None = None
        self.selected_month: int | None = None
        self.selected_category: str | None = None
        self.selected_page: int = 0
        self.knowledge_group = None
        self.knowledge_list = None

        for label, code in AGE_RANGES:
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
            )

            async def bucket_cb(itx: discord.Interaction, c=code):
                self.selected_age_range = c
                self.build_level2_months()
                await self.update_view(itx)

            btn.callback = bucket_cb
            self.add_item(btn)

    # Level 2：選月份（1月~12月 / 13~24 / 25~36）
    def build_level2_months(self):
        self.clear_items()
        self.selected_month: int | None = None
        self.selected_category: str | None = None
        self.selected_page: int = 0
        self.knowledge_group = None
        self.knowledge_list = None

        current_row = 0
        months = months_in_bucket(self.selected_age_range)
        for idx, month in enumerate(months):
            row = (idx // 3)
            btn = discord.ui.Button(
                label=f"{month}月",
                style=discord.ButtonStyle.primary,
                row=row,
            )
            current_row = row

            async def month_cb(itx: discord.Interaction, mv=month):
                self.selected_month = mv
                self.knowledge_group = await self.client.api_utils.get_mission_info(
                    month_id=mv,
                    group_by='milestone_domain',
                )
                self.build_level3_type()
                await self.update_view(itx)

            btn.callback = month_cb
            self.add_item(btn)
        
        # 返回到年齡區間
        back = discord.ui.Button(
            label="返回年齡區間",
            style=discord.ButtonStyle.secondary,
            row=current_row + 1,
        )

        async def back_cb(itx: discord.Interaction):
            self.build_level1()
            await self.update_view(itx)

        back.callback = back_cb
        self.add_item(back)

    # Level 3：選知識類型
    def build_level3_type(self):
        self.clear_items()
        self.selected_category: str | None = None
        self.selected_page: int = 0
        self.knowledge_type = None
        self.knowledge_list = None

        current_row = 0
        for i, c in enumerate(self.knowledge_group.keys()):            
            btn = discord.ui.Button(
                label=c,
                style=discord.ButtonStyle.primary,
            )
            btn.row = i // 3  # 0-2 排
            current_row = btn.row
            async def category_cb(itx: discord.Interaction, lbl=c):
                self.selected_category = lbl
                self.knowledge_list = self.knowledge_group[lbl]
                self.build_level4_post()
                await self.update_view(itx)

            btn.callback = category_cb
            self.add_item(btn)

        # 返回到月份選擇
        back = discord.ui.Button(
            label="返回月份選擇",
            style=discord.ButtonStyle.secondary,
            row=current_row + 1,
        )

        async def back_cb(itx: discord.Interaction):
            self.build_level2_months()
            await self.update_view(itx)

        back.callback = back_cb
        self.add_item(back)

    # -------- Level 4：選擇具體Post --------
    def build_level4_post(self, page: int = 0):
        self.clear_items()
        self.selected_page = page
        
        # 計算分頁
        start_idx = page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.knowledge_list))
        selected_page_posts = self.knowledge_list[start_idx:end_idx]
        menu_options = {
            'selected_age_range': self.selected_age_range,
            'selected_month': self.selected_month,
            'selected_category': self.selected_category,
            'selected_page': self.selected_page,
        }

        current_row = 0
        for i, post in enumerate(selected_page_posts):
            button = KnowledgePostButton(
                self.client, 
                self.user_id,
                menu_options,
                post
            )
            button.row = i // 2  # 0-2 排
            current_row = button.row
            self.add_item(button)

        back_button = discord.ui.Button(
            label="返回知識分類",
            style=discord.ButtonStyle.secondary,
            emoji="◀",
            row=current_row+1
        )
        
        async def back_to_type(itx: discord.Interaction):
            self.build_level3_type()
            await self.update_view(itx)
        
        back_button.callback = back_to_type
        self.add_item(back_button)
        
        # 上一頁按鈕
        if page > 0:
            prev_button = discord.ui.Button(
                label="上一頁", 
                style=discord.ButtonStyle.secondary,
                row=current_row+1
            )
            
            async def prev_page(itx: discord.Interaction):
                self.build_level4_post(page - 1)
                await self.update_view(itx)
            
            prev_button.callback = prev_page
            self.add_item(prev_button)
        
        # 頁面指示器
        total_pages = (len(self.knowledge_list) - 1) // self.page_size + 1
        if total_pages > 1:
            page_indicator = discord.ui.Button(
                label=f"{page + 1}/{total_pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=current_row+1
            )
            self.add_item(page_indicator)
        
        # 下一頁按鈕
        if end_idx < len(self.knowledge_list):
            next_button = discord.ui.Button(
                label="下一頁", 
                style=discord.ButtonStyle.secondary,
                row=current_row+1
            )
            
            async def next_page(itx: discord.Interaction):
                self.build_level4_post(page + 1)
                await self.update_view(itx)
            
            next_button.callback = next_page
            self.add_item(next_button)

class KnowledgePostButton(discord.ui.Button):
    def __init__(self, client, user_id, menu_options, post_info):
        self.client = client
        self.user_id = user_id
        self.post_info = post_info
        self.menu_options = menu_options

        super().__init__(
            label=self.setup_label(post_info),
            style=discord.ButtonStyle.primary,
            custom_id=f"knowledge_post_{post_info['mission_id']}"
        )

    def setup_label(self, post_info):
        if '週' in post_info.get('development_week', ''):
            return f"{post_info['development_week']} | {post_info['milestone_title']}"
        return post_info['milestone_title']

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        knowledge_list = await self.client.api_utils.get_mission_info(
            month_id=self.menu_options['selected_month'],
            milestone_domain=self.menu_options['selected_category']
        )

        view = KnowledgePostView(
            self.client,
            self.user_id,
            self.post_info,
            knowledge_list,
            self.menu_options
        )
        embed, files = await view.build_post_embed()
        if files:
            await interaction.edit_original_response(embed=None, view=view, attachments=files)
        else:
            await interaction.edit_original_response(embed=embed, view=view, attachments=[])

class KnowledgePostView(discord.ui.View):
    def __init__(self, client, user_id, post_info, knowledge_list, menu_options=None, timeout: float = 3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.post_info = post_info
        self.menu_options = menu_options
        self.knowledge_list = knowledge_list

        # current post index
        self.current_post_index = 0
        for idx, post in enumerate(self.knowledge_list):
            if post['mission_id'] == self.post_info['mission_id']:
                self.current_post_index = idx
                break

        self.setup_back_button()
        self.setup_navigation_buttons()

    def setup_back_button(self):
        back_button = discord.ui.Button(
            label="返回上一層",
            style=discord.ButtonStyle.secondary,
        )

        async def back_cb(itx: discord.Interaction):
            knowledge_group = await self.client.api_utils.get_mission_info(
                month_id=self.menu_options['selected_month'],
                group_by='milestone_domain',
            )
            knowledge_list = knowledge_group[self.menu_options['selected_category']]
            # rebuild book selection view
            menu_view = KnowledgeMenuView(self.client, self.user_id)
            menu_view.selected_age_range = self.menu_options['selected_age_range']
            menu_view.selected_month = self.menu_options['selected_month']
            menu_view.selected_category = self.menu_options['selected_category']
            menu_view.knowledge_group = knowledge_group
            menu_view.knowledge_list = knowledge_list
            menu_view.build_level4_post(page=self.menu_options['selected_page'])
            await itx.response.edit_message(embed=None, view=menu_view, attachments=[])

        back_button.callback = back_cb
        self.add_item(back_button)

    def setup_navigation_buttons(self):
        prev_button = discord.ui.Button(
            label="上一篇文章",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_post_index == 0) # disable if first post
        )

        async def prev_cb(itx: discord.Interaction):
            if self.current_post_index > 0:
                self.current_post_index -= 1
                self.post_info = self.knowledge_list[self.current_post_index]

                prev_button.disabled = (self.current_post_index == 0)
                next_button.disabled = (self.current_post_index == len(self.knowledge_list) - 1)

                embed, files = await self.build_post_embed()
                if files:
                    await itx.response.edit_message(embed=None, view=self, attachments=files)
                else:
                    await itx.response.edit_message(embed=embed, view=self, attachments=[])
            else:
                await itx.response.send_message("已經是第一篇文章囉！", ephemeral=True)

        prev_button.callback = prev_cb
        self.add_item(prev_button)

        next_button = discord.ui.Button(
            label="下一篇文章",
            style=discord.ButtonStyle.primary,
            disabled=(self.current_post_index == len(self.knowledge_list) - 1) # disable if last post
        )

        async def next_cb(itx: discord.Interaction):
            if self.current_post_index + 1 < len(self.knowledge_list):
                self.current_post_index += 1
                self.post_info = self.knowledge_list[self.current_post_index]

                # 更新按鈕狀態
                prev_button.disabled = (self.current_post_index == 0)
                next_button.disabled = (self.current_post_index == len(self.knowledge_list) - 1)

                embed, files = await self.build_post_embed()
                if files:
                    await itx.response.edit_message(embed=None, view=self, attachments=files)
                else:
                    await itx.response.edit_message(embed=embed, view=self, attachments=[])
            else:
                await itx.response.send_message("已經是最後一篇文章囉！", ephemeral=True)

        next_button.callback = next_cb
        self.add_item(next_button)

    async def build_post_embed(self):
        video_url = self.post_info.get('milestone_video_contents', '').strip()
        image_url = self.post_info.get('milestone_image_contents', '').strip()
        instruction = ""
        if video_url and image_url:
            instruction = f"▶️ [教學影片]({video_url})\u2003\u2003📂 [圖文懶人包]({image_url})\n"
        elif video_url:
            instruction = f"▶️ [教學影片]({video_url})\n"

        embed = discord.Embed(
            title=f"🧠 **{self.post_info['milestone_title']}**",
            description=(
                f"{self.post_info['mission_instruction']}\n\n"
                f"{instruction}\n"
            ),
            color=0xeeb2da
        )
        embed.set_author(name=f"{self.post_info['development_week']}")
        embed.set_footer(text="用科學育兒，用愛紀錄成長")

        files = []
        if '週' in self.post_info['development_week']:
            for url in self.post_info['milestone_image_contents'].split(','):
                if url.strip():
                    file = await create_file_from_url(url.strip())
                    if file:
                        files.append(file)

        return embed, files
