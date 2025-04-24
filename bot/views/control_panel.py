import discord
from types import SimpleNamespace
from datetime import datetime

from bot.config import config
from bot.views.mission import MilestoneSelectView
from bot.views.photo_mission import PhotoTaskSelectView

class ControlPanelView(discord.ui.View):
    def __init__(self, client, user_id, course_info, timeout=None):
        super().__init__(timeout=None)
        self.client = client
        self.user_id = user_id
        self.todays_course = course_info.get('todays_course') if course_info else None
        self.continue_course = course_info.get('incomplete_course') if course_info else None
        self.incomplete_photo_tasks = course_info.get('incomplete_photo_tasks') if course_info else None
        self.embed_content = self.create_control_panel_embed()

        self.button_index = 0
        if self.todays_course and self.todays_course['mission_status'] != 'Completed':
            today_button = discord.ui.Button(
                custom_id='start_today',
                label="📘 開始今日新課程",
                style=discord.ButtonStyle.primary,
                row=self.button_index
            )
            today_button.callback = self.start_today_callback
            self.add_item(today_button)
            self.button_index += 1

        if self.continue_course:
            continue_button = discord.ui.Button(
                custom_id='continue_course',
                label="📖 繼續未完成課程",
                style=discord.ButtonStyle.primary,
                row=self.button_index
            )
            continue_button.callback = self.continue_course_callback
            self.add_item(continue_button)
            self.button_index += 1

        if self.incomplete_photo_tasks:
            photo_button = discord.ui.Button(
                custom_id='photo_task',
                label="🧩 回憶碎片",
                style=discord.ButtonStyle.success,
                row=self.button_index
            )
            photo_button.callback = self.photo_task_callback
            self.add_item(photo_button)
            self.button_index += 1

        milestone_button = discord.ui.Button(
            custom_id='milestones',
            label='🏆 檢視任務完成進度',
            style=discord.ButtonStyle.secondary,
            row=self.button_index
        )
        milestone_button.callback = self.milestones_callback
        self.add_item(milestone_button)
        self.button_index += 1

    def create_control_panel_embed(self):
        today = datetime.now().strftime('%Y-%m-%d')
        embed_content = []
        embed_content.append(f"✨ 今天是 **{today}**，歡迎回來！\n")

        if self.todays_course:
            if self.todays_course['mission_status'] == 'Completed':
                embed_content.append(f"📘 **今日新課程**: 恭喜你已完成🎉\n")
            elif self.todays_course['mission_id'] in config.photo_mission_list:
                embed_content.append(f"📘 **今日新課程**：{self.todays_course['mission_title']}\n({self.todays_course['mission_type']})\n💡 今天是特別任務喔，完成可獲得100金幣！\n")
            else:
                embed_content.append(f"📘 **今日新課程**：{self.todays_course['mission_title']}\n({self.todays_course['mission_type']})\n")

        if self.continue_course:
            embed_content.append(f"🎯 **上次未完成課程**：{self.continue_course['mission_title']}\n({self.continue_course['mission_type']})\n")

        return "-------------------\n".join(embed_content)

    async def start_today_callback(self, interaction):
        await interaction.response.defer(ephemeral=True)
        self.todays_course['current_step'] = 0
        await self.start_or_resume_course(self.todays_course)

    async def continue_course_callback(self, interaction):
        await interaction.response.send_message(
            f"繼續進行課程：{self.continue_course['mission_title']}\n",
            ephemeral=True
        )
        await self.start_or_resume_course(self.continue_course)

    async def photo_task_callback(self, interaction):
        if len(self.incomplete_photo_tasks) > 1:
            photo_task_view = PhotoTaskSelectView(self.client, interaction.user.id, self.incomplete_photo_tasks)
            await interaction.response.send_message(
                "🧩 缺失的回憶碎片",
                view=photo_task_view,
                ephemeral=True
            )
        elif len(self.incomplete_photo_tasks) == 1:
            await interaction.response.defer(ephemeral=True)
            from bot.handlers.photo_mission_handler import handle_photo_mission_start
            self.client.logger.info(f"User {interaction.user.id} starts photo mission {self.incomplete_photo_tasks[0]['mission_id']}")
            await handle_photo_mission_start(self.client, interaction.user.id, self.incomplete_photo_tasks[0]['mission_id'])

    async def milestones_callback(self, interaction):
        student_milestones = await self.client.api_utils.get_student_milestones(str(interaction.user.id))
        milestone_view = MilestoneSelectView(self.client, interaction.user.id, student_milestones)
        await interaction.response.send_message(
            "🔍 *以下是您課程進度，按下方按鈕開始課程* 🔍",
            view=milestone_view,
            ephemeral=True
        )

    async def start_or_resume_course(self, course_status):
        mission_id = course_status['mission_id']

        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')

        await channel.send(f"START_MISSION_{mission_id} <@{self.user_id}>")

