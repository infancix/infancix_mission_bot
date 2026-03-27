import discord
import random
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

from bot.config import config
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.utils.message_tracker import save_task_entry_record, delete_task_entry_record, get_mission_record, save_mission_record

class TaskSelectView(discord.ui.View):
    def __init__(self, client, task_type, mission_id, mission_result={}, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.book_id = mission_result.get('book_id', 0) if mission_result is not None else 0
        self.mission_result = mission_result
        self.message = None

        if "go_book_instruction" in task_type:
            label = "開始製作繪本"
            self.go_book_instruction_button = discord.ui.Button(
                custom_id="go_book_instruction_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.go_book_instruction_button.callback = self.go_book_instruction_button_callback
            self.add_item(self.go_book_instruction_button)

        if "go_next_mission" in task_type:
            if self.mission_result.get('next_book_title'):
                label = f"製作《{self.mission_result.get('next_book_title')}》"
            elif self.mission_result.get('is_first_mission'):
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

        if "go_purchase" in task_type:
            label = "購買繪本"
            self.purchase_button = discord.ui.Button(
                custom_id="purchase_button",
                label=label,
                style=discord.ButtonStyle.success,
            )
            self.purchase_button.callback = self.purchase_button_callback
            self.add_item(self.purchase_button)

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

        if task_type == "baby_optin":
            label = "送出"
            self.baby_optin_button = discord.ui.Button(
                custom_id="baby_optin_button",
                label=label,
                style=discord.ButtonStyle.success
            )
            self.baby_optin_button.callback = self.baby_optin_button_callback
            self.add_item(self.baby_optin_button)

        if task_type == "baby_pre_registration_confirm":
            # Confirm button
            confirm_button = discord.ui.Button(
                custom_id="baby_pre_confirm_button",
                label="✓ 確認並繼續",
                style=discord.ButtonStyle.success
            )
            confirm_button.callback = self.baby_pre_confirm_button_callback
            self.add_item(confirm_button)

            # Re-fill button
            refill_button = discord.ui.Button(
                custom_id="baby_pre_refill_button",
                label="✎ 重新填寫",
                style=discord.ButtonStyle.secondary
            )
            refill_button.callback = self.baby_pre_refill_button_callback
            self.add_item(refill_button)

        if task_type == "check_add_on":
            label = "我要加購"
            self.check_add_on_button = discord.ui.Button(
                custom_id="check_add_on_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.check_add_on_button.callback = self.check_add_on_button_callback
            self.add_item(self.check_add_on_button)

            if self.mission_result.get('next_mission_id'):
                label = "跳過此任務"
                self.skip_mission_button = discord.ui.Button(
                    custom_id="skip_mission_button",
                    label=label,
                    style=discord.ButtonStyle.secondary
                )
                self.skip_mission_button.callback = self.go_next_mission_button_callback
                self.add_item(self.skip_mission_button)
            else:
                label = '返回繪本狀態'
                self.return_album_button = discord.ui.Button(
                    custom_id="return_album_button",
                    label=label,
                    style=discord.ButtonStyle.secondary
                )
                self.return_album_button.callback = self.return_album_button_callback
                self.add_item(self.return_album_button)

        if task_type == "theme_baby_info_confirm":
            # Confirm button
            confirm_button = discord.ui.Button(
                custom_id="theme_baby_info_confirm_button",
                label="✓ 確認並繼續",
                style=discord.ButtonStyle.success
            )
            confirm_button.callback = self.theme_baby_info_confirm_button_callback
            self.add_item(confirm_button)

        if task_type == "skip_theme_book_aside_text":
            label = "跳過"
            self.skip_theme_book_aside_text_button = discord.ui.Button(
                custom_id="skip_theme_book_aside_text_button",
                label=label,
                style=discord.ButtonStyle.primary
            )
            self.skip_theme_book_aside_text_button.callback = self.skip_theme_book_aside_text_button_callback
            self.add_item(self.skip_theme_book_aside_text_button)

        if task_type == "skip_mission":
            if self.mission_result.get('next_mission_id'):
                label = "跳過此任務"
                self.skip_mission_button = discord.ui.Button(
                    custom_id="skip_mission_button",
                    label=label,
                    style=discord.ButtonStyle.secondary
                )
                self.skip_mission_button.callback = self.go_next_mission_button_callback
                self.add_item(self.skip_mission_button)
            else:
                label = '返回繪本狀態'
                self.return_album_button = discord.ui.Button(
                    custom_id="return_album_button",
                    label=label,
                    style=discord.ButtonStyle.secondary
                )
                self.return_album_button.callback = self.return_album_button_callback
                self.add_item(self.return_album_button)

    async def go_book_instruction_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        mission_info = await self.client.api_utils.get_mission_info(self.mission_id)
        embed = discord.Embed(
            title=f"📖繪本介紹: **{mission_info['book_month_label']} - {mission_info['mission_title']}**",
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

        from bot.handlers.utils import start_mission_by_id
        user_id = str(interaction.user.id)
        next_mission_id = self.mission_result['next_mission_id']
        await start_mission_by_id(self.client, user_id, next_mission_id, send_weekly_report=1)
    
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

    async def baby_pre_confirm_button_callback(self, interaction):
        """確認寶寶資料,提交並產生繪本"""
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        user_id = str(interaction.user.id)

        # Submit baby data (similar to process_baby_profile_filling)
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        student_mission_info = {
            'user_id': user_id,
            'mission_id': self.mission_id
        }

        # Submit the baby profile data
        from bot.handlers.profile_handler import submit_baby_data, submit_image_data
        success = await submit_baby_data(self.client, message, student_mission_info, self.mission_result)

        if success:
            # Submit image if it's baby_registration_mission and has attachment
            if self.mission_id == config.baby_registration_mission and self.mission_result.get('attachment'):
                await submit_image_data(self.client, message, student_mission_info, self.mission_result)

            # Generate the photo/book
            await self.client.api_utils.submit_generate_photo_request(user_id, self.mission_id)
            self.client.logger.info(f"送出繪本任務 {self.mission_id}")
        else:
            await interaction.followup.send("更新寶寶資料失敗，請稍後再試。")

    async def baby_pre_refill_button_callback(self, interaction):
        """重新填寫寶寶資料"""
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        # Show the input form
        mission_info = await self.client.api_utils.get_mission_info(self.mission_id)
        from bot.handlers.profile_handler import get_baby_name_registration_embed
        embed = get_baby_name_registration_embed(mission_info)
        await interaction.followup.send(embed=embed)

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

        # update baby profile
        payload = {
            'baby_name': self.mission_result.get('baby_name'),
            'baby_name_en': self.mission_result.get('baby_name_en'),
            'gender': self.mission_result.get('gender'),
            'birthday': self.mission_result.get('birthday'),
            'height': self.mission_result.get('height'),
            'weight': self.mission_result.get('weight'),
            'head_circumference': self.mission_result.get('head_circumference'),
        }
        response = await self.client.api_utils.update_student_baby_profile(str(interaction.user.id), **payload)
        if not response:
            await interaction.followup.send("更新寶寶資料失敗，請稍後再試。")
            return
        return True

    async def submit_image_data(self, interaction):
        if not self.mission_result:
            return

        user_id = str(interaction.user.id)

        # Check if this is a photo mission - use new photo_mission_handler logic
        from bot.config import config
        if self.mission_id in config.photo_mission_list:
            from bot.handlers.photo_mission_handler import submit_photo_mission
            from types import SimpleNamespace

            # Create a message-like object for submit_photo_mission
            message = SimpleNamespace(author=interaction.user, channel=interaction.channel)
            student_mission_info = {'mission_id': self.mission_id}

            await submit_photo_mission(self.client, message, student_mission_info, self.mission_result)

        # For other missions, use original logic
        elif self.mission_result.get('attachment'):
            attachment_obj = [self.mission_result.get('attachment')]
            update_status = await self.client.api_utils.update_mission_image_content(
                user_id, self.mission_id, attachment_obj,
                aside_text=self.mission_result.get('aside_text'),
                content=self.mission_result.get('content')
            )

            if bool(update_status):
                await self.client.api_utils.submit_generate_photo_request(user_id, self.mission_id)
                self.client.logger.info(f"送出繪本任務 {self.mission_id}")

    async def check_add_on_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        # Handle the add-on purchase logic here
        student_profile = await self.client.api_utils.get_student_profile(str(interaction.user.id))
        if not student_profile or student_profile.get('gold', 0) < abs(self.mission_result.get('reward', 200)):
            embed = self.get_insufficient_coin_embed()
            await interaction.followup.send(embed=embed)
            delete_task_entry_record(str(self.message.author.id), str(self.mission_id))
            return
        else:
            embed = self.get_add_on_photo_embed()
            await interaction.followup.send(embed=embed)
            delete_task_entry_record(str(self.message.author.id), str(self.mission_id))
            return

    def get_insufficient_coin_embed(self):
        embed = discord.Embed(
            title="👛 餘額不足",
            color=0xeeb2da,
        )
        embed.add_field(name="🫰 如何獲得金幣", value="解任務、參與活動", inline=False)
        embed.add_field(name="🔍︎ 查看金幣餘額", value="請至 <@1272828469469904937> 於私訊對話框輸入 */我的檔案* 查詢喔", inline=False)
        embed.add_field(name="🥺 如何回來賺買", value="於對話框輸入 */補上傳照片*，重新製作喔！", inline=False)
        return embed

    def get_add_on_photo_embed(self):
        embed = discord.Embed(
            title="💸 加購成功",
            description="**製作加購頁**\n請上傳四張照片",
            color=0xeeb2da,
        )
        embed.set_footer(text="可以一次上傳多張喔!")
        instruction_url = self.mission_result.get('mission_instruction_image_url', '').split(',')[-1]
        if instruction_url:
            instruction_url = create_preview_image_from_url(instruction_url)
        else:
            instruction_url = "https://infancixbaby120.com/discord_assets/book1_add_on_photo_mission.png"
        embed.set_image(url=instruction_url)
        return embed

    async def theme_baby_info_confirm_button_callback(self, interaction):
        """Confirm baby info and proceed to cover photo upload for theme missions"""
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        user_id = str(interaction.user.id)
        mission_id = self.mission_id

        # Get saved mission record and mark step_1_completed
        saved_result = get_mission_record(user_id, mission_id)
        if not saved_result:
            await interaction.followup.send("找不到任務紀錄，請重新開始任務。")
            return

        saved_result['step_1_completed'] = True
        save_mission_record(user_id, mission_id, saved_result)

        # Get mission info to show cover instruction
        mission = await self.client.api_utils.get_mission_info(mission_id)
        from bot.handlers.theme_mission_handler import get_cover_instruction_embed
        embed = get_cover_instruction_embed(mission)
        await interaction.followup.send(embed=embed)

        # Update mission status to step 2
        student_mission_info = {
            **mission,
            'user_id': user_id,
            'current_step': 2,
            'total_steps': 4
        }
        await self.client.api_utils.update_student_mission_status(**student_mission_info)

    async def skip_theme_book_aside_text_button_callback(self, interaction):
        await interaction.response.defer()
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)

        book_id = self.mission_result['book_id']
        saved_result = get_mission_record(str(interaction.user.id), self.mission_id)
        saved_result['aside_texts'] = saved_result.get('aside_texts', [])

        if str(interaction.user.id) in self.client.photo_mission_replace_index:
            photo_index = self.client.photo_mission_replace_index[str(interaction.user.id)]
            saved_result['aside_texts'][photo_index-1] = {
                "photo_index": photo_index,
                "aside_text": "[使用者選擇跳過]"
            }
        else:
            photo_index = len(saved_result['aside_texts']) + 1
            saved_result['aside_texts'].append({
                "photo_index": photo_index,
                "aside_text": "[使用者選擇跳過]"
            })

        self.client.logger.info(f"使用者 {interaction.user.id} 選擇跳過繪本({book_id}) {photo_index} 頁面旁白文字")
        mission_result = self.client.openai_utils.process_theme_book_validation(book_id, saved_result)
        save_mission_record(str(interaction.user.id), self.mission_id, mission_result)

        from bot.handlers.theme_mission_handler import _handle_mission_step
        message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
        student_mission_info = {
            **self.mission_result,
            'user_id': str(interaction.user.id),
            'current_step': 3,
        }
        await _handle_mission_step(self.client, message, student_mission_info, mission_result)

    async def purchase_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        # Send log to Background channel
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"<@{str(interaction.user.id)}> 購買繪本"
        await channel.send(msg_task)

        await interaction.channel.send(f"🛒 已收到您的購買請求！社群客服「阿福 <@1272828469469904937>」會儘快與您聯繫。")

    async def return_album_button_callback(self, interaction):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        from bot.views.album_select_view import AlbumView

        self.user_id = str(interaction.user.id)
        book_info = await self.client.api_utils.get_album_info(book_id=self.book_id) or {}
        book_status = await self.client.api_utils.get_student_album_purchase_status(self.user_id, book_id=self.book_id) or {}
        book_info.update(book_status)
        completed_missions = await self.client.api_utils.get_student_complete_photo_mission(
            user_id=self.user_id,
            book_id=self.book_id
        )
        incomplete_missions = await self.client.api_utils.get_student_incomplete_photo_mission(
            user_id=self.user_id,
            book_id=self.book_id
        )

        view = AlbumView(
            self.client,
            self.user_id,
            book_info,
            completed_missions,
            incomplete_missions
        )
        embed, file_path, filename, fallback_url = view.preview_embed()
        await view.send_embed_with_file(interaction, embed, view, file_path, filename, fallback_url, use_response=False)

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
