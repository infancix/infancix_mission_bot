import discord
import random
import time
from datetime import datetime
from types import SimpleNamespace

from bot.config import config
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.utils.message_tracker import delete_task_entry_record

class TaskSelectView(discord.ui.View):
    def __init__(self, client, task_type, mission_id, mission_result=None, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.message = None
        self.result = mission_result or {}

        if task_type == "go_quiz":
            label = "挑戰任務 GO!"
            self.go_quiz_button = discord.ui.Button(
                custom_id="go_quiz_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_quiz_button.callback = self.go_quiz_button_callback
            self.add_item(self.go_quiz_button)
        
        if task_type == "go_skip":
            label = "跳過"
            self.go_skip_button = discord.ui.Button(
                custom_id="go_skip_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_skip_button.callback = self.go_skip_button_callback
            self.add_item(self.go_skip_button)

        if task_type == "go_submit":
            label = "送出"
            self.go_submit_button = discord.ui.Button(
                custom_id="go_submit_button",
                label=label,
                style=discord.ButtonStyle.success
            )
            self.go_submit_button.callback = self.go_submit_button_callback
            self.add_item(self.go_submit_button)
        
        if task_type == "baby_born":
            label = "寶寶還在肚子裡，不想退房"
            self.baby_not_born_button = discord.ui.Button(
                custom_id="baby_not_born_button",
                label=label,
                style=discord.ButtonStyle.danger
            )
            self.baby_not_born_button.callback = self.baby_not_born_button_callback
            self.add_item(self.baby_not_born_button)

            label = "我家寶寶出生了"
            self.baby_born_button = discord.ui.Button(
                custom_id="baby_born_button",
                label=label,
                style=discord.ButtonStyle.success
            )
            self.baby_born_button.callback = self.baby_born_button_callback
            self.add_item(self.baby_born_button)
        
        if task_type == "baby_optin":
            label = "送出"
            self.baby_optin_button = discord.ui.Button(
                custom_id="baby_optin_button",
                label=label,
                style=discord.ButtonStyle.success
            )
            self.baby_optin_button.callback = self.baby_optin_button_callback
            self.add_item(self.baby_optin_button)

        if task_type == "check_add_on":
            label = "我要加購"
            self.check_add_on_button = discord.ui.Button(
                custom_id="check_add_on_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.check_add_on_button.callback = self.check_add_on_button_callback
            self.add_item(self.check_add_on_button)

    async def go_quiz_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        student_mission_info = await self.client.api_utils.get_student_mission_status(str(interaction.user.id), self.mission_id)
        student_mission_info['user_id'] = str(interaction.user.id)
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        await interaction.channel.send(f"🔥 挑戰開始！讓我來看看你對「{student_mission_info['mission_title']}」的知識掌握得怎麼樣呢 🐾✨")
        
        from bot.handlers.quiz_mission_handler import handle_quiz_round
        await handle_quiz_round(self.client, message, student_mission_info)
    
    async def go_skip_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        await self.submit_image_data(interaction)

    async def go_submit_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        await self.submit_image_data(interaction)

    async def baby_optin_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        success = await self.submit_baby_data(interaction)
        if success:
            student_mission_info = await self.client.api_utils.get_student_mission_status(str(interaction.user.id), self.mission_id)
            student_mission_info['user_id'] = str(interaction.user.id)
            student_mission_info['current_step'] = 2
            await self.client.api_utils.update_student_mission_status(**student_mission_info)
            message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        
            from bot.handlers.photo_mission_handler import handle_photo_upload_instruction
            await handle_photo_upload_instruction(self.client, message, student_mission_info)

    async def baby_not_born_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
        await interaction.channel.send(f"等寶寶出生後再來製作繪本吧！")

    async def submit_baby_data(self, interaction):
        await self.client.api_utils.update_student_profile(
            str(interaction.user.id),
            str(interaction.user.name),
            '寶寶已出生'
        )
        await self.client.api_utils.update_student_registration_done(str(interaction.user.id))

        # update baby profile
        payload = {
            'baby_name': self.result.get('baby_name'),
            'baby_name_en': self.result.get('baby_name_en'),
            'gender': self.result.get('gender'),
            'birthday': self.result.get('birthday'),
            'height': self.result.get('height'),
            'weight': self.result.get('weight'),
            'head_circumference': self.result.get('head_circumference'),
        }
        response = await self.client.api_utils.update_student_baby_profile(str(interaction.user.id), **payload)
        if not response:
            await interaction.followup.send("更新寶寶資料失敗，請稍後再試。")
            return
        return True

    async def submit_image_data(self, interaction):
        if self.result and self.result.get('attachment'):
            attachment_obj = [self.result.get('attachment')]
            update_status = await self.client.api_utils.update_mission_image_content(
                str(interaction.user.id), self.mission_id, attachment_obj, aside_text=self.result.get('aside_text'), content=self.result.get('content')
            )

            if bool(update_status):
                await self.client.api_utils.submit_generate_photo_request(str(interaction.user.id), self.mission_id)
                self.client.logger.info(f"送出繪本任務 {self.mission_id}")

    async def baby_born_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        await interaction.channel.send(f"🎉 恭喜你！寶寶已經出生了！可以製作您和寶寶的專屬繪本囉!")
        await self.client.api_utils.update_student_profile(
            str(interaction.user.id),
            str(interaction.user.name),
            '寶寶已出生'
        )

        # Call next mission
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"START_MISSION_1001 <@{str(interaction.user.id)}>"
        await channel.send(msg_task)

        # Delete task entry record
        delete_task_entry_record(str(interaction.user.id), str(self.mission_id))

    async def check_add_on_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        # Handle the add-on purchase logic here
        student_profile = await self.client.api_utils.get_student_profile(str(interaction.user.id))
        if not student_profile or student_profile.get('gold', 0) < 200:
            embed = self.get_insufficient_coin_embed()
            await interaction.followup.send(embed=embed)
            return
        else:
            embed = self.get_add_on_photo_embed()
            await interaction.followup.send(embed=embed)

    def get_insufficient_coin_embed(self):
        embed = discord.Embed(
            title="👛 餘額不足",
            color=0xeeb2da,
        )
        embed.add_field(name="🫰 如何獲得金幣", value="解任務、參與活動", inline=False)
        embed.add_field(name="🔍︎ 查看金幣餘額", value="請至 <@1272828469469904937> 點選指令", inline=False)
        embed.add_field(name="🥺 如何回來賺買", value="點選 `指令` > `補上傳照片` > `加購繪本單頁`", inline=False)
        return embed

    def get_add_on_photo_embed(self):
        embed = discord.Embed(
            title="💸 加購成功",
            description="**製作加購頁**\n請上傳四張照片",
            color=0xeeb2da,
        )
        embed.set_footer(text="可以一次上傳多張喔!")
        instruction_url = self.result.get('mission_instruction_image_url', '').split(',')[-1]
        if instruction_url:
            instruction_url = create_preview_image_from_url(instruction_url)
        else:
            instruction_url = "https://infancixbaby120.com/discord_assets/book1_add_on_photo_mission.png"
        embed.set_image(url=instruction_url)
        return embed

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                print("✅ 24 小時後按鈕已自動 disable")
            except discord.NotFound:
                print("❌ 訊息已刪除，無法更新")

        self.stop()
