import discord
from bot.config import config
from bot.utils.message_tracker import delete_photo_view_record

class GrowthPhotoView(discord.ui.View):
    def __init__(self, client, user_id, mission_info, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.mission_id = mission_info['mission_id']
        self.aside_text = mission_info.get('aside_text', None)
        self.content = mission_info.get('content', None)
        self.image_url = mission_info.get('image', None)
        self.baby_data = {}
        if int(self.mission_id) in config.baby_intro_mission:
            self.baby_data.update({
                'baby_name': mission_info.get('baby_name'),
                'gender': mission_info.get('gender'),
                'birthday': mission_info.get('birthday'),
                'height': mission_info.get('height'),
                'weight': mission_info.get('weight'),
                'head_circumference': mission_info.get('head_circumference'),
            })
        
        self.add_aside_text_button = discord.ui.Button(
            custom_id='add_aside_text',
            label="📝 新增/修改文字內容",
            style=discord.ButtonStyle.success
        )
        self.add_aside_text_button.callback = self.add_aside_text_callback
        self.add_item(self.add_aside_text_button)

        self.change_image_button = discord.ui.Button(
            custom_id='change_image',
            label="📷 更換照片",
                style=discord.ButtonStyle.success,
            )
        self.change_image_button.callback = self.change_image_callback
        self.add_item(self.change_image_button)

        self.complete_button = discord.ui.Button(
            custom_id='complete_photo',
            label="完成任務✨: 我覺得OK，不修改了!",
            style=discord.ButtonStyle.secondary
        )
        self.complete_button.callback = self.complete_callback
        self.add_item(self.complete_button)

        self.message = None
    
    async def add_aside_text_callback(self, interaction):
        await self.client.api_utils.store_message(self.user_id, 'user', "📝 新增/修改文字內容")
        await interaction.response.send_message(f"好的～直接輸入你想要的內容就好囉！")

        # Mission continue
        student_mission_info = {
            'user_id': self.user_id,
            'mission_id': self.mission_id,
            'current_step': 3
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

        # Delete the message record
        delete_photo_view_record(self.user_id)

    async def change_image_callback(self, interaction):
        await self.client.api_utils.store_message(self.user_id, 'user', "📷 更換照片")
        await interaction.response.send_message(f"好的～ **點擊對話框左側「+」上傳照片**")

        # Mission continue
        student_mission_info = {
            'user_id': self.user_id,
            'mission_id': self.mission_id,
            'current_step': 3
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

        # Delete the message record
        delete_photo_view_record(self.user_id)

    async def complete_callback(self, interaction):
        await self.client.api_utils.store_message(self.user_id, 'user', "完成任務✨: 我覺得OK，不修改了!")
        photo_url = None
        if self.image_url:
            photo_url = await self.client.s3_client.process_discord_attachment(self.image_url)

        if self.baby_data:
            await self.client.api_utils.update_student_baby_profile(self.user_id, **self.baby_data)
        
        if photo_url or self.aside_text or self.content:
            update_status = await self.client.api_utils.update_mission_image_content(
                self.user_id, self.mission_id, image_url=photo_url, aside_text=self.aside_text, content=self.content
            )
            if bool(update_status):
                await self.client.api_utils.submit_generate_photo_request(self.user_id, self.mission_id)

        msg = "好的～我已經把這張照片收進寶寶的相冊裡囉 ❤️"
        await interaction.response.send_message(msg)
        await self.client.api_utils.store_message(self.user_id, 'assistant', msg)

        student_mission_info = await self.client.api_utils.get_student_mission_status(self.user_id, self.mission_id)
        if student_mission_info.get('mission_completion_percentage', 0) < 1:
            from bot.handlers.utils import send_reward_and_log
            await send_reward_and_log(self.client, self.user_id, self.mission_id, 100)

        # Mission Completed
        student_mission_info = {
            'user_id': self.user_id,
            'mission_id': self.mission_id,
            'current_step': 4,
            'score': 1
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

        # Delete the message record
        delete_photo_view_record(self.user_id)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(content="⚠️ 編輯逾時，可以透過「/回憶寶箱」重新上傳喔！", view=self)
                self.client.logger.info("GrowthALbumView: Invitation expired and message updated successfully.")
            except discord.NotFound:
                self.client.logger.warning("GrowthALbumView: Failed to update expired invitation message as it was already deleted.")

        self.stop()
