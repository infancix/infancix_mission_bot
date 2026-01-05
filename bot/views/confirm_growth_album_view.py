import discord
import time
import calendar
from datetime import datetime

from bot.config import config
from bot.views.photo_mission import PhotoTaskSelect
from bot.views.album_select_view import AlbumButton

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

class ConfirmGrowthAlbumView(discord.ui.View):
    def __init__(self, client, user_id, albums_info, incomplete_missions, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.incomplete_missions = incomplete_missions

        self.user_id = user_id
        self.albums_info = albums_info
        self.page_size = 4
        self.message = None
        self.call_incompleted_missions = True
        self.build_select_book_menu()

    def build_select_book_menu(self, page: int = 0):
        current_row = 0
        for i, book in enumerate(self.albums_info):
            button = AlbumButton(
                self.client,
                self.user_id,
                menu_options=None,
                book_info=book
            )
            button.row = i // 2  # 0-2 排
            current_row = button.row
            self.add_item(button)

    def preview_embed(self):
        current_day = datetime.now().day
        current_month, current_year, next_month, next_year = calculate_next_month()
        next_month_str = f"{next_month}" if current_month < 12 else f"{next_year}/1"
        if current_day == 5:
            title = f"📦 {current_month}月送印提醒 (今天截止)"
        elif current_day == 4:
            title = f"📦 {current_month}月送印提醒（明天截止）"
        else:
            title = f"📦 每月送印提醒"
        embed = discord.Embed(
            title=title,
            description=(
                f"請於 🗓️ {current_month}/{self.client.submit_deadline} ({calculate_weekday(current_year, current_month, self.client.submit_deadline)}) 前完成送印\n\n"
                f"📚 您的繪本進度\n"
            ),
            color=0x3498db
        )

        if not self.albums_info:
            embed.description += "目前沒有待送印的繪本喔\n"
        else:
            for e, album in enumerate(self.albums_info):
                #print(album)
                embed.description += f"{number_emojis[e]} {album['book_type']} | {album['book_title']} {album['completed_mission_count']} / {album['total_mission_count']}\n"
            embed.description += "----------------------------\n\n"

        embed.description += (
            f"🚚 **運送機制**\n"
            f"每月 5 號統一印製，送印後約 30 個工作天即可收到繪本！\n\n"
            f"💰 **運費規則**\n"
            f"• 體驗組會員：一本即可直接送印\n"
            f"• 一年 / 三年份會員：滿 4 本免運，未滿收 NT$120 (港澳 HKD$50)\n"
            f"• ✨ **限時優惠中：不限本數，全台免運！** (至 2025/12/31 止)\n\n"
    
            f"⚠️ **重要提醒**\n"
            f"若未在期限內確認，將順延至 *{next_month_str}/1* 才能送印！\n\n"
            f"----------------------------\n\n"
        )

        if self.call_incompleted_missions:
            embed.description += f"👇下一步\n請點選下方按鈕，前往完成繪本內尚未完成的照片任務喔！"
        else:
            embed.description += f"👇下一步\n請點選下方按鈕，查看繪本進度喔！"

        embed.set_footer(
            text="若有任何問題，隨時聯絡社群客服「阿福」。",
        )

        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                print("✅ 1周後後按鈕已自動 disable")
            except discord.NotFound:
                print("❌ 訊息已刪除，無法更新")

        delete_task_entry_record(str(self.message.author.id), str(self.mission_id))
        self.stop()
