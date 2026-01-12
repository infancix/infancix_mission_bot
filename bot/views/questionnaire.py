import discord
from types import SimpleNamespace

from bot.config import config
from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    load_questionnaire_records,
    save_questionnaire_record,
    delete_questionnaire_record,
    save_task_entry_record,
    delete_task_entry_record,
    get_mission_record,
    save_mission_record,
    delete_mission_record,
)

class QuestionnaireView(discord.ui.View):
    def __init__(self, client, mission_id, current_round=0, student_mission_info=None, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.current_round = current_round
        self.student_mission_info = student_mission_info
        self.message = None
        self.total_rounds = 1  # Simplified: one question per view

        # Get current questionnaire (only one question)
        self.questionnaire = self.client.mission_questionnaire[str(self.mission_id)][current_round]
        self.min_selections = self.questionnaire.get('min_selections', 1)
        self.max_selections = self.questionnaire.get('max_selections', 3)
        self.clicked_options = self.student_mission_info.get('clicked_options', [])
        self.is_response = None

        # Get options (use .get() to avoid KeyError for non-choice questions)
        self.options = self.questionnaire.get('options', [])
        for idx, option in enumerate(self.options):
            button = discord.ui.Button(
                label=option,
                custom_id=f"questionnaire_{self.mission_id}_{self.current_round}_opt_{idx}",
                style=discord.ButtonStyle.primary if option not in self.clicked_options else discord.ButtonStyle.secondary
            )
            button.callback = self.create_callback(idx)
            self.add_item(button)

        # Add skip button if there's a next mission
        if student_mission_info and student_mission_info.get('next_mission_id'):
            skip_button = discord.ui.Button(
                label="跳過此任務",
                custom_id=f"questionnaire_skip_{self.mission_id}",
                style=discord.ButtonStyle.secondary
            )
            skip_button.callback = self.skip_callback
            self.add_item(skip_button)

    async def update_view(self, interaction: discord.Interaction):
        """Update the message view (buttons)"""
        try:
            await interaction.response.edit_message(view=self)
        except discord.errors.InteractionResponded:
            await self.message.edit(view=self)

    async def send_ephemeral(self, interaction: discord.Interaction, content: str):
        """Send ephemeral message to user"""
        try:
            await interaction.response.send_message(content, ephemeral=True)
        except discord.errors.InteractionResponded:
            await interaction.followup.send(content, ephemeral=True)

    def create_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            try:
                selected_option = self.options[idx]
                if selected_option in self.clicked_options:
                    # remove selection if already selected
                    self.clicked_options.remove(selected_option)
                    self.children[idx].style = discord.ButtonStyle.primary
                else:
                    if len(self.clicked_options) < self.max_selections:
                        self.clicked_options.append(selected_option)
                        self.children[idx].style = discord.ButtonStyle.secondary

                # single-select or max selections reached: immediately submit
                if self.max_selections == 1 or len(self.clicked_options) == self.max_selections:
                    # Disable all buttons
                    for item in self.children:
                        if item.custom_id.startswith("questionnaire_"):
                            item.disabled = True

                    await self.update_view(interaction)
                    # trigger submit
                    await self.submit_callback(interaction)
                    return

                # update the message view
                await self.update_view(interaction)

            except Exception as e:
                self.client.logger.error(f"處理按鈕邏輯時發生錯誤: {e}")
                await self.send_ephemeral(interaction, "發生錯誤，請重試")

        return callback

    async def submit_callback(self, interaction: discord.Interaction):
        await self.send_ephemeral(interaction, "繪本製作中")
        user_id = str(interaction.user.id)
        try:
            save_questionnaire_record(user_id, str(self.message.id), self.mission_id, self.current_round, self.clicked_options)
            self.client.logger.info(f"✅ 已儲存問卷紀錄，使用者 {interaction.user.id} 任務 {self.mission_id} 回合 {self.current_round}")

            # Save results
            mission_result = get_mission_record(user_id, self.mission_id) or {}
            click_summary = "、".join(opt.split('.')[-1] for opt in self.clicked_options)

            # Simplified: always save to first element since total_rounds = 1
            mission_result['aside_texts'] = [click_summary]
            save_mission_record(user_id, self.mission_id, mission_result)

            # Simplified: always go to completion since total_rounds = 1
            student_mission_info = {
                'user_id': user_id,
                'mission_id': self.mission_id,
                'current_step': self.student_mission_info['current_step'] + 1
            }
            await self.client.api_utils.update_student_mission_status(**student_mission_info)

            # Complete questionnaire round
            from bot.handlers.questionnaire_mission_handler import handle_questionnaire_next_mission
            message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
            await handle_questionnaire_next_mission(self.client, message, student_mission_info, mission_result)

            self.stop()

        except Exception as e:
            self.client.logger.error(f"submit_callback 發生錯誤: {e}")
            await self.send_ephemeral(interaction, "❌ 發生錯誤，請稍後再試。")

    async def skip_callback(self, interaction: discord.Interaction):
        """Skip current questionnaire mission and go to next mission"""
        # Disable all buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        from bot.handlers.utils import start_mission_by_id
        user_id = str(interaction.user.id)
        next_mission_id = self.student_mission_info.get('next_mission_id')

        if next_mission_id:
            await start_mission_by_id(self.client, user_id, next_mission_id, send_weekly_report=0)

        self.stop()

    async def on_timeout(self):
        """Disable buttons on timeout"""
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                self.client.logger.info("⏰ 時間到，已禁用按鈕")
            except Exception:
                pass
        self.stop()
