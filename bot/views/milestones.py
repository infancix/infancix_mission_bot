import discord

from bot.config import config

def calculate_spacer(label_text: str, score_text, max_spaces: int = 40) -> str:
    label_text_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in label_text)
    score_text_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in score_text)
    spaces = max_spaces - label_text_length - score_text_length - 1
    return '\u2000' * max(1, spaces)

def setup_label(mission_type, mission):
    score = int(float(mission['mission_completion_percentage'])*100)
    score_text = f"(完成度: {score})"
    title = ""
    if int(mission['mission_id']) in config.photo_mission_list:
        title += "📸"
    elif int(mission['mission_id']) in config.record_mission_list:
        title += "📝"

    title += f"{mission['mission_title']}" if mission_type == 'video_task' else f"{mission['photo_mission']}"
    if score >= 100:
        title += " ✅"

    spaces = calculate_spacer(title, score_text)
    return f"{title}{spaces}{score_text}"

class MilestoneSelectView(discord.ui.View):
    def __init__(self, client, user_id, student_milestones, mission_type, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        if mission_type == 'video_task':
            self.add_item(MilestoneSelect(client, user_id, student_milestones, mission_type))
        else:
            self.add_item(PhotoTaskSelect(client, user_id, student_milestones, mission_type))

class MilestoneSelect(discord.ui.Select):
    def __init__(self, client, user_id, student_milestones, mission_type):
        options = [
            discord.SelectOption(
                label=setup_label(mission_type, mission),
                description=mission['mission_type'],
                value=mission['mission_id'])
            for mission in student_milestones
        ]

        super().__init__(
            placeholder="檢視課程進度...",
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

        is_ephemeral = interaction.message.flags.ephemeral
        if is_ephemeral:
            await interaction.response.edit_message(view=None)
            await interaction.followup.send(
                "汪～請交給我，讓加一馬上幫你準備新課程🐾\n會需要一點時間喔，請耐心等候😊",
                ephemeral=True
            )
        else:
            await interaction.message.edit(
                f"汪～請交給我，讓加一馬上幫你準備新課程🐾\n會需要一點時間喔，請耐心等候😊",
                view=None
            )

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        start_task_msg = f"START_MISSION_{selected_mission_id} <@{interaction.user.id}>"
        await channel.send(start_task_msg)

class PhotoTaskSelect(discord.ui.Select):
    def __init__(self, client, user_id, student_milestones, mission_type='photo_task'):
        options = [
            discord.SelectOption(
                label=setup_label(mission_type, mission),
                description=mission['mission_type'],
                value=mission['mission_id'])
            for mission in student_milestones
        ]

        super().__init__(
            placeholder="檢視照片任務...",
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

        is_ephemeral = interaction.message.flags.ephemeral
        if is_ephemeral:
            await interaction.response.edit_message(view=None)
            await interaction.followup.send(
                "汪～請交給我🐾\n會需要一點時間喔，請耐心等候😊",
                ephemeral=True
            )
        else:
            await interaction.message.edit(
                f"汪～請交給我🐾\n會需要一點時間喔，請耐心等候😊",
                view=None
            )

        from bot.handlers.photo_mission_handler import handle_photo_mission_start
        await handle_photo_mission_start(self.client, interaction.user.id, selected_mission_id)

