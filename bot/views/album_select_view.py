import discord
import time
import calendar
from datetime import datetime

from bot.config import config
from bot.utils.id_utils import encode_ids
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.views.task_select_view import TaskSelectView

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
    ("pregnancy", "懷孕特別版（敬請期待）", False),
    (1, "0–1 歲", True),
]

BOOK_TYPES = {
    "成長繪本": "成長繪本",
    "主題寶寶書": "主題寶寶書",
    # "周年特別版繪本": "特別版",
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
    def __init__(self, client, timeout: float = 3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.age_code: str | None = None   # "pregnancy" / "1-12" ...
        self.book_type: str | None = None  # "growth_book" / ...
        self.build_level1()

    # -------- 共用工具 --------
    def clear_items(self):
        for c in list(self.children):
            self.remove_item(c)

    async def update_view(self, itx: discord.Interaction):
        await itx.response.edit_message(view=self)

    # -------- Level 1：選年齡 --------
    def build_level1(self):
        self.clear_items()
        self.age_code = None
        self.book_type = None

        for code, label, enabled in BOOK_AGE_OPTIONS:
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
                disabled=not enabled,
            )

            if code == 1:
                async def age_cb(itx: discord.Interaction, c=code):
                    self.age_code = c
                    self.build_level2_type()
                    await self.update_view(itx)

                btn.callback = age_cb
                self.add_item(btn)
                continue

            # 🔸 懷孕特別版（敬請期待）：secondary，點了只提示
            if code == "pregnancy":
                async def teaser_cb(itx: discord.Interaction, lbl=label):
                    await itx.response.send_message(
                        f"💛「{lbl.replace('（敬請期待）', '')}」還在準備中，完成後會在這裡開放喔！",
                        ephemeral=True,
                    )

                btn.callback = teaser_cb
                self.add_item(btn)
                continue

    # -------- Level 2：選繪本類型 --------
    def build_level2_type(self):
        self.clear_items()

        back = discord.ui.Button(
            label="返回年齡選擇",
            style=discord.ButtonStyle.secondary,
        )

        async def back_cb(itx: discord.Interaction):
            self.build_level1()
            await self.update_view(itx)

        back.callback = back_cb
        self.add_item(back)

        for label in BOOK_TYPES:
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
            )

            async def type_cb(itx: discord.Interaction, t=label):
                self.book_type = t
                await self.handle_type_click(itx, t)

            btn.callback = type_cb
            self.add_item(btn)

    # -------- Level 3：依「類型」決定行為 --------
    async def handle_type_click(self, itx: discord.Interaction, book_type: str):
        user_id = str(itx.user.id)
        age_code = self.age_code
    
        book_list = await self.client.api_utils.get_student_album_purchase_status(
            user_id,
            age_range=age_code,
            book_type=book_type,
        )

        if not book_list:
            await itx.response.send_message(
                f"「{age_code}」目前尚未開放。",
                ephemeral=True,
            )
            return

        view = discord.ui.View()
        view.add_item(AlbumSelect(self.client, user_id, age_code, book_type, book_list))

        embed = discord.Embed(
            title=f"📘 請選擇要製作的{BOOK_TYPES.get(book_type, "繪本")}",
            description=f"年齡分類：{age_code}",
            color=0xeeb2da,
        )

        await itx.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )

class AlbumSelect(discord.ui.Select):
    def __init__(self, client, user_id, age_code, book_type, book_list):
        self.client = client
        self.user_id = user_id
        self.age_code = age_code
        self.book_type = book_type
        self.book_list = book_list

        options = []
        for album in self.book_list:
            label = f"{album['book_type']} | {album['book_title']}"
            if album.get('purchase_status', '未購買') == '已購買':
                if album.get("shipping_status", "待確認") == "待確認":
                    description = f"狀態: 製作中"
                else:
                    description = f"狀態: {album.get('shipping_status')}"
            else:
                description = f"狀態: {album.get('purchase_status', '未購買')}"

            options.append(discord.SelectOption(
                label=label,
                description=description,
                value=str(album['book_id'])
            ))

        super().__init__(
            placeholder="選擇要查看的繪本...",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_book_id = int(self.values[0])
        album_status = next((album for album in self.book_list
                             if album['book_id'] == selected_book_id), None)
        if not album_status:
            await interaction.followup.send("找不到選取的繪本資料，請稍後再試。", ephemeral=True)
            return

        album_info = await self.client.api_utils.get_album_info(book_id=selected_book_id)
        album_info.update(album_status)

        incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(
            user_id=str(interaction.user.id),
            book_id=selected_book_id
        )

        view = AlbumView(
            self.client,
            self.user_id,
            album_info,
            incomplete_missions,
            age_code=self.age_code,
            book_type=self.book_type,
        )
        embed = view.preview_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class AlbumView(discord.ui.View):
    def __init__(self, client, user_id, album_info, incomplete_missions, age_code, book_type, timeout=None):
        self.client = client
        self.album_info = album_info
        self.user_id = user_id
        self.book_id = album_info['book_id']
        self.baby_id = album_info['baby_id']
        self.age_code = age_code
        self.book_type = book_type
        self.design_id = encode_ids(self.baby_id, self.book_id)
        self.incomplete_missions = incomplete_missions
        self.next_mission_id = None
        self.message = None

        if timeout is None and self.is_confirm_view_enabled():
            timeout = calculate_deadline_timeout(self.client)
        super().__init__(timeout=timeout)

        self.setup_back_button()
        self.setup_revise_button()
        self.setup_main_cta_button()

    def setup_back_button(self):
        back_button = discord.ui.Button(
            label="返回上一層",
            style=discord.ButtonStyle.secondary,
        )

        async def back_cb(itx: discord.Interaction):
            book_list = await self.client.api_utils.get_student_album_purchase_status(
                str(itx.user.id),
                age_range=self.age_code,
                book_type=self.book_type,
            )

            if not book_list:
                await itx.response.edit_message(
                    content=f"「{self.age_code}」目前尚未開放。",
                    embed=None,
                    view=None,
                )
                return

            # rebuild book selection view
            view = discord.ui.View()
            view.add_item(
                AlbumSelect(
                    self.client,
                    self.user_id,
                    self.age_code,
                    self.book_type,
                    book_list
                )
            )

            embed = discord.Embed(
                title=f"📘 請選擇要製作的{BOOK_TYPES.get(book_type, "繪本")}",
                description=f"年齡分類：{self.age_code}",
                color=0xeeb2da,
            )

            await itx.response.edit_message(embed=embed, view=view)

        back_button.callback = back_cb
        self.add_item(back_button)

    def setup_revise_button(self):
        disabled = False if self.album_info.get('shipping_status', '待確認') == '待確認' else True
        revise_button = discord.ui.Button(
            label="修改照片",
            style=discord.ButtonStyle.primary,
            disabled=True #disabled, # 先關閉修改照片功能
        )

        async def revise_cb(itx: discord.Interaction):
            await self.go_next_missions_button_callback(itx)

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

    def is_confirm_view_enabled(self):
        if len(self.incomplete_missions) == 0 and self.album['completed_mission_count'] > 0 and self.album_info.get('purchase_status') == '已購買' and self.album_info.get('shipping_status') == '待確認':
            return True
        return False

    def need_intro_mission(self):
        if self.album_info.get('completed_mission_count', 0) > 0:
            return False
        return True

    def preview_embed(self):
        if self.is_confirm_view_enabled():
            preview_embed = self.confirm_preview_embed()
        else:
            preview_embed = self.normal_preview_embed()
        return preview_embed

    def normal_preview_embed(self):
        embed = discord.Embed(
            title=f"{self.album_info['book_title']}**",
            description=(
                f"✨ **{self.album_info['book_introduction']}\n\n"
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

        if self.album_info.get('purchase_status', '未購買') != '未購買':
            embed.description += (
                f"想收藏這本屬於你與寶寶的故事嗎？\n"
                f"🛍️ 購買繪本: @社群管家阿福將私訊您，協助您下單。"
            )

        embed.set_image(url=self.album_info['book_cover_url'])
        embed.set_footer(
            text="有任何問題，隨時聯絡社群客服「阿福」。"
        )
        return embed

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
        embed.set_footer(
            text="有任何問題，隨時聯絡社群客服「阿福」。"
        )
        return embed

    async def go_next_missions_button_callback(self, interaction: discord.Interaction, next_mission_id=None):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        if not next_mission_id:
            await interaction.followup.send("繪本尚未開放，未來會第一時間通知您喔!💌。", ephemeral=True)
            return

        if next_mission_id in config.theme_mission_list:
            from bot.handlers.theme_mission_handler import handle_theme_mission_start
            await handle_theme_mission_start(self.client, self.user_id, next_mission_id)
        elif next_mission_id in config.audio_mission:
            from bot.handlers.audio_mission_handler import handle_audio_mission_start
            await handle_audio_mission_start(self.client, self.user_id, next_mission_id)
        elif next_mission_id in config.questionnaire_mission:
            from bot.handlers.questionnaire_mission_handler import handle_questionnaire_mission_start
            await handle_questionnaire_mission_start(self.client, self.user_id, next_mission_id)
        elif next_mission_id in config.baby_profile_registration_missions:
            from bot.handlers.profile_handler import handle_registration_mission_start
            await handle_registration_mission_start(self.client, self.user_id, next_mission_id)
        elif next_mission_id in config.relation_or_identity_mission:
            from bot.handlers.relation_or_identity_handler import handle_relation_identity_mission_start
            await handle_relation_identity_mission_start(self.client, self.user_id, next_mission_id)
        elif next_mission_id in config.add_on_photo_mission:
            from bot.handlers.add_on_mission_handler import handle_add_on_mission_start
            await handle_add_on_mission_start(self.client, self.user_id, next_mission_id)
        else:
            from bot.handlers.photo_mission_handler import handle_photo_mission_start
            await handle_photo_mission_start(self.client, self.user_id, next_mission_id, send_weekly_report=1)

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
        self.stop()
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)

        user = self.client.get_user(self.user_id)
        if user:
            timeout_embed = discord.Embed(
                title="繪本確認逾時通知",
                description=(
                    "很抱歉，您未在期限內完成繪本確認。\n"
                    "請於下個月 1 號重新製作並送出繪本。\n\n"
                    "若有任何問題，隨時聯絡社群客服「阿福 <@1272828469469904937>」。"
                ),
                color=0xeeb2da,
            )
            try:
                await user.send(embed=timeout_embed)
            except discord.Forbidden:
                print(f"無法傳送訊息給用戶 {self.user_id}，可能已封鎖機器人。")

class PreviousButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="⬅上一頁",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.page -= 1
        view.setup_select_options()
        view.update_buttons()
        await interaction.response.edit_message(view=view)

class NextButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="下一頁⮕",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.page += 1
        view.setup_select_options()
        view.update_buttons()
        await interaction.response.edit_message(view=view)

class PageIndicator(discord.ui.Button):
    def __init__(self, current_page, total_pages):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=f"{current_page + 1}/{total_pages}",
            disabled=True,
            row=1
        )
