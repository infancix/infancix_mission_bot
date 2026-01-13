import discord
import time
import calendar
from datetime import datetime

from bot.config import config
from bot.utils.id_utils import encode_ids
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.views.task_select_view import TaskSelectView
from bot.views.theme_book_view import EditThemeBookView

weekday_map = {
    0: "星期一",
    1: "星期二",
    2: "星期三",
    3: "星期四",
    4: "星期五",
    5: "星期六",
    6: "星期日",
}

number_emojis = [
    "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"
]

BOOK_AGE_OPTIONS = [
    (1, "0–1 歲"),
    #(2, "1–2 歲"),
]

BOOK_TYPES = [
    "成長繪本",
    "主題寶寶書",
    #"特別版"
]

BOOK_CATALOGS = {
    '特別版': {
        0: [
            {'book_id': 21, 'book_title': '生日什麼時候才會來'},
            {'book_id': 64, 'book_title': '我好期待你的到來'},
        ]
    },
    '成長繪本': {
        1: [
            {'book_id': 1, 'book_title': '第一個月：新手地圖篇'},
            {'book_id': 2, 'book_title': '第二個月：照顧者的魔法篇'},
            {'book_id': 3, 'book_title': '第三個月：大樹屋冒險篇'},
            {'book_id': 4, 'book_title': '第四個月：兔子的彩虹慶典'},
            #{'book_id': 5, 'book_title': '第五個月：挑食的國王'},
            #{'book_id': 6, 'book_title': '第六個月：與媽媽逛街去'},
            #{'book_id': 7, 'book_title': '第七個月：冒險學校的挑戰(上)'},
            #{'book_id': 8, 'book_title': '第八個月：冒險學校的挑戰(下)'},
            #{'book_id': 9, 'book_title': '第九個月：牙齒城堡'},
            #{'book_id': 10, 'book_title': '第十個月：森林魔法的試煉篇'},
            #{'book_id': 11, 'book_title': '第十一個月：海底挑戰賽'},
            #{'book_id': 12, 'book_title': '第十二個月：森林裡的祕密水果'},
        ]
    },
    '主題寶寶書': {
        1: [
            {'book_id': 13, 'book_title': '認識動物 | 動物大冒險'},
            {'book_id': 14, 'book_title': '認識家人 | 他們好愛我'},
            {'book_id': 15, 'book_title': '認識周邊物品 | 在哪裡呢?'},
            {'book_id': 16, 'book_title': '認識親子互動 | 我喜歡和你在一起'},
            {'book_id': 17, 'book_title': '認識情緒 | 我感覺..'},
            {'book_id': 18, 'book_title': '認識身體部位 | 誰最厲害?'},
        ]
    }
}

def calculate_deadline_timeout(client):
    """計算到本月 5 號 23:59:59 的剩餘秒數"""
    now = datetime.now()
    current_year = now.year
    current_month = now.month
    deadline = datetime(current_year, current_month, client.submit_deadline, 23, 59, 59)
    remaining_seconds = (deadline - now).total_seconds()
    return max(remaining_seconds, 0)

def calculate_next_month():
    """計算下個月的月份和年份"""
    now = datetime.now()
    if 1 <= now.day <= 5:
        next_month = now.month + 1 if now.month < 12 else 1
        next_year = now.year if now.month < 12 else now.year + 1
        return now.month, now.year, next_month, next_year
    else:
        current_month = now.month + 1 if now.month < 12 else 1
        current_year = now.year if now.month < 12 else now.year + 1
        next_month = now.month + 2 if now.month < 11 else (now.month + 2) % 12
        next_year = now.year if now.year < 11 else now.year + 1
        return current_month, current_year, next_month, next_year

def calculate_weekday(year, month, day):
    """計算指定日期是星期幾，返回 0 (星期一) 到 6 (星期日)"""
    week_index = datetime(year, month, day).weekday()
    return weekday_map.get(week_index, "")

class BookMenuView(discord.ui.View):
    def __init__(self, client, user_id, timeout: float = 3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.age_code: str | None = None   # "pregnancy" / "1-12" ...
        self.book_type: str | None = None  # "growth_book" / ...
        self.book_list: list = []  # 繪本列表
        self.current_page: int = 0  # 當前頁碼
        self.page_size: int = 4  # 每頁顯示數量
        #self.build_level1()

        self.age_code = 1
        self.book_type = '成長繪本'
        self.book_list = BOOK_CATALOGS.get(self.book_type, {}).get(self.age_code, [])
        self.build_level3_book(page=0)

    # -------- 共用工具 --------
    def clear_items(self):
        for c in list(self.children):
            self.remove_item(c)

    async def update_view(self, itx: discord.Interaction):
        embed = self.get_current_embed()
        await itx.response.edit_message(embed=embed, view=self)

    # -------- Level 1：選類型 --------
    def build_level1(self):
        self.clear_items()
        self.age_code = None
        self.book_type = None
        self.book_list = []
        self.current_page = 0

        for label in BOOK_TYPES:
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
            )

            if label == '成長繪本': # go level 2
                async def type_cb(itx: discord.Interaction, book_type: str=label):
                    self.book_type = book_type
                    self.build_level2_type()
                    await self.update_view(itx)

                btn.callback = type_cb
                self.add_item(btn)

            elif label == '主題寶寶書':
                async def type_cb(itx: discord.Interaction, book_type: str=label):
                    self.book_type = book_type
                    self.age_code = 1 # 主題書沒有年齡區間
                    self.book_list = BOOK_CATALOGS.get(self.book_type, {}).get(self.age_code, [])
                    self.build_level3_book()
                    await self.update_view(itx)

                btn.callback = type_cb
                self.add_item(btn)

            elif label == '特別版': # go level 3
                async def special_cb(itx: discord.Interaction, book_type: str=label):
                    self.book_type = book_type
                    self.age_code = 0 # 特別版沒有年齡區間
                    self.book_list = BOOK_CATALOGS.get(self.book_type, {}).get(self.age_code, [])
                    self.build_level3_book()
                    await self.update_view(itx)

                btn.callback = special_cb
                self.add_item(btn)

    # -------- Level 2：選年齡區間 --------
    def build_level2_type(self):
        self.clear_items()
        self.age_code = None
        self.book_list = []
        self.current_page = 0

        back = discord.ui.Button(
            label="返回類型選擇",
            style=discord.ButtonStyle.secondary,
        )

        async def back_cb(itx: discord.Interaction):
            self.build_level1()
            await self.update_view(itx)

        back.callback = back_cb
        self.add_item(back)

        for code, age_label in BOOK_AGE_OPTIONS:
            btn = discord.ui.Button(
                label=age_label,
                style=discord.ButtonStyle.primary,
            )

            async def age_cb(itx: discord.Interaction, c=code):
                self.age_code = c
                self.book_list = BOOK_CATALOGS.get(self.book_type, {}).get(self.age_code, [])
                self.build_level3_book(page=0)
                await self.update_view(itx)

            btn.callback = age_cb
            self.add_item(btn)

    # -------- Level 3：選擇具體繪本 --------
    def build_level3_book(self, page: int = 0):
        self.clear_items()
        self.current_page = page

        # 計算分頁
        start_idx = page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.book_list))
        current_page_books = self.book_list[start_idx:end_idx]
        menu_options = {
            'age_code': self.age_code,
            'book_type': self.book_type,
            'current_page': self.current_page,
        }

        current_row = 0
        for i, book in enumerate(current_page_books):
            button = AlbumButton(
                self.client, 
                self.user_id,
                menu_options,
                book
            )
            button.row = i // 2  # 0-2 排
            current_row = button.row
            self.add_item(button)

        # 返回繪本分類按鈕
        back_button = discord.ui.Button(
            label="返回繪本分類",
            style=discord.ButtonStyle.secondary,
            emoji="◀",
            row=current_row+1
        )

        async def back_to_type(itx: discord.Interaction):
            if self.book_type == '成長繪本':
                self.build_level2_type()
            else:
                self.build_level1()
            await self.update_view(itx)

        #back_button.callback = back_to_type
        #self.add_item(back_button)

        # 上一頁按鈕
        if page > 0:
            prev_button = discord.ui.Button(
                label="上一頁", 
                style=discord.ButtonStyle.secondary,
                row=current_row+1
            )

            async def prev_page(itx: discord.Interaction):
                self.build_level3_book(page - 1)
                await self.update_view(itx)

            prev_button.callback = prev_page
            self.add_item(prev_button)

        # 頁面指示器
        total_pages = (len(self.book_list) - 1) // self.page_size + 1
        if total_pages > 1:
            page_indicator = discord.ui.Button(
                label=f"{page + 1}/{total_pages}",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=current_row+1
            )
            self.add_item(page_indicator)

        # 下一頁按鈕
        if end_idx < len(self.book_list):
            next_button = discord.ui.Button(
                label="下一頁", 
                style=discord.ButtonStyle.secondary,
                row=current_row+1
            )

            async def next_page(itx: discord.Interaction):
                self.build_level3_book(page + 1)
                await self.update_view(itx)

            next_button.callback = next_page
            self.add_item(next_button)

    def get_current_embed(self):
        """根據當前狀態返回對應的 embed"""
        if self.book_type is None:
            return self.create_level1_embed()
        elif self.age_code is None:
            return self.create_level2_embed()
        else:
            return self.create_level3_embed()

    def create_level1_embed(self):
        """建立 Level 1 的 Embed"""
        embed = discord.Embed(
            title=f"📘 請選擇要製作的繪本類型",
            color=0xeeb2da
        )
        embed.set_image(url="https://infancixbaby120.com/discord_assets/book_type.jpg")
        return embed

    def create_level2_embed(self):
        embed = discord.Embed(
            title=f"📘 請選擇年齡區間 - {self.book_type}",
            color=0xeeb2da
        )
        return embed

    def create_level3_embed(self):
        embed = discord.Embed(
            title=f"📘 選擇繪本 - {self.book_type}",
            color=0xeeb2da
        )
        return embed

class AlbumButton(discord.ui.Button):
    def __init__(self, client, user_id, menu_options, book_info):
        self.client = client
        self.user_id = user_id
        self.book_info = book_info
        self.menu_options = menu_options

        super().__init__(
            label=book_info['book_title'],
            style=discord.ButtonStyle.primary,
            custom_id=f"album_{book_info['book_id']}"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        book_info = await self.client.api_utils.get_album_info(book_id=self.book_info['book_id'])
        book_status = await self.client.api_utils.get_student_album_purchase_status(self.user_id, book_id=self.book_info['book_id']) or {}
        book_info.update(book_status)
        completed_missions = await self.client.api_utils.get_student_complete_photo_mission(
            user_id=str(interaction.user.id),
            book_id=self.book_info['book_id']
        )
        incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(
            user_id=str(interaction.user.id),
            book_id=self.book_info['book_id']
        )

        view = AlbumView(
            self.client,
            self.user_id,
            book_info,
            completed_missions,
            incomplete_missions,
            self.menu_options
        )
        embed, file_path, filename, fallback_url = view.preview_embed()
        await view.send_embed_with_file(
            interaction, embed, view, file_path, filename, fallback_url, use_response=False
        )

class AlbumView(discord.ui.View):
    def __init__(self, client, user_id, album_info, completed_missions=[], incomplete_missions=[], menu_options={}, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.album_info = album_info
        self.user_id = user_id
        self.book_id = album_info['book_id']
        self.baby_id = album_info['baby_id']
        self.menu_options = menu_options
        self.design_id = encode_ids(self.baby_id, self.book_id)
        self.completed_missions = completed_missions
        self.incomplete_missions = incomplete_missions
        self.next_mission_id = None
        self.message = None

        if self.menu_options:
            self.setup_back_button()
        self.setup_revise_button()
        self.setup_main_cta_button()

    async def send_embed_with_file(self, interaction, embed, view=None, file_path=None, filename=None, fallback_url=None, use_response=True):
        """
        Helper to send embed with file attachment, with fallback to URL if file not found.

        Args:
            interaction: Discord interaction object
            embed: Discord embed object
            view: View object (defaults to self)
            file_path: Path to file to attach
            filename: Filename for attachment
            fallback_url: Fallback URL to use if file not found
            use_response: If True, use response.edit_message; if False, use edit_original_response
        """
        if view is None:
            view = self

        try:
            if file_path:
                file = discord.File(file_path, filename=filename)
                if use_response:
                    await interaction.response.edit_message(embed=embed, view=view, attachments=[file])
                else:
                    await interaction.edit_original_response(embed=embed, view=view, attachments=[file])
            else:
                raise FileNotFoundError("No file_path provided")
        except FileNotFoundError:
            if fallback_url:
                self.client.logger.warning(f"File not found: {file_path}, using fallback URL: {fallback_url}")
                embed.set_image(url=fallback_url)
            if use_response:
                await interaction.response.edit_message(embed=embed, view=view, attachments=[])
            else:
                await interaction.edit_original_response(embed=embed, view=view, attachments=[])
        except Exception as e:
            self.client.logger.error(f"Error loading file {file_path}: {e}")
            if fallback_url:
                embed.set_image(url=fallback_url)
            if use_response:
                await interaction.response.edit_message(embed=embed, view=view, attachments=[])
            else:
                await interaction.edit_original_response(embed=embed, view=view, attachments=[])

    def setup_back_button(self):
        back_button = discord.ui.Button(
            label="返回上一層",
            style=discord.ButtonStyle.secondary,
        )

        async def back_cb(itx: discord.Interaction):
            book_list = BOOK_CATALOGS.get(self.menu_options['book_type'], {}).get(self.menu_options['age_code'], [])
            # rebuild book selection view
            menu_view = BookMenuView(self.client, self.user_id)
            menu_view.age_code = self.menu_options['age_code']
            menu_view.book_type = self.menu_options['book_type']
            menu_view.book_list = book_list
            menu_view.build_level3_book(page=self.menu_options['current_page'])
            embed = menu_view.get_current_embed()
            await itx.response.edit_message(embed=embed, view=menu_view, attachments=[])

        back_button.callback = back_cb
        self.add_item(back_button)

    def setup_revise_button(self):
        disabled = False
        if self.completed_missions is None or len(self.completed_missions) == 0:
            disabled = True
        if self.album_info.get('shipping_status', '待確認') != '待確認':
            disabled = True
        revise_button = discord.ui.Button(
            label="修改繪本內容",
            style=discord.ButtonStyle.primary,
            disabled=disabled,
        )

        async def revise_cb(itx: discord.Interaction):
            book_info = await self.client.api_utils.get_album_info(book_id=self.book_id) or {}
            book_status = await self.client.api_utils.get_student_album_purchase_status(self.user_id, book_id=self.book_id) or {}
            book_info.update(book_status)
            submitted_missions = await self.client.api_utils.get_student_complete_photo_mission(
                user_id=str(itx.user.id),
                book_id=self.book_id
            )

            if self.menu_options.get('book_type') == '寶寶主題書':
                from bot.handlers.theme_mission_handler import handle_theme_mission_restart
                await handle_theme_mission_restart(self.client, str(itx.user.id), self.book_id)
                view = EditThemeBookView(self.client, book_info)
                embed, file_path, filename = view.get_current_embed(str(itx.user.id))
                await self.send_embed_with_file(itx, embed, view, file_path, filename, use_response=True)
            else:
                view = EditGrowthBookView(self.client, str(itx.user.id), book_info, submitted_missions, self.menu_options)
                embed, file_path, filename = view.build_preview_page()
                await self.send_embed_with_file(itx, embed, view, file_path, filename, use_response=True)

        revise_button.callback = revise_cb
        self.add_item(revise_button)

    def setup_main_cta_button(self):
        if self.album_info.get('shipping_status', '待確認') != '待確認':
            main_button = discord.ui.Button(
                label="已送印",
                style=discord.ButtonStyle.success,
                disabled=True,
            )
            # No action needed, just disabled

        elif self.is_confirm_view_enabled():
            main_button = discord.ui.Button(
                label="確認送印",
                style=discord.ButtonStyle.success,
            )
            async def confirm_cb(itx: discord.Interaction):
                await self.confirm_button_callback(itx)
            main_button.callback = confirm_cb

        elif self.need_intro_mission():
            main_button = discord.ui.Button(
                label="開始製作",
                style=discord.ButtonStyle.success,
            )
            next_mission_id = config.book_intro_mission_map.get(self.book_id)
            async def start_cb(itx: discord.Interaction):
                await self.go_next_missions_button_callback(itx, next_mission_id)
            main_button.callback = start_cb

        elif len(self.incomplete_missions) == 0 and self.album_info.get('purchase_status') != '已購買':
            main_button = discord.ui.Button(
                label="購買繪本",
                style=discord.ButtonStyle.success,
            )
            async def purchase_cb(itx: discord.Interaction):
                await self.purchase_button_callback(itx)
            main_button.callback = purchase_cb

        else:
            main_button = discord.ui.Button(
                label="繼續製作",
                style=discord.ButtonStyle.success,
            )
            next_mission_id = self.incomplete_missions[0]['mission_id'] if self.incomplete_missions else None
            async def continue_cb(itx: discord.Interaction):
                await self.go_next_missions_button_callback(itx, next_mission_id)
            main_button.callback = continue_cb

        # Add the main CTA button
        self.add_item(main_button)

    def is_confirm_view_enabled(self):
        if len(self.incomplete_missions) == 0 \
            and self.album_info.get('completed_mission_count', 0) > 0 \
            and self.album_info.get('purchase_status') == '已購買' \
            and self.album_info.get('shipping_status') == '待確認':
            return True
        return False

    def need_intro_mission(self):
        if self.album_info.get('completed_mission_count', 0) > 0:
            return False
        return True

    def preview_embed(self):
        if self.is_confirm_view_enabled():
            preview_embed, file_path, filename, fallback_url = self.confirm_preview_embed()
        else:
            preview_embed, file_path, filename, fallback_url = self.normal_preview_embed()
        return preview_embed, file_path, filename, fallback_url

    def normal_preview_embed(self):
        embed = discord.Embed(
            title=f"**{self.album_info['book_title']}**",
            description=(
                f"**{self.album_info['book_introduction']}**\n\n"
                f"🔗[繪本預覽]({f"https://infancixbaby120.com/babiary/{self.design_id}"})\n\n"
                f"繪本進度: \n"
            ),
            color=0xeeb2da,
        )

        if len(self.incomplete_missions) > 0:
            embed.description += f"目前繪本尚有 {len(self.incomplete_missions)} 頁未完成，點擊下方按鈕繼續製作喔！\n\n"
        else:
            if self.album_info.get('purchase_status', '未購買') == '已購買':
                embed.description += f"💛 您的繪本已 {self.album_info['shipping_status']}\n\n"
            else:
                embed.description += f"💛 您的體驗任務完成囉！\n\n"

        if self.album_info.get('purchase_status', '未購買') != '已購買':
            embed.description += (
                f"想收藏這本屬於你與寶寶的故事嗎？\n"
                f"🛍️ 購買繪本: @社群管家阿福將私訊您，協助您下單。"
            )

        intro_mission_id = config.book_intro_mission_map.get(self.book_id)
        if self.need_intro_mission():
            if self.album_info.get('lang_version', 'zh') == 'zh':
                baby_id = 2024000001 # 中文繪本示範寶寶ID
            else:
                baby_id = 2024000002 # 英文繪本示範寶寶ID
        else:
            baby_id = self.baby_id

        file_path = f"/home/ubuntu/canva_exports/{baby_id}/{intro_mission_id}.jpg"
        filename = f"{intro_mission_id}.jpg"
        current_page_url = f"attachment://{filename}"
        fallback_url = f"https://infancixbaby120.com/discord_image/{baby_id}/{intro_mission_id}.jpg"
        embed.set_image(url=current_page_url)
        embed.set_footer(
            text="有任何問題，隨時聯絡社群客服「阿福」。"
        )
        return embed, file_path, filename, fallback_url

    def confirm_preview_embed(self):
        now = datetime.now()
        current_day = now.day
        deadline_day = self.client.submit_deadline
        if current_day <= deadline_day:
            deadline_month, deadline_year = now.month, now.year
            if now.month == 12:
                defer_month, defer_year = 1, now.year + 1
            else:
                defer_month, defer_year = now.month + 1, now.year
        else:
            if now.month == 12:
                deadline_month, deadline_year = 1, now.year + 1
            else:
                deadline_month, deadline_year = now.month + 1, now.year
            if deadline_month == 12:
                defer_month, defer_year = 1, deadline_year + 1
            else:
                defer_month, defer_year = deadline_month + 1, deadline_year

        deadline_str = f"{deadline_month}/{deadline_day}"
        defer_str = f"{defer_year}/{defer_month}/1" if defer_month == 1 else f"{defer_month}/1"

        preview_link = f"https://infancixbaby120.com/babiary/{self.design_id}"
        embed = discord.Embed(
            title=f"{self.album_info['book_title']} 送印確認",
            description=(
                f"📚 恭喜您，繪本已完成製作！\n\n"
                f"🔍 最後檢查:\n"
                f"請點擊下方連結確認整本內容：\n"
                f"📎[繪本預覽]({preview_link})\n"
                f"確認完成後，請點下方按鈕送印。\n\n"
                f"🚚 運送機制\n"
                f"每月 5 號統一印製，送印後約 30 個工作天 即可收到繪本囉！\n\n"
                f"📌 **重要提醒**\n"
                f"修改截止日為 **{deadline_str} 23:59**\n"
                f"若未在期限內確認，將順延至 **{defer_str}** 才能送印！\n\n"
                f"**如需修改照片**，請依下列步驟操作：\n"
                f"💬於對話框輸入 */查看育兒里程碑*，重啟任務\n"
            ),
            color=0xeeb2da,
            timestamp=datetime.now()
        )

        intro_mission_id = config.book_intro_mission_map.get(self.book_id)
        file_path = f"/home/ubuntu/canva_exports/{self.baby_id}/{intro_mission_id}.jpg"
        filename = f"{intro_mission_id}.jpg"
        current_page_url = f"attachment://{filename}"
        fallback_url = f"https://infancixbaby120.com/discord_image/{self.baby_id}/{intro_mission_id}.jpg"
        embed.set_image(url=current_page_url)
        embed.set_footer(
            text="有任何問題，隨時聯絡社群客服「阿福」。"
        )
        return embed, file_path, filename, fallback_url

    async def go_next_missions_button_callback(self, interaction: discord.Interaction, next_mission_id=None):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        if not next_mission_id:
            await interaction.followup.send("繪本尚未開放，未來會第一時間通知您喔!💌。", ephemeral=True)
            return

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        if config.ENV:
            msg_task = f"START_MISSION_DEV_{next_mission_id} <@{self.user_id}>"
        else:
            msg_task = f"START_MISSION_{next_mission_id} <@{self.user_id}>"
        await channel.send(msg_task)

    async def confirm_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        confirm_embed = discord.Embed(
            title="📘 已確認送印！",
            description=(
                "這本屬於您與寶寶的成長故事，將進入印刷流程。\n\n"
                "📦 **印刷期與運送期**\n"
                "約需**30 個工作天**，完成後將寄送至您的指定地址。\n\n"
                "🎶 **親子共讀課 X Music Together 會員專屬**\n"
                "您的繪本將於**課程當天**發放，無需等待郵寄！\n"
            ),
            color=0xeeb2da,
        )
        await interaction.followup.send(embed=confirm_embed, ephemeral=True)

        await self.client.api_utils.update_student_confirmed_growth_album(self.user_id, self.book_id)
        self.stop()

        # Send log to Background channel
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')
        msg_task = f"BOOK_{self.book_id}_CONFIRM_FINISHED <@{self.user_id}>"
        await channel.send(msg_task)

    async def purchase_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        purchase_embed = discord.Embed(
            title="🛒 繪本購買資訊",
            description=(
                "感謝您選擇購買這本屬於您與寶寶的成長故事繪本！\n\n"
                "📩 社群管家阿福將會私訊您，協助您完成下單流程。\n"
                "若有任何問題，隨時聯絡社群客服「阿福 <@1272828469469904937>」。"
            ),
            color=0xeeb2da,
        )
        await interaction.followup.send(embed=purchase_embed, ephemeral=True)

        # Send log to Background channel
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"<@{self.user_id}> 購買繪本"
        await channel.send(msg_task)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                print("✅ 1周後後按鈕已自動 disable")
            except discord.NotFound:
                print("❌ 訊息已刪除，無法更新")

        self.stop()

class EditGrowthBookView(discord.ui.View):
    def __init__(self, client, user_id, book_info, submitted_missions, menu_options={}, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.book_info = book_info
        self.user_id = user_id
        self.book_id = book_info['book_id']
        self.baby_id = book_info['baby_id']
        self.submitted_missions = [m for m in submitted_missions if m['mission_id'] in config.growth_book_mission_map.get(self.book_id, [])]
        self.menu_options = menu_options
        self.message = None

        # Pagination state
        self.total_pages = len(self.submitted_missions)
        self.mission_ids = [m['mission_id'] for m in self.submitted_missions]
        self.current_page = 0
        self.current_mission_id = self.mission_ids[self.current_page] if self.mission_ids else None

        # Setup buttons
        self.setup_buttons()

    # -------- 共用工具 --------
    def clear_items(self):
        for c in list(self.children):
            self.remove_item(c)

    async def update_view(self, itx: discord.Interaction, update_embed: discord.Embed, file_path: str, filename: str):
        file = discord.File(fp=file_path, filename=filename)
        await itx.response.edit_message(embed=update_embed, view=self, attachments=[file])

    def setup_buttons(self):
        # 上一頁按鈕
        prev_button = discord.ui.Button(
            label="上一頁", 
            style=discord.ButtonStyle.primary,
            row=0,
            disabled=self.current_page == 0
        )

        async def prev_page(itx: discord.Interaction):
            self.current_page -= 1
            await self.client.api_utils.update_student_current_mission(str(itx.user.id), self.mission_ids[self.current_page])
            embed, file_path, filename = self.build_preview_page(self.current_page)
            await self.update_view(itx, embed, file_path, filename)

        prev_button.callback = prev_page
        self.add_item(prev_button)

        # 頁面指示器
        page_indicator = discord.ui.Button(
            label=f"{self.current_page + 1}/{self.total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=0
        )
        self.add_item(page_indicator)

        # 下一頁按鈕
        next_button = discord.ui.Button(
            label="下一頁", 
            style=discord.ButtonStyle.primary,
            row=0,
            disabled=self.current_page == self.total_pages - 1
        )

        async def next_page(itx: discord.Interaction):
            self.current_page += 1
            await self.client.api_utils.update_student_current_mission(str(itx.user.id), self.mission_ids[self.current_page])
            embed, file_path, filename = self.build_preview_page(self.current_page)
            await self.update_view(itx, embed, file_path, filename)

        next_button.callback = next_page
        self.add_item(next_button)
        restart_button = discord.ui.Button(
            label="重新製作此頁",
            style=discord.ButtonStyle.primary,
            row=1
        )
        async def restart_cb(itx: discord.Interaction):
            current_mission_id = self.mission_ids[self.current_page]
            await self.restart_mission_button_callback(itx, current_mission_id)

        restart_button.callback = restart_cb
        self.add_item(restart_button)

        back_button = discord.ui.Button(
            label="返回繪本狀態",
            style=discord.ButtonStyle.secondary,
            row=1
        )

        async def back_cb(itx: discord.Interaction):
            book_info = await self.client.api_utils.get_album_info(book_id=self.book_id) or {}
            book_status = await self.client.api_utils.get_student_album_purchase_status(self.user_id, book_id=self.book_id) or {}
            book_info.update(book_status)
            completed_missions = await self.client.api_utils.get_student_complete_photo_mission(
                user_id=str(itx.user.id),
                book_id=self.book_id
            )
            incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(
                user_id=str(itx.user.id),
                book_id=self.book_id
            )

            view = AlbumView(
                self.client,
                self.user_id,
                book_info,
                completed_missions,
                incomplete_missions,
                self.menu_options
            )
            embed, file_path, filename, fallback_url = view.preview_embed()
            await view.send_embed_with_file(itx, embed, view, file_path, filename, fallback_url, use_response=True)

        back_button.callback = back_cb
        self.add_item(back_button)

    def build_preview_page(self, page: int = 0):
        self.clear_items()
        self.current_page = page
        current_mission_id = self.mission_ids[page]
        current_page_url = f"attachment://{current_mission_id}.jpg"
        description = """📖 **瀏覽你的繪本**

用 **[◀][▶]** 翻頁，不滿意某一頁就點 **[🔄 重新製作此頁]**

看完後點 **[返回繪本]** 即可
"""
        embed = discord.Embed(
            title=f"**{self.book_info['book_title']}**",
            description=description,
            color=0xeeb2da,
        )
        embed.set_author(name=self.book_info['book_collection'])

        file_path = f"/home/ubuntu/canva_exports/{self.baby_id}/{current_mission_id}.jpg"
        filename = f"{current_mission_id}.jpg"
        current_page_url = f"attachment://{filename}"
        embed.set_image(url=current_page_url)

        # Setup buttons again
        self.setup_buttons()

        return embed, file_path, filename

    async def restart_mission_button_callback(self, interaction: discord.Interaction, current_mission_id: int):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        if config.ENV:
            msg_task = f"START_MISSION_DEV_{current_mission_id} <@{self.user_id}>"
        else:
            msg_task = f"START_MISSION_{current_mission_id} <@{self.user_id}>"
        await channel.send(msg_task)
