import discord

from bot.config import config
from bot.views.unfinish_mission import MilestoneSelectView

class OptinClassButton(discord.ui.Button):
    def __init__(
        self, client, user_id, label, style=discord.ButtonStyle.secondary
    ):
        super().__init__(label=label, style=style)
        self.client = client
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        # Disable the button to prevent duplicate interactions
        self.disabled = True
        if interaction.message is None:
            return
        await interaction.message.edit(view=self.view)

        # Ensure we provide an immediate response to the interaction
        await interaction.response.defer()  # Indicates processing is ongoing

        # Perform the backend logic
        await self.client.api_utils.optin_class(self.user_id)

        # Determine the message to send based on the student status
        student_status = await self.client.api_utils.check_student_mission_eligible(self.user_id)
        if student_status == "over_31_days":
            msg = (
                "感謝登記，請交給我，讓加一馬上幫你準備第一堂課🐾\n"
                "汪～會需要一點時間喔，請耐心等候😊\n"
            )
        elif student_status == "pregnancy_or_newborn_stage":
            msg = "感謝登記，咱們在寶寶滿月後見啦！"
        else:
            msg = "請先到寶寶檔案室登記寶寶資料/或是預產期喔"

        # Send the final message to the user
        await interaction.user.send(msg)
        await self.client.api_utils.store_message(self.user_id, 'assistant', msg)

        if student_status == "over_31_days":
            channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
            if channel is None or not isinstance(channel, discord.TextChannel):
                raise Exception('Invalid channel')
            msg_task = f"START_MISSION_1 <@{interaction.user.id}>"
            await channel.send(msg_task)

class TerminateButton(discord.ui.Button):
    def __init__(
        self, client, label, msg, user_data, style=discord.ButtonStyle.secondary
    ):
        super().__init__(label=label, style=style)
        self.client = client
        self.msg = msg
        self.mission_id = user_data['mission_id']
        self.total_steps = 6
        self.current_step = 6
        self.ending_message = f"🎉 恭喜完成任務，獲得🪙{user_data['reward']}金幣🎉"

    async def callback(self, interaction: discord.Interaction):
        self.disabled = True
        if interaction.message is None:
            return

        # Send the ending message to the user
        await interaction.message.edit(view=self.view)
        await interaction.response.send_message(self.msg)
        await interaction.user.send(self.ending_message)

        # Update mission status
        await self.client.api_utils.update_student_mission_status(
            interaction.user.id, self.mission_id, self.total_steps, self.current_step
        )

        # Send ending message to 背景紀錄
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')
        msg_task = f"MISSION_{self.mission_id}_FINISHED <@{interaction.user.id}>"
        await channel.send(msg_task)

        # Provide unfinish mission lists
        unfinished_missions = await self.client.api_utils.get_student_incompleted_mission_list(interaction.user.id)
        if unfinished_missions:
            milestone_view = MilestoneSelectView(self.client, interaction.user.id, unfinished_missions)
            await interaction.channel.send(
                "🔍 *以下是您尚未完成的里程碑任務，按下方按鈕開始任務* 🔍",
                view=milestone_view
            )

