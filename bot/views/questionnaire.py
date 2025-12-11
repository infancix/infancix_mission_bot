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
        self.questionnaire = self.client.mission_questionnaire[str(mission_id)]
        self.total_rounds = len(self.questionnaire)
        self.current_round = current_round
        self.student_mission_info = student_mission_info
        self.message = None
        self.min_selections = self.questionnaire[current_round].get('min_selections', 1)
        self.max_selections = self.questionnaire[current_round].get('max_selections', 3)
        self.clicked_options = self.student_mission_info.get('clicked_options', [])
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

    async def _safe_send(self, interaction: 'discord.Interaction' = None, content: str = None, update_view=None, **kwargs):
        """Unified safe interaction helper.

        - If update_view is provided, attempt to edit the stored message's view.
        - If content is provided and interaction is provided, try response.send_message,
          fallback to followup.send. If interaction is None or send fails, try editing
          the stored message content as a last resort.
        """
        # 1) update public view if requested
        if update_view is not None:
            if self.message:
                try:
                    await self.message.edit(view=update_view)
                except discord.NotFound:
                    try:
                        self.client.logger.error("❌ 訊息已刪除，無法更新")
                    except Exception:
                        pass
                except Exception as e:
                    try:
                        self.client.logger.debug(f"_safe_send update_view failed: {e}")
                    except Exception:
                        pass

        # 2) send ephemeral / direct content if requested
        if content is None:
            return

        if interaction is not None:
            try:
                await interaction.response.send_message(content, **kwargs)
                return
            except discord.errors.InteractionResponded:
                try:
                    await interaction.followup.send(content, **kwargs)
                    return
                except Exception:
                    pass
            except Exception:
                try:
                    await interaction.followup.send(content, **kwargs)
                    return
                except Exception:
                    pass

        # fallback: edit the public message content if available
        try:
            if self.message:
                await self.message.edit(content=content)
        except Exception:
            pass

    async def _ensure_deferred(self, interaction: discord.Interaction):
        """Ensure the interaction is deferred if possible. If already responded, do nothing."""
        try:
            # Only defer if the interaction hasn't been responded to yet
            await interaction.response.defer()
        except discord.errors.InteractionResponded:
            # already deferred/responded; that's fine
            return
        except Exception as e:
            # log unexpected issues but continue; we prefer to keep flow simple
            try:
                self.client.logger.debug(f"_ensure_deferred: {e}")
            except Exception:
                pass

    def create_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            # Ensure interaction is deferred if not already; keep logic simple otherwise.
            await self._ensure_deferred(interaction)

            try:
                selected_option = self.options[idx]
                if selected_option in self.clicked_options:
                    # remove selection if already selected
                    self.clicked_options.remove(selected_option)
                    self.children[idx].style = discord.ButtonStyle.primary
                    if len(self.clicked_options) < self.max_selections:
                        # keep submit button disabled until enough selections
                        if self.children and hasattr(self.children[-1], 'disabled'):
                            self.children[-1].disabled = True
                else:
                    if len(self.clicked_options) < self.max_selections:
                        self.clicked_options.append(selected_option)
                        self.children[idx].style = discord.ButtonStyle.secondary

                # single-select flow: immediately submit
                if self.max_selections == 1 or len(self.clicked_options) == self.max_selections:
                    for item in self.children:
                        if item.custom_id.startswith("questionnaire_"):
                            item.disabled = True

                    await self._safe_send(interaction, update_view=self)

                    # trigger submit (it uses safe send internally)
                    await self.submit_callback(interaction)
                    return

                # update the public message view and notify the user ephemerally
                await self._safe_send(interaction, update_view=self, ephemeral=True)

            except Exception as e:
                self.client.logger.error(f"處理按鈕邏輯時發生錯誤: {e}")
                await self._safe_send(interaction, "發生錯誤，請重試", ephemeral=True)

        return callback

    async def submit_callback(self, interaction: discord.Interaction):
        await self._safe_send(interaction, "繪本製作中", ephemeral=True)
        try:
            save_questionnaire_record(str(interaction.user.id), str(self.message.id), self.mission_id, self.current_round, self.clicked_options)
            self.client.logger.info(f"✅ 已儲存問卷紀錄，使用者 {interaction.user.id} 任務 {self.mission_id} 回合 {self.current_round}")

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
                from bot.handlers.questionnaire_mission_handler import handle_questionnaire_completion
                message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
                await handle_questionnaire_completion(self.client, message, student_mission_info)

            self.stop()

        except Exception as e:
            self.client.logger.error(f"submit_callback 發生錯誤: {e}")
            await self._safe_send(interaction, "❌ 發生錯誤，請稍後再試。", ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

        await self._safe_send(None, update_view=self)
        try:
            self.client.logger.info("⏰ 時間到，已禁用按鈕")
        except Exception:
            pass
        self.stop()
