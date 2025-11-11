import discord
import time
import discord
import time
import calendar
from datetime import datetime

from collections import defaultdict
from bot.config import config
from bot.views.task_select_view import TaskSelectView
from bot.views.album_select_view import AlbumView
from bot.utils.message_tracker import (
    save_task_entry_record,
)
from bot.utils.id_utils import encode_ids

class GrowthPhotoView(discord.ui.View):
    def __init__(self, client, user_id, mission_id, mission_result={}, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.mission_id = mission_id
        self.baby_id = mission_result.get('baby_id', 0)
        self.book_id = mission_result.get('book_id', 0)
        self.reward = mission_result.get('reward', 20)
        self.purchase_status = mission_result.get('purchase_status', '未購買')
        self.need_generated_full_album = mission_result.get('design_id', None) is None
        self.design_id = mission_result.get('design_id') if mission_result.get('design_id') else encode_ids(self.baby_id, self.book_id)
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

        if self.mission_id in config.book_intro_mission:
            self.next_mission_button = discord.ui.Button(
                custom_id='next_mission',
                label="開始製作內頁",
                style=discord.ButtonStyle.success
            )
            self.next_mission_button.callback = self.next_mission_button_callback
            self.add_item(self.next_mission_button)
        else:
            self.complete_button = discord.ui.Button(
                custom_id='complete_photo',
                label="送出 (送出即無法修改)",
                style=discord.ButtonStyle.success
            )
            self.complete_button.callback = self.complete_callback
            self.add_item(self.complete_button)

        self.message = None

    def generate_embed(self, baby_id, mission_id):
        if self.mission_id in config.book_intro_mission:
            description = "恭喜你成功為寶寶製作專屬繪本封面 🎉\n\n點選下方按鈕，開始製作內頁吧！"
        elif self.mission_id in config.questionnaire_mission:
            description = "請點選 重新選擇 或是 直接送出"
        elif mission_id in config.add_on_photo_mission:
            description = "請透過下方按鈕，選擇要更換的照片（1–4）"
        elif mission_id in config.audio_mission:
            description = "🔊 重新錄製：點左下 [+] 重新錄音; 或是重新上傳錄音檔即可"
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

        previous_status = await self.client.api_utils.get_student_mission_status(str(interaction.user.id), self.mission_id)
        if previous_status.get('mission_completion_percentage') >= 1:
            self.reward = 0

        # Mission Completed
        student_mission_info = {
            'user_id': self.user_id,
            'mission_id': self.mission_id,
            'current_step': 4,
            'total_steps': 4,
            'score': 1
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

        # reset user state
        from bot.handlers.utils import reset_user_state
        reset_user_state(self.client, str(interaction.user.id), self.mission_id)

        # Check for incomplete missions
        incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(self.user_id, self.book_id)

        embed = discord.Embed(
            title="🎉 任務完成！",
            description="",
            color=0xeeb2da,
        )

        # Send completion message
        if self.reward > 0:
            embed.description += f"🎁 你獲得獎勵：🪙 金幣 Coin：+{self.reward}！\n\n"
            await self.client.api_utils.add_gold(self.user_id, gold=self.reward)

        if len(incomplete_missions) > 0:
            embed.description += f"🔗 [繪本預覽](https://infancixbaby120.com/babiary/{self.design_id})\n\n"
            embed.description += f"📖 繪本進度\n目前繪本尚有 {len(incomplete_missions)} 頁未完成，點擊下方按鈕繼續製作喔\n\n"
            next_mission_id = incomplete_missions[0]['mission_id'] if incomplete_missions else None
            payload = {
                'user_id': self.user_id,
                'book_id': self.book_id,
                'mission_id': self.mission_id,
                'next_mission_id': next_mission_id,
            }
            view = TaskSelectView(self.client, "go_next_mission", self.mission_id, mission_result=payload)
            view.message = await interaction.followup.send(embed=embed, view=view)
            save_task_entry_record(self.user_id, str(view.message.id), "go_next_mission", self.mission_id, payload)
        else:
            if self.purchase_status != "已購買":
                task_type = ["go_purchase"]
                payload = {
                    'user_id': self.user_id,
                    'book_id': self.book_id,
                    'mission_id': self.mission_id,
                }

                embed.description += (
                    f"🔗 [繪本預覽](https://infancixbaby120.com/babiary/{self.design_id})\n\n"
                    f"💛 您的體驗任務完成囉！\n"
                    f"想收藏這本屬於你與寶寶的故事嗎？\n\n"
                    f"🛍️ 購買繪本：\n"
                    f"點擊下方按鈕社群管家阿福將私訊您，協助您下單。\n"
                )
                target_book_id = None
                for book_id in config.available_books:
                    incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(self.user_id, book_id)
                    if len(incomplete_missions) > 0:
                        target_book_id = book_id
                        break

                if target_book_id is not None:
                    next_book_info = await self.client.api_utils.get_mission_info(config.book_first_mission_map[target_book_id])
                    embed.description += (
                        f"或是點擊按鈕體驗更多繪本吧！"
                    )
                    task_type.append("go_next_mission")
                    payload['next_mission_id'] = config.book_first_mission_map[target_book_id]
                    payload['next_book_title'] = f"{next_book_info['volume_title']} | {next_book_info['photo_mission']}"

                task_type_str = "_".join(task_type)
                view = TaskSelectView(self.client, task_type_str, self.mission_id, mission_result=payload)
                view.message = await interaction.followup.send(embed=embed, view=view)
                save_task_entry_record(self.user_id, str(view.message.id), task_type_str, self.mission_id, payload)

            else:
                # purchased user
                if self.need_generated_full_album:
                    # submit generate full album request
                    await self.client.api_utils.submit_generate_album_request(self.user_id, self.book_id)
                    self.client.logger.info(f"送出完整繪本產生任務 for user {self.user_id}, book {self.book_id}")
                    embed.description += (
                        f"⏳系統正在為您製作完整繪本，請耐心等待。完成後會在此通知您！\n\n"
                    )
                    embed.set_image(url=f"https://infancixbaby120.com/discord_assets/loading1.gif")
                    await interaction.followup.send(embed=embed)
                else:
                    deadline_str, defer_str = self.get_deadline_and_defer_timestamp()
                    embed.description += (
                        f"你已經完成所有任務囉！\n\n"
                        f"🔍 最後檢查:\n"
                        f"請點擊下方連結確認整本內容：\n"
                        f"📎[繪本預覽](https://infancixbaby120.com/babiary/{self.design_id})\n"
                        f"確認完成後，請點下方按鈕送印。\n\n"
                        f"🚚 運送機制\n"
                        f"每月 5 號統一印製，送印後約 30 個工作天 即可收到繪本囉！\n\n"
                        f"📌 **重要提醒**\n"
                        f"修改截止日為 **{deadline_str} 23:59**\n"
                        f"若未在期限內確認，將順延至 **{defer_str}** 才能送印！\n\n"
                        f"🖼️ **如需修改照片**，請依下列步驟操作：\n"
                        f"1️⃣ 於對話框輸入 */查看育兒里程碑* ，重啟任務\n"
                        f"2️⃣ 確認完畢後，於對話框輸入 */我的書櫃* > 點選 `確認送印`"
                    )
                    task_type_str = "confirm_print"
                    payload = {
                        'user_id': self.user_id,
                        'book_id': self.book_id,
                        'mission_id': self.mission_id,
                        'design_id': self.design_id
                    }
                    view = TaskSelectView(self.client, task_type_str, self.mission_id, mission_result=payload)
                    view.message = await interaction.followup.send(embed=embed, view=view)
                    save_task_entry_record(self.user_id, str(view.message.id), task_type_str, self.mission_id, payload)

        # Send log to Background channel
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"MISSION_{self.mission_id}_FINISHED <@{self.user_id}>"
        await channel.send(msg_task)

    async def next_mission_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
        await interaction.followup.send("⏳開啟任務會需一點時間，點選後請耐心等待，不必重複點喔！", ephemeral=True)

        # Mission Completed
        student_mission_info = {
            'user_id': self.user_id,
            'mission_id': self.mission_id,
            'current_step': 4,
            'total_steps': 4,
            'score': 1
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

        # reset user state
        from bot.handlers.utils import reset_user_state
        reset_user_state(self.client, str(interaction.user.id), self.mission_id)

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"MISSION_{self.mission_id}_FINISHED <@{self.user_id}>"
        await channel.send(msg_task)

        next_mission_id = config.book_first_mission_map.get(self.book_id)
        msg_task = f"START_MISSION_{next_mission_id} <@{self.user_id}>"
        await channel.send(msg_task)

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

        update_status = await self.client.api_utils.update_mission_image_content(str(interaction.user.id), self.mission_id, aside_text="REMOVE_ASIDE_TEXT")
        self.client.skip_aside_text[str(interaction.user.id)] = True
        if bool(update_status):
            await self.client.api_utils.submit_generate_photo_request(str(interaction.user.id), self.mission_id)
            self.client.logger.info(f"送出繪本任務 {self.mission_id}")

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(content="⚠️ 編輯逾時，可以在對話框輸入 [*/補上傳照片*]，重新製作喔！", view=self)
                self.client.logger.info("GrowthALbumView: Invitation expired and message updated successfully.")
            except discord.NotFound:
                self.client.logger.warning("GrowthALbumView: Failed to update expired invitation message as it was already deleted.")

        self.stop()

    def get_deadline_and_defer_timestamp(self):
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
        return deadline_str, defer_str
