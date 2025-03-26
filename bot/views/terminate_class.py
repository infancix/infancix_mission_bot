import discord
from bot.config import config
from bot.views.control_panel import ControlPanelView

class TerminateClassView(discord.ui.View):
    def __init__(self, client, student_mission_info, reward=20, timeout=86400):
        super().__init__(timeout=timeout)
        self.client = client
        self.student_mission_info = student_mission_info
        self.user_id = self.student_mission_info['user_id']
        self.mission_id = self.student_mission_info['mission_id']
        self.terminate_button = TerminateButton(client, student_mission_info, reward, label='結束課程', msg='課程完成！期待下次見！')
        self.add_item(self.terminate_button)
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        if self.message:
            try:
                await self.message.edit(view=self)
                print("✅ 按鈕已自動 disable")
            except discord.NotFound:
                print("❌ 訊息已刪除，無法更新")

        self.stop()

class TerminateButton(discord.ui.Button):
    def __init__(
        self, client, student_mission_info, reward, label, msg, style=discord.ButtonStyle.secondary
    ):
        super().__init__(label=label, style=style)
        self.client = client
        self.student_mission_info = student_mission_info
        self.reward = reward
        self.msg = msg

    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        self.disabled = True
        if interaction.message is None:
            return

        # Send the ending message to the user
        await interaction.message.edit(view=self.view)
        await interaction.response.send_message(self.msg)
        await self.client.api_utils.add_gold(
            user_id,
            gold=self.reward
        )
        await self.client.api_utils.send_dm_message(
            user_id,
            f"🎉 恭喜完成 {self.student_mission_info['mission_type']} - {self.student_mission_info['mission_title']}\n獲得🪙{self.reward}金幣🎉\n"
        )

        # Send ending message to 背景紀錄
        channel = self.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            raise Exception('Invalid channel')
        msg_task = f"MISSION_{self.student_mission_info['mission_id']}_FINISHED <@{user_id}>"
        await channel.send(msg_task)

        course_info = await self.client.api_utils.get_student_mission_notifications_by_id(user_id)
        control_panel_view = ControlPanelView(self.client, user_id, course_info)
        embed = discord.Embed(
            title=f"📅 照護課表",
            description=control_panel_view.embed_content,
            color=discord.Color.blue()
        )
        message = await interaction.channel.send(embed=embed, view=control_panel_view)
        await self.client.api_utils.store_message(user_id, 'assistant', control_panel_view.embed_content, message_id=message.id)


