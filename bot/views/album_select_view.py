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

class AlbumSelectView(discord.ui.View):
    def __init__(self, client, user_id, albums_info, timeout=3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.albums_info = albums_info
        # pagination index
        self.items_per_page = 24
        self.setup_records()
        self.page = 0

        self.setup_select_options()
        if self.needs_pagination:
            self.update_buttons()

    def setup_records(self):
        self.sorted_tasks = sorted(self.albums_info, key=lambda x: (x['age_range'], x['book_id']))
        self.total_tasks = len(self.sorted_tasks)
        self.needs_pagination = self.total_tasks > self.items_per_page
        self.total_pages = (self.total_tasks - 1) // self.items_per_page + 1 if self.total_tasks > 0 else 1

    def setup_select_options(self):
        # Remove current buttons
        for item in self.children[:]:
            if isinstance(item, AlbumSelect):
                self.remove_item(item)

        start_idx = self.page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, self.total_tasks)
        current_page_records = self.sorted_tasks[start_idx:end_idx]

        self.add_item(AlbumSelect(self.client, self.user_id, current_page_records))

    def update_buttons(self):
        # Remove current buttons
        for item in self.children[:]:
            if isinstance(item, (PreviousButton, NextButton, PageIndicator)):
                self.remove_item(item)

        self.add_item(PreviousButton(self.page > 0))
        self.add_item(PageIndicator(self.page, self.total_pages))
        self.add_item(NextButton(self.page < self.total_pages - 1))

    def preview_embed(self):
        embed = discord.Embed(
            title="我的成長書櫃",
            description="選擇下方選單，查看或確認送印您的成長繪本！",
            color=0xeeb2da,
        )
        return embed

class AlbumSelect(discord.ui.Select):
    def __init__(self, client, user_id, albums_info):
        self.client = client
        self.user_id = user_id
        self.albums_info = albums_info

        options = []
        for album in albums_info:
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
        album_info = next((album for album in self.albums_info if album['book_id'] == selected_book_id), None)
        if not album_info:
            await interaction.followup.send("找不到選取的繪本資料，請稍後再試。", ephemeral=True)
            return

        if album_info.get('intro_mission_status', 0) == 0:
            intro_mission_id = config.book_intro_mission_map[album_info['book_id']]
            mission_info = await self.client.api_utils.get_mission_info(intro_mission_id)
            album_info = {
                **album_info,
                'book_instruction': mission_info.get('mission_instruction', ''),
                'mission_instruction_image_url': mission_info.get('mission_instruction_image_url', ''),
            }

        incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(str(interaction.user.id), album_info['book_id'])
        view = AlbumView(self.client, self.user_id, album_info, incomplete_missions)
        embed = view.preview_embed()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

class AlbumView(discord.ui.View):
    def __init__(self, client, user_id, album_info, incomplete_missions, timeout=None):
        self.client = client
        self.album_info = album_info
        self.user_id = user_id
        self.book_id = album_info['book_id']
        self.baby_id = album_info['baby_id']
        self.design_id = album_info.get('design_id', None) or encode_ids(self.baby_id, self.book_id)
        self.incomplete_missions = incomplete_missions
        self.message = None

        if timeout is None and self.is_confirm_view_enabled():
            timeout = calculate_deadline_timeout(self.client)
        super().__init__(timeout=timeout)

        if self.album_info.get('purchase_status', '未購買') == '未購買':
            # Unpurchased users
            if self.album_info.get('intro_mission_status', 0) == 0:
                label="體驗製作繪本"
            else:
                label="繼續製作繪本"

            if len(self.incomplete_missions) > 0:
                self.go_next_missions_button = discord.ui.Button(
                    custom_id='go_next_missions_button',
                    label=label,
                    style=discord.ButtonStyle.secondary,
                )
                self.go_next_missions_button.callback = self.go_next_missions_button_callback
                self.add_item(self.go_next_missions_button)

            self.purchase_button = discord.ui.Button(
                custom_id='purchase_album_button',
                label="🛒 購買繪本",
                style=discord.ButtonStyle.success,
            )
            self.purchase_button.callback = self.purchase_button_callback
            self.add_item(self.purchase_button)

        else:
            # Purchased users
            if len(self.incomplete_missions) > 0:
                if self.album_info.get('intro_mission_status', 0) == 0:
                    label="開始製作封面"
                else:
                    label="繼續製作下一頁"

                self.go_next_missions_button = discord.ui.Button(
                    custom_id='go_next_missions_button',
                    label=label,
                    style=discord.ButtonStyle.secondary,
                )
                self.go_next_missions_button.callback = self.go_next_missions_button_callback
                self.add_item(self.go_next_missions_button)

            self.confirm_button = discord.ui.Button(
                custom_id='confirm_album_button',
                label="📘 確認送印",
                style=discord.ButtonStyle.success,
                disabled=not (self.is_confirm_view_enabled()),
            )
            self.confirm_button.callback = self.confirm_button_callback
            self.add_item(self.confirm_button)

    def is_confirm_view_enabled(self):
        if len(self.incomplete_missions) == 0 and self.album_info.get('purchase_status') == '已購買' and self.album_info.get('shipping_status') == '待確認':
            return True
        return False

    def preview_embed(self):
        if self.is_confirm_view_enabled():
            preview_embed = self.confirm_preview_embed()
        else:
            preview_embed = self.normal_preview_embed()
        return preview_embed

    def normal_preview_embed(self):
        if self.album_info.get('intro_mission_status') and self.baby_id != 0:
            image = f"https://infancixbaby120.com/discord_image/{self.baby_id}/{self.book_id}/2.jpg?t={int(time.time())}" 
        else:
            image = self.album_info['book_cover_url']

        if self.album_info.get('intro_mission_status', 0) == 0 and 'book_instruction' in self.album_info:
            embed = discord.Embed(
                title=self.album_info['book_title'],
                description=self.album_info['book_instruction'],
                color=0xeeb2da,
            )
            if self.album_info.get('mission_instruction_image_url', '') != '':
                image = create_preview_image_from_url(self.album_info['mission_instruction_image_url'])
        else:
            embed = discord.Embed(
                title=self.album_info['book_title'],
                description=(
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

        if self.album_info.get('purchase_status', '未購買') == '未購買':
            embed.description += (
                f"想收藏這本屬於你與寶寶的故事嗎？\n"
                f"🛍️ 購買繪本: @社群管家阿福將私訊您，協助您下單。"
            )

        embed.set_image(url=image)
        embed.set_footer(
            text="💬若按鈕無回應，請在對話框輸入 */我的書櫃* > 點選*確認送印*"
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

    async def go_next_missions_button_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        if self.album_info.get('intro_mission_status', 0) == 0:
            next_mission_id = config.book_intro_mission_map.get(self.book_id)
        else:
            next_mission_id = self.incomplete_missions[0]['mission_id'] if self.incomplete_missions else None

        if not next_mission_id:
            await interaction.followup.send("繪本尚未開放，未來會第一時間通知您喔!💌。", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        if next_mission_id in config.theme_mission_list:
            from bot.handlers.theme_mission_handler import handle_theme_mission_start
            await handle_theme_mission_start(self.client, user_id, next_mission_id)
        elif next_mission_id in config.audio_mission:
            from bot.handlers.audio_mission_handler import handle_audio_mission_start
            await handle_audio_mission_start(self.client, user_id, next_mission_id)
        elif next_mission_id in config.questionnaire_mission:
            from bot.handlers.questionnaire_mission_handler import handle_questionnaire_mission_start
            await handle_questionnaire_mission_start(self.client, user_id, next_mission_id)
        elif next_mission_id in config.baby_profile_registration_missions:
            from bot.handlers.profile_handler import handle_registration_mission_start
            await handle_registration_mission_start(self.client, user_id, next_mission_id)
        elif next_mission_id in config.relation_or_identity_mission:
            from bot.handlers.relation_or_identity_handler import handle_relation_identity_mission_start
            await handle_relation_identity_mission_start(self.client, user_id, next_mission_id)
        elif next_mission_id in config.add_on_photo_mission:
            from bot.handlers.add_on_mission_handler import handle_add_on_mission_start
            await handle_add_on_mission_start(self.client, user_id, next_mission_id)
        else:
            from bot.handlers.photo_mission_handler import handle_photo_mission_start
            await handle_photo_mission_start(self.client, user_id, next_mission_id, send_weekly_report=1)

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
