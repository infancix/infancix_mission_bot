import discord
import random
import time
from datetime import datetime
from types import SimpleNamespace

from bot.config import config
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.utils.message_tracker import save_task_entry_record, delete_task_entry_record, get_mission_record, save_mission_record

class TaskSelectView(discord.ui.View):
    def __init__(self, client, task_type, mission_id, mission_result=None, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.book_id = mission_result.get('book_id') if mission_result else 0
        self.message = None
        self.result = mission_result or {}

        if task_type == "go_book_instruction":
            label = "開始製作繪本"
            self.go_book_instruction_button = discord.ui.Button(
                custom_id="go_book_instruction_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_book_instruction_button.callback = self.go_book_instruction_button_callback
            self.add_item(self.go_book_instruction_button)

        if task_type == "go_next_mission":
            if self.result.get('is_first_mission'):
                label = "開始製作封面"
            else:
                label = "繼續製作下一頁"
            self.go_next_mission_button = discord.ui.Button(
                custom_id="go_next_mission_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_next_mission_button.callback = self.go_next_mission_button_callback
            self.add_item(self.go_next_mission_button)

        if task_type == "go_quiz":
            label = "挑戰任務 GO!"
            self.go_quiz_button = discord.ui.Button(
                custom_id="go_quiz_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_quiz_button.callback = self.go_quiz_button_callback
            self.add_item(self.go_quiz_button)
        
        if task_type == "go_skip_aside_text":
            label = "跳過"
            self.go_skip_aside_text_button = discord.ui.Button(
                custom_id="go_skip_aside_text_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_skip_aside_text_button.callback = self.go_skip_aside_text_button_callback
            self.add_item(self.go_skip_aside_text_button)

        if task_type == "go_skip_growth_info":
            label = "跳過"
            self.go_skip_growth_info_button = discord.ui.Button(
                custom_id="go_skip_growth_info_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_skip_growth_info_button.callback = self.go_skip_growth_info_button_callback
            self.add_item(self.go_skip_growth_info_button)

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

        if task_type == "show_command_instruction":
            label = "📖 解鎖繪本任務秘訣"
            self.show_command_instruction_button = discord.ui.Button(
                custom_id="show_command_instruction_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.show_command_instruction_button.callback = self.show_command_instruction_button_callback
            self.add_item(self.show_command_instruction_button)

        if task_type == "skip_theme_book_aside_text":
            label = "跳過"
            self.skip_theme_book_aside_text_button = discord.ui.Button(
                custom_id="skip_theme_book_aside_text_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.skip_theme_book_aside_text_button.callback = self.skip_theme_book_aside_text_button_callback
            self.add_item(self.skip_theme_book_aside_text_button)

    async def go_book_instruction_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        mission_info = await self.client.api_utils.get_mission_info(self.mission_id)
        embed = discord.Embed(
            title=f"📖繪本介紹: **{mission_info['volume_title']} - {mission_info['photo_mission']}**",
            description=mission_info['mission_instruction'],
            color=0xeeb2da,
        )
        if 'mission_instruction_image_url' in mission_info and mission_info['mission_instruction_image_url'] != "":
            instruction_url = create_preview_image_from_url(mission_info['mission_instruction_image_url'])
            embed.set_image(url=instruction_url)

        payload = {
            'user_id': str(interaction.user.id),
            'book_id': mission_info['book_id'],
            'mission_id': self.mission_id,
            'next_mission_id': self.mission_id,
            'is_first_mission': True,
        }
        view = TaskSelectView(self.client, "go_next_mission", self.mission_id, mission_result=payload)
        view.message = await interaction.channel.send(embed=embed, view=view)
        save_task_entry_record(str(interaction.user.id), str(view.message.id), "go_next_mission", self.mission_id, payload)

    async def go_next_mission_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        user_id = str(interaction.user.id)  
        next_mission_id = self.result['next_mission_id']
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
            await handle_photo_mission_start(self.client, user_id, next_mission_id, send_weekly_report=0)

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
    
    async def go_skip_aside_text_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        self.client.skip_aside_text[str(interaction.user.id)] = True
        await self.submit_image_data(interaction)

    async def go_submit_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        await self.submit_image_data(interaction)

    async def go_skip_growth_info_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        if self.client.reset_baby_profile.get(str(interaction.user.id)):
            await self.client.api_utils.submit_generate_photo_request(str(interaction.user.id), self.mission_id)
            return

        self.client.skip_growth_info[str(interaction.user.id)] = True
        success = await self.submit_baby_data(interaction)
        if success:
            student_mission_info = await self.client.api_utils.get_student_mission_status(str(interaction.user.id), self.mission_id)
            student_mission_info['user_id'] = str(interaction.user.id)
            student_mission_info['current_step'] = 2
            await self.client.api_utils.update_student_mission_status(**student_mission_info)
            message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)

            from bot.handlers.profile_handler import handle_baby_photo_upload
            await handle_baby_photo_upload(self.client, message, student_mission_info)

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
        
            from bot.handlers.profile_handler import handle_baby_photo_upload
            await handle_baby_photo_upload(self.client, message, student_mission_info)

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
        if not student_profile or student_profile.get('gold', 0) < abs(self.result.get('reward', 200)):
            embed = self.get_insufficient_coin_embed()
            await interaction.followup.send(embed=embed)
            return
        else:
            embed = self.get_add_on_photo_embed()
            await interaction.followup.send(embed=embed)

    async def show_command_instruction_button_callback(self, interaction):
        embed = discord.Embed(
            title="快來試試看吧！",
            color=0xeeb2da,
        )
        embed.set_image(url="https://infancixbaby120.com/discord_assets/command_instruction.jpg")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

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

    async def skip_theme_book_aside_text_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        saved_result = get_mission_record(str(interaction.user.id), self.mission_id)
        if not saved_result or 'attachment' not in saved_result:
            await interaction.followup.send("找不到任務紀錄，請稍後再試。")
            return

        student_mission_info = self.result
        book_id = student_mission_info['book_id']
        photo_index = student_mission_info.get('photo_index', -1)

        saved_result['attachment'][photo_index]['aside_text'] = "[使用者選擇跳過]"
        mission_result = self.client.openai_utils.process_theme_book_validation(book_id, saved_result)
        save_mission_record(str(interaction.user.id), self.mission_id, mission_result)

        from bot.handlers.theme_mission_handler import _handle_mission_step
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        await _handle_mission_step(self.client, message, student_mission_info, mission_result)

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
