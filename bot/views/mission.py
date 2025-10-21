import discord

from bot.config import config

def calculate_spacer(label_text: str, max_spaces: int = 40) -> str:
    label_text_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in label_text)
    spaces = max_spaces - label_text_length - 1
    return '\u2000' * max(1, spaces)

def setup_label(mission):
    title = ""
    if int(mission['mission_id']) in config.photo_mission_list:
        title += "📸"
    elif int(mission['mission_id']) in config.audio_mission:
        title += "🔊"
    elif int(mission['mission_id']) in config.questionnaire_mission:
        title += "📝"

    title += f"{mission['mission_title']}"
    if mission['mission_status'] == 'Completed':
        title += " ✅"

    return f"{title}"

class MilestoneSelectView(discord.ui.View):
    def __init__(self, client, user_id, student_milestones, timeout=3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.student_milestones = student_milestones['milestones']
        self.current_page = int(student_milestones['current_stage'])
        self.total_pages = 3

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

class PreviousYearButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="⬅上一個年份",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page = max(0, view.current_page - 12)
        view.update_select_menu()
        view.update_buttons()
        await interaction.response.edit_message(view=view)

class NextYearButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="下一個年份⮕",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.current_page = min(view.total_pages - 1, view.current_page + 12)
        view.update_select_menu()
        view.update_buttons()
        await interaction.response.edit_message(view=view)

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
        warning = {
            0: "⚠️ 任務尚未開放",
            -1: "⚠️ 寶寶年齡尚未符合要求",
            -2: "⚠️ 尚未購買繪本，請洽官網或是社團客服阿福",
            -3: "⚠️ 繪本已進入送印階段，無法修改"
        }
        options = []
        for mission in student_milestones:
            mission_id = int(mission['mission_id'])
            if mission['mission_available'] == -2:
                continue
            if mission['mission_available'] in warning:
                description = warning[mission['mission_available']]
                mission_available = 0
            else:
                if mission.get('photo_mission') and mission['photo_mission'] and mission['photo_mission'] != "":
                    description = f"{mission['mission_type']} | {mission['photo_mission']}"
                else:
                    description = mission['mission_type']
                mission_available = mission['mission_available']

            options.append(
                discord.SelectOption(
                    label=setup_label(mission),
                    description=description,
                    value=f"{mission_id}_{mission_available}"
                )
            )

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
        selected_mission_id = int(selected_mission.split('_')[0])
        mission_available = int(selected_mission.split('_')[-1])
        mission = await self.client.api_utils.get_mission_info(selected_mission_id)

        self.view.stop()
        await interaction.response.edit_message(content=f"選擇任務: {mission['mission_title']}", view=None)
    
        if not mission_available:
            await interaction.followup.send("任務尚未開放，請稍後再試！", ephemeral=True)
            return

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        start_task_msg = f"START_MISSION_{selected_mission_id} <@{interaction.user.id}>"
        await channel.send(start_task_msg)

        if not isinstance(interaction.channel, discord.DMChannel):
            await interaction.followup.send("請去任務佈告欄查看！", ephemeral=True)

        return

