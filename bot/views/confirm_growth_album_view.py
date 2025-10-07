import discord
import time
import calendar
from datetime import datetime

from bot.config import config
from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    delete_confirm_growth_album_record
)
class ConfirmGrowthAlbumView(discord.ui.View):
    def __init__(self, client, user_id, album_result={}, timeout=None):
        if timeout is None:
            timeout = self._calculate_deadline_timeout()
        super().__init__(timeout=timeout)

        self.client = client
        self.user_id = user_id
        self.baby_id = album_result.get('baby_id', 0)
        self.book_id = album_result.get('book_id', 0)
        self.purchase_status = album_result.get('purchase_status', '未購買')
        self.design_id = album_result.get('design_id', None)
        self.album_result = album_result
        self.message = None

        self.confirm_button = discord.ui.Button(
            custom_id='confirm_album',
            label="確認送出 (送出即無法修改)",
            style=discord.ButtonStyle.success
        )
        self.confirm_button.callback = self.confirm_callback
        self.add_item(self.confirm_button)

        self.edit_button = discord.ui.Button(
            custom_id='edit_album',
            label="返回修改",
            style=discord.ButtonStyle.secondary
        )
        self.edit_button.callback = self.edit_callback
        self.add_item(self.edit_button)

    async def confirm_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        confirm_embed = discord.Embed(
            title="🎆 成長繪本已確認",
            description="感謝您的確認！您的繪本已送出製作\n\n📦印刷期 + 運送期約 **30 個工作天**，完成後將寄送至您的指定地址",
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=confirm_embed, ephemeral=True)

        await self.client.api_utils.update_student_confirmed_growth_album(self.user_id, self.book_id)
        delete_confirm_growth_album_record(self.user_id, self.book_id)
        self.stop()

    async def edit_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        embed = discord.Embed(
            title="修改繪本教學",
            description=(
                "1️⃣ 參考下方圖片教學重新製作繪本\n"
                "2️⃣ 修改完成後，點選「`指令` > `繪本送印`」\n"
                "3️⃣ 檢視整本繪本並再次確認送印"
            ),
            color=0xeeb2da,
            timestamp=datetime.utcnow()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        delete_confirm_growth_album_record(self.user_id, self.book_id)
        self.stop()

    def preview_embed(self):
        current_month, next_month, next_year = self._calculate_next_month()
        next_month_str = f"{next_month}" if current_month < 12 else f"{next_year}/1"

        preview_link = f"https://infancixbaby120.com/babiary/{self.design_id}"
        embed = discord.Embed(
            title="📚 成長繪本最終確認",
            description=(
                f"請仔細檢查您的成長繪本內容\n"
                f"[👉 點擊這裡預覽整本繪本]({preview_link})\n\n"
                f"⏰ **重要提醒：修改截止日為 {current_month}/{self.client.submit_deadline} 23:59 UTC**\n"
                f"若未在期限內確認，將順延至 *{next_month_str}/1* 才能製作！"
            ),
            color=0xeeb2da,
            timestamp=datetime.utcnow()
        )
        return embed

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
                    "若有任何問題，歡迎隨時聯絡社群客服「阿福 <@1272828469469904937>」。"
                ),
                color=0xeeb2da,
            )
            try:
                await user.send(embed=timeout_embed)
            except discord.Forbidden:
                print(f"無法傳送訊息給用戶 {self.user_id}，可能已封鎖機器人。")

        delete_confirm_growth_album_record(self.user_id, self.book_id)

    @staticmethod
    def _calculate_deadline_timeout():
        """計算到本月 5 號 23:59:59 的剩餘秒數"""
        now = datetime.now()
        current_year = now.year
        current_month = now.month
        deadline = datetime(current_year, current_month, self.client.submit_deadline, 23, 59, 59)
        remaining_seconds = (deadline - now).total_seconds()
        return max(remaining_seconds, 0)

    @staticmethod
    def _calculate_next_month():
        """計算下個月的月份和年份"""
        now = datetime.now()
        next_month = now.month + 1 if now.month < 12 else 1
        next_year = now.year if now.month < 12 else now.year + 1
        return now.month, next_month, next_year
