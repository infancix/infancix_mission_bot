import discord
import time
from collections import defaultdict
from bot.config import config
from bot.views.task_select_view import TaskSelectView
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
        self.design_id = mission_result.get('design_id')
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
        if self.mission_id in config.questionnaire_mission:
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

        # Send completion message
        description = ""
        if self.reward > 0:
            description = f"🎁 你獲得獎勵：🪙 金幣 Coin：+{self.reward}！\n"
            await self.client.api_utils.add_gold(self.user_id, gold=self.reward)

        try:
            if self.design_id or (self.baby_id is not None and self.baby_id != 0 and self.book_id and self.book_id != 0):
                self.design_id = encode_ids(self.baby_id, self.book_id)
                description += f"- 🔗 [繪本預覽](https://infancixbaby120.com/babiary/{self.design_id})\n"
        except Exception as e:
            self.client.logger.error(f"Error encoding IDs: {e}")
            pass

        description += f"- 💡小提示：在繪本送印確認前，您隨時可以透過 `指令` > `查看里程碑` 重新上傳照片喔\n"
        embed = discord.Embed(
            title="🎉 任務完成！",
            description=description,
            color=0xeeb2da,
        )

        if len(incomplete_missions) > 0:
            embed.add_field(name="📖 繪本進度", value=f"目前繪本尚有 {len(incomplete_missions)} 頁未完成，點擊下方按鈕繼續製作喔", inline=False)

        # Go next mission if available
        if self.book_id is not None and self.book_id != 0:
            self.client.logger.info(f"GrowthPhotoView: Book ID for mission {self.mission_id} is {self.book_id}")
            print("len(incomplete_missions):", len(incomplete_missions))
            if len(incomplete_missions) > 0:
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
                await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed)

        # Send log to Background channel
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"MISSION_{self.mission_id}_FINISHED <@{self.user_id}>"
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
                await self.message.edit(content="⚠️ 編輯逾時，可以透過右下方[指令]，重新上傳喔！", view=self)
                self.client.logger.info("GrowthALbumView: Invitation expired and message updated successfully.")
            except discord.NotFound:
                self.client.logger.warning("GrowthALbumView: Failed to update expired invitation message as it was already deleted.")

        self.stop()
