import discord

from bot.config import config
from bot.utils.utils import update_student_mission_status

class TerminateButton(discord.ui.Button):
    def __init__(
        self, client, label, msg, user_data, style=discord.ButtonStyle.secondary
    ):
        super().__init__(label=label, style=style)
        self.client = client
        self.msg = msg
        self.mission_id = user_data['mission_id']
        self.assistant_id = user_data['assistant_id']
        self.thread_id = user_data['thread_id']
        self.total_steps = user_data['total_steps']
        self.current_step = str(user_data['total_steps'])

    async def callback(self, interaction: discord.Interaction):
        self.disabled = True
        if interaction.message is None:
            return

        await interaction.message.edit(view=self.view)

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"MISSION_{self.mission_id}_FINISHED <@{interaction.user.id}>"
        await channel.send(msg_task)
        await update_student_mission_status(
            interaction.user.id, self.mission_id, self.total_steps, self.current_step
        )

        response = self.client.gpt_client.client.beta.assistants.delete(self.assistant_id)
        response = self.client.gpt_client.client.beta.threads.delete(self.thread_id)

        await interaction.response.send_message(self.msg)
