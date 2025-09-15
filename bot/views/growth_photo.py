import discord
import time
from bot.config import config
from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    delete_growth_photo_record,
    delete_conversations_record,
    delete_questionnaire_record
)
class GrowthPhotoView(discord.ui.View):
    def __init__(self, client, user_id, mission_id, mission_result={}, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.mission_id = mission_id
        self.book_id = mission_result.get('book_id', 0)
        self.reward = mission_result.get('reward', 20)
        self.purchase_status = mission_result.get('purchase_status', '未購買')
        self.design_id = mission_result.get('design_id', None)
        self.mission_result = mission_result

        if self.mission_id in config.add_on_photo_mission:
            for photo_number in range(1, 5):
                self.change_photo_button = discord.ui.Button(
                    custom_id=f'{photo_number}',
                    label=f"換第 {photo_number} 張照片",
                    style=discord.ButtonStyle.secondary
                )
                self.change_photo_button.callback = self.change_photo_callback
                self.add_item(self.change_photo_button)

        if self.mission_id in config.photo_mission_with_aside_text and self.mission_result.get('aside_text', None):
            self.remove_aside_text_button = discord.ui.Button(
                custom_id='remove_aside_text',
                label="刪除回憶文字",
                style=discord.ButtonStyle.secondary
            )
            self.remove_aside_text_button.callback = self.remove_aside_text_callback
            self.add_item(self.remove_aside_text_button)

        if self.mission_id in config.questionnaire_mission:
            self.reselect_button = discord.ui.Button(
                custom_id='reselect_button',
                label="重新選擇",
                style=discord.ButtonStyle.secondary
            )
            self.reselect_button.callback = self.reselect_button_callback
            self.add_item(self.reselect_button)

        self.complete_button = discord.ui.Button(
            custom_id='complete_photo',
            label="送出 (送出即無法修改)",
            style=discord.ButtonStyle.success
        )
        self.complete_button.callback = self.complete_callback
        self.add_item(self.complete_button)

        self.message = None

    def generate_embed(self, baby_id, mission_id):
        if mission_id in config.add_on_photo_mission:
            description = "請透過下方按鈕，選擇要更換的照片（1–4）"
        elif mission_id in config.photo_mission_with_aside_text:
            if self.mission_result.get('aside_text', None):
                description = "📷 換照片：請選擇要更換的照片\n💬 修改文字：在對話框輸入並送出(限30字)\n ❌刪除文字: 點選刪除按鈕即可"
            else:
                description = "📷 換照片：請選擇要更換的照片\n💬 新增照片回憶(限30字)\n"
        elif mission_id in config.photo_mission_with_title_and_content:
            description = "📷 換照片：請選擇要更換的照片\n💬 修改文字：在對話框輸入並送出\n"
        else:
            description = "📷 換照片：直接重新上傳即可"

        embed = discord.Embed(
            title="🤍 製作完成預覽",
            description=description,
            color=0xeeb2da,
        )
        embed.set_image(url=f"https://infancixbaby120.com/discord_image/{baby_id}/{mission_id}.jpg?t={int(time.time())}")
        if mission_id not in config.add_on_photo_mission:
            embed.set_footer(text="✨ 喜歡這一頁嗎？完成更多任務，就能集滿一本喔！")
        return embed

    async def complete_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        # Mission Completed
        student_mission_info = {
            'user_id': self.user_id,
            'mission_id': self.mission_id,
            'current_step': 4,
            'score': 1
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

        # Check for incomplete missions
        incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(self.user_id, self.book_id)

        # Send completion message
        if self.reward > 0:
            embed = discord.Embed(
                title="🎉 任務完成！",
                description=f"🎁 你獲得獎勵：🪙 金幣 Coin：+{self.reward}\n\n想更快完成屬於寶寶的一整本繪本嗎？點下方按鈕，馬上解鎖秘訣 🚀",
                color=0xeeb2da,
            )
        else:
            embed = discord.Embed(
                title="🎆 任務完成",
                description=f"📚 已匯入繪本，可點選 `指令` > `瀏覽繪本進度` 查看整本\n\n",
                color=0xeeb2da,
            )
            if len(incomplete_missions) == 0:
                embed.description += (
                "📦 Baby120 寄件說明\n"
                "將會於 10/1號 抽出 3 名幸運兒，送出精美繪本！"
                #"書籍每 90 天統一寄送一次，未完成的任務將自動順延。\n"
                #"收檔後 15 個工作天內出貨。\n"
                #"所有寄送進度、任務狀態請以官網「會員中心 → 我的書櫃」公告為主。"
            )

        view = TaskSelectView(self.client, "show_command_instruction", self.mission_id)
        await interaction.followup.send(embed=embed, view=view)
        await self.client.api_utils.add_gold(self.user_id, gold=self.reward)

        # Send log to Background channel
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"MISSION_{self.mission_id}_FINISHED <@{self.user_id}>"
        await channel.send(msg_task)

        # Check mission status
        if self.book_id is not None and self.book_id != 0:
            self.client.logger.info(f"GrowthPhotoView: Book ID for mission {self.mission_id} is {self.book_id}")
            if len(incomplete_missions) == 0:
                await self.client.api_utils.submit_generate_album_request(self.user_id, self.book_id)
            elif not self.design_id and (self.book_id == 1 or self.purchase_status == '已購買'):
                await self.client.api_utils.submit_generate_album_request(self.user_id, self.book_id)

        # Delete the message record
        delete_questionnaire_record(str(interaction.user.id), str(self.mission_id))
        delete_growth_photo_record(str(interaction.user.id), str(self.mission_id))
        delete_conversations_record(str(interaction.user.id), str(self.mission_id))

    async def change_photo_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        custom_id = int(interaction.data.get("custom_id")) if interaction.data else None
        if custom_id is None:
            await interaction.response.send_message("按鈕識別失敗，請再試一次。", ephemeral=True)
            return

        photo_number = custom_id
        self.client.photo_mission_replace_index[str(interaction.user.id)] = photo_number

        embed = discord.Embed(
            title="🔼 請上傳新照片",
            description="📎 點左下 [+] 上傳照片",
            color=0xeeb2da,
        )
        await interaction.followup.send(embed=embed)

    async def reselect_button_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("正在重新載入選項...", ephemeral=True)
        try:
            from bot.handlers.questionnaire_mission_handler import handle_questionnaire_round
            message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
            student_mission_info = {
                'user_id': str(interaction.user.id),
                'mission_id': self.mission_id,
                'current_step': 2
            }
            self.client.api_utils.update_student_mission_status(**student_mission_info)
            await handle_questionnaire_round(self.client, message, student_mission_info, current_round=0, restart=True)
        except Exception as e:
            await interaction.response.send_message("❌ 發生錯誤，請稍後再試。", ephemeral=True)

    async def remove_aside_text_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        update_status = await self.client.api_utils.update_mission_image_content(str(interaction.user.id), self.mission_id, aside_text="[REMOVE_ASIDE_TEXT]")
        if bool(update_status):
            await self.client.api_utils.submit_generate_photo_request(str(interaction.user.id), self.mission_id)
            self.client.logger.info(f"送出繪本任務 {self.mission_id}")

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(content="⚠️ 編輯逾時，可以透過右下方[指令]，重新上傳喔！", view=self)
                self.client.logger.info("GrowthALbumView: Invitation expired and message updated successfully.")
            except discord.NotFound:
                self.client.logger.warning("GrowthALbumView: Failed to update expired invitation message as it was already deleted.")

        self.stop()
