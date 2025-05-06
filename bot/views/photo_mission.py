import discord
from bot.config import config

def setup_label(mission):
    if mission['mission_status'] == "Completed":
        status_emoji = "✅"
    elif mission['mission_available'] == 1:
        status_emoji = "📷"
    else:
        status_emoji = "🔒"

    title = mission['mission_title']
    if len(title) > 90:
        title = title[:87] + "..."

    return f"{status_emoji}{title}"

class PhotoTaskSelectView(discord.ui.View):
    def __init__(self, client, user_id, photo_tasks, timeout=3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.add_item(PhotoTaskSelect(client, user_id, photo_tasks))

class PhotoTaskSelect(discord.ui.Select):
    def __init__(self, client, user_id, student_milestones):
        options = [
            discord.SelectOption(
                label=setup_label(mission),
                description=mission['photo_mission'],
                value=mission['mission_id'])
            for mission in student_milestones
        ]

        super().__init__(
            placeholder="🧩 回憶碎片",
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
        await interaction.response.edit_message(view=None)

        from bot.handlers.photo_mission_handler import handle_photo_mission_start
        await handle_photo_mission_start(self.client, str(interaction.user.id), selected_mission_id)
