import discord

from bot.config import config

class MilestoneSelectView(discord.ui.View):
    def __init__(self, client, user_id, unfinished_missions):
        super().__init__(timeout=None)
        self.add_item(MilestoneSelect(client, user_id, unfinished_missions))

class MilestoneSelect(discord.ui.Select):
    def __init__(self, client, user_id, unfinished_missions):
        options = [
            discord.SelectOption(
                label=mission['mission_title'],
                description=mission['mission_type'],
                value=mission['mission_id'])
            for mission in unfinished_missions
        ]

        super().__init__(
            placeholder="選擇一個未完成的任務...",
            min_values=1,
            max_values=1,
            options=options
        )

        self.client = client
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        selected_mission_id = int(self.values[0])

        # Stop View to prevent duplicate interactions
        self.view.stop()
        await interaction.message.edit(view=None)

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        start_task_msg = f"START_MISSION_{selected_mission_id} <@{interaction.user.id}>"
        await channel.send(start_task_msg)

        await interaction.channel.send(f"汪～請交給我，讓加一馬上幫你準備新課程🐾")

