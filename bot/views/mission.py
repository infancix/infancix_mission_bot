import discord

from bot.config import config

def calculate_spacer(label_text: str, max_spaces: int = 40) -> str:
    label_text_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in label_text)
    spaces = max_spaces - label_text_length - 1
    return '\u2000' * max(1, spaces)

def setup_label(mission):
    title = f"{mission['mission_title']}"
    if mission['mission_status'] == 'Completed':
        title += " ✅"
    return f"{title}"

class MilestoneSelectView(discord.ui.View):
    def __init__(self, client, user_id, student_milestones, timeout=3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.student_milestones = student_milestones['milestones']
        self.total_pages = len(self.student_milestones)
        self.current_page = int(student_milestones['current_stage'])

        self.update_select_menu()
        self.update_buttons()

    def update_select_menu(self):
        # Remove current buttons
        for item in self.children[:]:
            if isinstance(item, MilestoneSelect):
                self.remove_item(item)

        current_milestones = self.student_milestones[str(self.current_page)]
        self.add_item(MilestoneSelect(self.client, self.user_id, current_milestones))

    def update_buttons(self):
        # Remove current buttons
        for item in self.children[:]:
            if isinstance(item, (PreviousButton, NextButton, PageIndicator)):
                self.remove_item(item)

        self.add_item(PreviousButton(self.current_page > 0))
        self.add_item(PageIndicator(self.current_page, self.total_pages))
        self.add_item(NextButton(self.current_page < self.total_pages - 1))

class PreviousButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="⬅上一個月份",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page -= 1
        view.update_select_menu()
        view.update_buttons()
        await interaction.response.edit_message(view=view)

class NextButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="下一個月份⮕",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page += 1
        view.update_select_menu()
        view.update_buttons()
        await interaction.response.edit_message(view=view)

class PageIndicator(discord.ui.Button):
    def __init__(self, current_page, total_pages):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=f"{current_page + 1}/{total_pages}",
            disabled=True,
            row=1
        )

class MilestoneSelect(discord.ui.Select):
    def __init__(self, client, user_id, student_milestones):
        options = []
        for mission in student_milestones:
            mission_id = int(mission['mission_id'])
            if mission['mission_available'] <= 0:
                continue
            else:
                if mission.get('mission_type') is not None and mission['mission_type'] != "":
                    description = f"{mission['mission_type']}"
                else:
                    description = f"{mission['book_type']} | {mission['volume_title']}"

                if mission.get('photo_mission') and mission['photo_mission'] and mission['photo_mission'] != "":
                    description += f" | {mission['photo_mission']}"

                mission_available = mission['mission_available']

            options.append(
                discord.SelectOption(
                    label=setup_label(mission),
                    description=description,
                    value=f"{mission_id}_{mission_available}"
                )
            )

        mission = student_milestones[0]
        class_type = '里程碑' if '里程碑' in mission.get('mission_type') else '成長週報'
        super().__init__(
            placeholder=f"查看{class_type}...",
            min_values=1,
            max_values=1,
            options=options
        )

        self.client = client
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        selected_mission = self.values[0]
        selected_mission_id = int(selected_mission.split('_')[0])
        mission_available = int(selected_mission.split('_')[-1])
        mission = await self.client.api_utils.get_mission_info(selected_mission_id)
        class_type = '里程碑' if '里程碑' in mission.get('mission_type') else '成長週報'

        if not mission_available:
            await interaction.followup.send("僅提供購買繪本的家長查看喔！", ephemeral=True)
            return

        self.view.stop()
        await interaction.response.edit_message(content=f"選擇{class_type}: {mission['mission_title']}", view=None)
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        msg_task = f"START_CLASS_{selected_mission_id} <@{self.user_id}>"
        await channel.send(msg_task)
