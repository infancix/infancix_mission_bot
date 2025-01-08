import discord

from bot.config import config
from bot.utils.utils import (
    update_student_mission_status,
    get_student_incompleted_mission_list,
)
from bot.views.unfinish_mission import MilestoneSelectView

class TerminateButton(discord.ui.Button):
    def __init__(
        self, client, label, msg, user_data, style=discord.ButtonStyle.secondary
    ):
        super().__init__(label=label, style=style)
        self.client = client
        self.msg = msg
        self.mission_id = user_data['mission_id']
        self.total_steps = user_data['total_steps']
        self.current_step = str(user_data['total_steps'])
        self.ending_message = f"🎉 恭喜完成任務，獲得🪙{user_data['reward']}金幣🎉"

    async def callback(self, interaction: discord.Interaction):
        self.disabled = True
        if interaction.message is None:
            return

        await interaction.message.edit(view=self.view)

        # Send the ending message to the user
        await interaction.user.send(self.ending_message)

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"MISSION_{self.mission_id}_FINISHED <@{interaction.user.id}>"
        await channel.send(msg_task)
        await update_student_mission_status(
            interaction.user.id, self.mission_id, self.total_steps, self.current_step
        )
        await interaction.response.send_message(self.msg)

        unfinished_missions = await get_student_incompleted_mission_list(interaction.user.id)
        if unfinished_missions:
            milestone_view = MilestoneSelectView(self.client, interaction.user.id, unfinished_missions)
            await interaction.channel.send(
                "🔍 *以下是您尚未完成的里程碑任務，按下方按鈕開始任務* 🔍",
                view=milestone_view
            )

