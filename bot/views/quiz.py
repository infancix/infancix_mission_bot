import discord
from types import SimpleNamespace

from bot.config import config
from bot.utils.message_tracker import delete_quiz_message_record

class QuizView(discord.ui.View):
    def __init__(self, client, mission_id, current_round, correct, student_mission_info=None, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.mission_id = mission_id
        self.current_round = current_round
        self.correct = correct
        self.student_mission_info = student_mission_info
        self.message = None

        # Get quiz
        self.quiz = self.client.mission_quiz[str(mission_id)][current_round]
        self.options = self.quiz['options']
        for idx, option in enumerate(self.options):
            button = discord.ui.Button(label=option['option'], custom_id=f"quiz_{mission_id}_{current_round}_opt_{idx}")
            button.callback = self.create_callback(idx)
            self.add_item(button)

    def create_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            try:
                selected_option = self.options[idx]
                is_correct = selected_option['option'][0] == self.quiz['answer']
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(view=self)

                # update score
                if is_correct:
                    self.correct += 1
                    await interaction.channel.send("回答正確！ 🎉\n\n")
                else:
                    explanation = selected_option['explanation']
                    await interaction.channel.send(f"正確答案是：{self.quiz['answer']}\n{explanation}\n\n")
                self.stop()

                from bot.handlers.video_mission_handler import handle_quiz, send_quiz_summary
                if self.current_round+1 >= 5:
                    delete_quiz_message_record(str(interaction.user.id))
                    await send_quiz_summary(interaction, self.correct, self.student_mission_info)
                else:
                    message = SimpleNamespace(author=interaction.user, channel=interaction.channel, content=None)
                    await handle_quiz(self.client, message, self.student_mission_info, self.current_round + 1, self.correct)

            except Exception as e:
                await interaction.response.defer()
                raise e
        return callback

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


