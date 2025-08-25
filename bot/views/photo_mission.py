import discord
from types import SimpleNamespace

from bot.config import config

class PhotoTaskSelectView(discord.ui.View):
    def __init__(self, client, user_id, incomplete_photo_tasks, timeout=3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.incomplete_photo_tasks = incomplete_photo_tasks
        
        self.items_per_page = 24
        self.setup_records()
        self.page = 0

        self.setup_select_options()
        if self.needs_pagination:
            self.update_buttons()

    def setup_records(self):
        self.sorted_tasks = sorted(self.incomplete_photo_tasks, key=lambda x: (x['book_id'], x['notification_day']))
        self.total_tasks = len(self.sorted_tasks)
        self.needs_pagination = self.total_tasks > self.items_per_page
        self.total_pages = (self.total_tasks - 1) // self.items_per_page + 1 if self.total_tasks > 0 else 1

    def setup_select_options(self):
        # Remove current buttons
        for item in self.children[:]:
            if isinstance(item, PhotoTaskSelect):
                self.remove_item(item)

        start_idx = self.page * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, self.total_tasks)
        current_page_records = self.sorted_tasks[start_idx:end_idx]

        self.add_item(PhotoTaskSelect(self.client, self.user_id, current_page_records))

    def update_buttons(self):
        # Remove current buttons
        for item in self.children[:]:
            if isinstance(item, (PreviousButton, NextButton, PageIndicator)):
                self.remove_item(item)

        self.add_item(PreviousButton(self.page > 0))
        self.add_item(PageIndicator(self.page, self.sorted_tasks))
        self.add_item(NextButton(self.page < self.total_pages - 1))

class PhotoTaskSelect(discord.ui.Select):
    def __init__(self, client, user_id, incomplete_missions):
        options = []
        for mission in incomplete_missions:
            if int(mission['mission_id']) < 7000:
                options.append(discord.SelectOption(
                    label=f"📷{mission['mission_title']}",
                    description=mission['photo_mission'],
                    value=mission['mission_id']
                ))
            else:
                options.append(discord.SelectOption(
                    label=f"📷{mission['mission_title'].replace("_封面", "")}",
                    description=mission['mission_type'],
                    value=mission['mission_id']
                ))

        super().__init__(
            placeholder="繪本任務",
            min_values=1,
            max_values=1,
            options=options
        )

        self.client = client
        self.user_id = str(user_id)

    async def callback(self, interaction: discord.Interaction):
        selected_mission_id = int(self.values[0])

        # Stop View to prevent duplicate interactions
        self.view.stop()
        await interaction.response.edit_message(view=None)

        if selected_mission_id <= 1008 or self.user_id in config.ADMIN_USER_IDS:
            if selected_mission_id in config.theme_mission_list:
                from bot.handlers.theme_mission_handler import handle_theme_mission_start
                await handle_theme_mission_start(self.client, self.user_id, selected_mission_id)
            else:
                from bot.handlers.photo_mission_handler import handle_photo_mission_start
                await handle_photo_mission_start(self.client, self.user_id, selected_mission_id, send_weekly_report=0)
        else:
            await interaction.response.send_message("您尚未購買此繪本，請聯絡社群客服「阿福 <@1272828469469904937>」。", ephemeral=True)

class PreviousButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="⬅上一頁",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.page -= 1
        view.setup_select_options()
        view.update_buttons()
        await interaction.response.edit_message(view=view)

class NextButton(discord.ui.Button):
    def __init__(self, enabled=True):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="下一頁⮕",
            disabled=not enabled,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        view.page += 1
        view.setup_select_options()
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