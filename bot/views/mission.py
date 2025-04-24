import discord

from bot.config import config

stage_to_page = {
    '第一階段': 0,
    '第二階段': 1,
    '第三階段': 2,
    '第四階段': 3,
    '第五階段': 4,
    '第六階段': 5,
}

page_to_stage = {
    0: '第一階段',
    1: '第二階段',
    2: '第三階段',
    3: '第四階段',
    4: '第五階段',
    5: '第六階段'
}

def calculate_spacer(label_text: str, score_text, max_spaces: int = 40) -> str:
    label_text_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in label_text)
    score_text_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in score_text)
    spaces = max_spaces - label_text_length - score_text_length - 1
    return '\u2000' * max(1, spaces)

def setup_label(mission):
    score = int(float(mission['mission_completion_percentage'])*100)
    score_text = f"(完成度: {score})"
    title = ""
    if int(mission['mission_id']) in config.photo_mission_list:
        title += "📸"
    elif int(mission['mission_id']) in config.record_mission_list:
        title += "📝"

    title += f"{mission['mission_title']}"
    if mission['mission_status'] == 'Completed':
        title += " ✅"

    spaces = calculate_spacer(title, score_text)
    return f"{title}{spaces}{score_text}"

class MilestoneSelectView(discord.ui.View):
    def __init__(self, client, user_id, student_milestones, timeout=3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.student_milestones = student_milestones['milestones']
        init_stage = student_milestones['current_stage']
        self.current_page = stage_to_page[init_stage]
        self.total_pages = 6
        print("total_pages", self.total_pages, "current_page", self.current_page)

        self.update_select_menu()
        self.update_buttons()

    def update_select_menu(self):
        # Remove current buttons
        for item in self.children[:]:
            if isinstance(item, MilestoneSelect):
                self.remove_item(item)

        current_milestones = self.student_milestones[page_to_stage[self.current_page]]
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
            label="上一階段",
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
            label="下一階段",
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
        warning = "⚠️ 寶寶年齡尚未符合要求"
        options = [
            discord.SelectOption(
                label=setup_label(mission),
                description=(mission['mission_type'] + warning) if not mission['mission_available'] else mission['mission_type'],
                value=f"{mission['mission_id']}_{mission['mission_available']}"
            )
            for mission in student_milestones
        ]

        super().__init__(
            placeholder="查看任務進度...",
            min_values=1,
            max_values=1,
            options=options
        )

        self.client = client
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        selected_mission = self.values[0]
        print(selected_mission)
        selected_mission_id = int(selected_mission.split('_')[0])
        mission_available = int(selected_mission.split('_')[-1])
        mission = await self.client.api_utils.get_mission_info(selected_mission_id)

        self.view.stop()
        await interaction.response.edit_message(content=f"選擇任務: {mission['mission_title']}", view=None)
    
        if not mission_available:
            await interaction.followup.send("您的寶寶年齡還太小囉，還不能解這個任務喔", ephemeral=True)
            return

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        start_task_msg = f"START_MISSION_{selected_mission_id} <@{interaction.user.id}>"
        await channel.send(start_task_msg)

        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.followup.send("請去任務佈告欄查看！", ephemeral=True)

        return

