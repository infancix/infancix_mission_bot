import discord
from types import SimpleNamespace

from bot.config import config
from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    load_questionnaire_records,
    save_questionnaire_record,
    delete_questionnaire_record,
    save_task_entry_record,
    delete_task_entry_record
)

class QuestionnaireView(discord.ui.View):
    def __init__(self, client, mission_id, current_round=0, student_mission_info=None, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.questionnaire = self.client.mission_questionnaire[str(mission_id)]
        self.total_rounds = len(self.questionnaire)
        self.current_round = current_round
        self.student_mission_info = student_mission_info
        self.message = None
        self.max_selections = 3
        self.clicked_options = set() or self.student_mission_info.get('clicked_options', set())
        self.is_response = None

        # Get questionnaire
        self.questionnaire = self.client.mission_questionnaire[str(self.mission_id)][current_round]
        self.options = self.questionnaire['options']
        for idx, option in enumerate(self.options):
            button = discord.ui.Button(
                label=option,
                custom_id=f"questionnaire_{self.mission_id}_{self.current_round}_opt_{idx}",
                style=discord.ButtonStyle.primary if option not in self.clicked_options else discord.ButtonStyle.secondary
            )
            button.callback = self.create_callback(idx)
            self.add_item(button)

        self.submit_button = discord.ui.Button(
            custom_id="submit_button",
            label="確認送出" if self.current_round + 1 == self.total_rounds else "下一題",
            style=discord.ButtonStyle.success,
            disabled=True if len(self.clicked_options) < self.max_selections else False
        )
        self.submit_button.callback = self.submit_callback
        self.add_item(self.submit_button)

    def generate_summary_embed(self):
        description = ""
        for round_idx, record in enumerate(self.clicked_options):
            description += (
                f"❓**{self.questionnaire[round_idx]['question']}**\n\n"
                f"你選擇了以下選項：\n"
            )
            for option in record['clicked_options']:
                description += f"- {option}\n"
            description += "\n----\n"

        embed = discord.Embed(
            title="🔍 確認內容",
            description=description,
            color=0xeeb2da
        )
        embed.set_footer(text="請確認以上選項，確認無誤後按下「確認送出」")
        return embed

    def create_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer()
            except discord.errors.InteractionResponded:
                self.client.logger.info(f"交互 {interaction.id} 已經被響應過了")
            except Exception as e:
                self.client.logger.error(f"defer 時發生錯誤: {e}")
                return

            try:
                selected_option = self.options[idx]
                if selected_option in self.clicked_options:
                    # remove selection if already selected
                    self.clicked_options.remove(selected_option)
                    self.children[idx].style = discord.ButtonStyle.primary
                    if len(self.clicked_options) < self.max_selections:
                        self.children[-1].disabled = True
                else:
                    if len(self.clicked_options) < self.max_selections:
                        self.clicked_options.add(selected_option)
                        self.children[idx].style = discord.ButtonStyle.secondary

                content = f"已選擇 {len(self.clicked_options)}/{self.max_selections} 個選項"
                if len(self.clicked_options) >= 3: # Must click 3 times to confirm
                    for item in self.children:
                        if item.custom_id.startswith("questionnaire_"):
                            item.disabled = True
                        elif item.custom_id == "submit_button":
                            item.disabled = False
                    if self.current_round + 1 < self.total_rounds:
                        content = "✅ 選擇完成！確認後按下「下一題」"
                    else:
                        content = "✅ 選擇完成！確認後按下「確認送出」"

                await interaction.edit_original_response(content=content, view=self)

            except Exception as e:
                self.client.logger.error(f"處理按鈕邏輯時發生錯誤: {e}")
                try:
                    await interaction.edit_original_response(content="發生錯誤，請重試")
                except:
                    pass

        return callback

    async def submit_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("更新中...", ephemeral=True)
        try:
            save_questionnaire_record(str(interaction.user.id), str(self.message.id), self.mission_id, self.current_round, self.clicked_options)
            self.client.logger.info(f"✅ 已儲存問卷紀錄，使用者 {interaction.user.id} 任務 {self.mission_id} 回合 {self.current_round}")

            from bot.handlers.questionnaire_mission_handler import send_questionnaire_end
            message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
            current_step = 3 if self.current_round + 1 == self.total_rounds else 2
            student_mission_info = {
                'user_id': str(interaction.user.id),
                'mission_id': self.mission_id,
                'current_step': current_step,
            }
            await self.client.api_utils.update_student_mission_status(**student_mission_info)
            self.client.logger.info(f"✅ 更新任務狀態，使用者 {interaction.user.id} 任務 {self.mission_id} 狀態 {current_step}")

            # Proceed to next step or end
            if self.current_round + 1 < self.total_rounds:
                from bot.handlers.questionnaire_mission_handler import handle_questionnaire_round
                message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
                await handle_questionnaire_round(self.client, message, student_mission_info, self.current_round + 1)
            else:
                from bot.handlers.questionnaire_mission_handler import handle_questionnaire_round
                message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
                await send_questionnaire_end(self.client, message, student_mission_info)

            self.stop()

        except Exception as e:
            await interaction.response.send_message("❌ 發生錯誤，請稍後再試。", ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                self.client.logger.info("⏰ 時間到，已禁用按鈕")
            except discord.NotFound:
                self.client.logger.error("❌ 訊息已刪除，無法更新")

        self.stop()
