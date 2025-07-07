import discord
from bot.config import config
from bot.utils.message_tracker import delete_photo_view_record

class GrowthPhotoView(discord.ui.View):
    def __init__(self, client, user_id, mission_id, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.mission_id = mission_id

        self.complete_button = discord.ui.Button(
            custom_id='complete_photo',
            label="送出 (送出即無法修改)",
            style=discord.ButtonStyle.secondary
        )
        self.complete_button.callback = self.complete_callback
        self.add_item(self.complete_button)

        self.message = None

    def generate_embed(self, baby_id, mission_id):
        embed = discord.Embed(
            title="製作完成預覽",
            description="📷 換照片：直接重新上傳即可\n💬 修改文字：在對話框輸入並送出(限30字)"
        )

        if self.image_url:
            embed.set_image(url=f"https://infancixbaby120.com/discord_image/{baby_id}/{mission_id}.png")

        embed.set_footer(
            text="✨ 喜歡這一頁嗎？完成更多任務，就能集滿一本喔！"
        )

        return embed

    async def complete_callback(self, interaction):
        # Mission Completed
        student_mission_info = {
            'user_id': self.user_id,
            'mission_id': self.mission_id,
            'current_step': 4,
            'score': 1
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

        # Send completion message
        embed = discord.Embed(
            title="🎉 任務完成！",
            description=f"🎁 你獲得獎勵：🪙 金幣 Coin：+100\n",
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed)
        await self.client.api_utils.add_gold(self.user_id, gold=100)

        # Send log to Background channel
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"MISSION_{mission_id}_FINISHED <@{self.user_id}>"
        await channel.send(msg_task)

        # Check mission status
        mission_info = await self.client.api_utils.get_mission_info(self.mission_id)
        book_id = mission_info.get('book_id', 0)
        if book_id is not None and book_id != 0:
            incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(self.user_id, book_id)
            if len(incomplete_missions) == 0:
                await self.client.api_utils.submit_generate_album_request(user_id, book_id)

        # Delete the message record
        delete_photo_view_record(self.user_id)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(content="⚠️ 編輯逾時，可以透過「/補上傳照片」重新上傳喔！", view=self)
                self.client.logger.info("GrowthALbumView: Invitation expired and message updated successfully.")
            except discord.NotFound:
                self.client.logger.warning("GrowthALbumView: Failed to update expired invitation message as it was already deleted.")

        self.stop()
