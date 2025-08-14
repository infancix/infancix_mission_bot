import discord
import time
from bot.config import config
from bot.utils.message_tracker import delete_task_entry_record

class GrowthPhotoView(discord.ui.View):
    def __init__(self, client, user_id, mission_id, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.mission_id = mission_id

        if self.mission_id in config.add_on_photo_mission:
            for photo_number in range(1, 5):
                self.change_photo_button = discord.ui.Button(
                    custom_id=f'{photo_number}',
                    label=f"換第 {photo_number} 張照片",
                    style=discord.ButtonStyle.secondary
                )
                self.change_photo_button.callback = self.change_photo_callback
                self.add_item(self.change_photo_button)

        self.complete_button = discord.ui.Button(
            custom_id='complete_photo',
            label="送出 (送出即無法修改)",
            style=discord.ButtonStyle.secondary
        )
        self.complete_button.callback = self.complete_callback
        self.add_item(self.complete_button)

        self.message = None

    def generate_embed(self, baby_id, mission_id):
        if mission_id in config.add_on_photo_mission:
            description = "請透過下方按鈕，選擇要更換的照片（1–4）"
        elif mission_id == config.baby_register_mission or mission_id in config.family_intro_mission:
            description = "📷 換照片：直接重新上傳即可"
        elif mission_id in config.photo_mission_with_title_and_content:
            description = "📷 換照片：請選擇要更換的照片\n💬 修改文字：在對話框輸入並送出\n"
        else:
            description = "📷 換照片：請選擇要更換的照片\n💬 修改文字：在對話框輸入並送出(限30字)\n"

        embed = discord.Embed(
            title="製作完成預覽",
            description=description,
            color=0xeeb2da,
        )
        embed.set_image(url=f"https://infancixbaby120.com/discord_image/{baby_id}/{mission_id}.png?t={int(time.time())}")
        if mission_id not in config.add_on_photo_mission:
            embed.set_footer(text="✨ 喜歡這一頁嗎？完成更多任務，就能集滿一本喔！")
        return embed

    async def complete_callback(self, interaction):
        mission_info = await self.client.api_utils.get_mission_info(self.mission_id)
        self.reward = mission_info.get('reward', 20)
        # Mission Completed
        student_mission_info = {
            'user_id': self.user_id,
            'mission_id': self.mission_id,
            'current_step': 4,
            'score': 1
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

        # Send completion message
        if self.reward > 0:
            embed = discord.Embed(
                title="🎉 任務完成！",
                description=f"🎁 你獲得獎勵：🪙 金幣 Coin：+{self.reward}\n",
                color=0xeeb2da,
            )
        else:
            embed = discord.Embed(
                title="🎆 任務完成",
                description=f"已匯入繪本，可點選 `指令` > `瀏覽繪本進度` 查看整本",
                color=0xeeb2da,
            )
        await interaction.response.send_message(embed=embed)
        await self.client.api_utils.add_gold(self.user_id, gold=self.reward)

        # Send log to Background channel
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"MISSION_{self.mission_id}_FINISHED <@{self.user_id}>"
        await channel.send(msg_task)

        # Check mission status
        mission_info = await self.client.api_utils.get_mission_info(self.mission_id)
        book_id = mission_info.get('book_id', 0)
        self.client.logger.info(f"GrowthPhotoView: Book ID for mission {self.mission_id} is {book_id}")
        if book_id is not None and book_id != 0:
            # If this is the very first mission of the book, generate the album immediately
            if int(self.mission_id) in config.first_mission_per_book:
                await self.client.api_utils.submit_generate_album_request(self.user_id, book_id)
            else:
                incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(self.user_id, book_id)
                if len(incomplete_missions) == 0:
                    # All photo missions are complete; generate the album
                    await self.client.api_utils.submit_generate_album_request(self.user_id, book_id)

        # Delete the message record
        delete_task_entry_record(str(interaction.user.id), str(self.mission_id))

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
        student_mission_info = await client.api_utils.get_student_is_in_mission(str(interaction.user.id))
        thread_id = student_mission_info['thread_id']
        mission_instructions = f"使用者希望更換第 {photo_number} 張照片"
        self.client.openai_utils.add_task_instruction(thread_id, mission_instructions)

        embed = discord.Embed(
            title="🔼 請上傳新照片",
            description="📎 點左下 [+] 上傳照片",
            color=0xeeb2da,
        )
        await interaction.followup.send(embed=embed)

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
