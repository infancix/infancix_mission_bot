import discord
from bot.config import config
from bot.views.control_panel import ControlPanelView
from bot.utils.message_tracker import delete_greeting_message_record, save_control_panel_record

class OptinClassView(discord.ui.View):
    def __init__(self, client, user_id, timeout=None):
        super().__init__(timeout=timeout)
        self.client = client
        self.user_id = user_id
        self.optin_button = OptinClassButton(client, user_id, label="登記課程")
        self.add_item(self.optin_button)
        self.message = None

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(content="課程邀請已經過期囉，麻煩找管理員處理喔", view=self)
                print("✅ 按鈕已自動 disable")
            except discord.NotFound:
                print("❌ 訊息已刪除，無法更新")

        self.stop()

class OptinClassButton(discord.ui.Button):
    def __init__(
        self, client, user_id, label, style=discord.ButtonStyle.secondary
    ):
        super().__init__(label=label, style=style)
        self.client = client
        self.user_id = str(user_id)

    async def callback(self, interaction: discord.Interaction):
        # Disable the button to prevent duplicate interactions
        self.disabled = True
        if interaction.message is None:
            return
        await interaction.message.edit(view=self.view)
        delete_greeting_message_record(self.user_id)

        # Ensure we provide an immediate response to the interaction
        await interaction.response.defer()  # Indicates processing is ongoing

        # Perform the backend logic
        await self.client.api_utils.optin_class(self.user_id)

        # Determine the message to send based on the student status
        student_status = await self.client.api_utils.check_student_mission_eligible(self.user_id)
        if student_status == "over_31_days":
            msg = "感謝登記，請交給我🐾"
        elif student_status == "pregnancy_or_newborn_stage":
            msg = "感謝登記，咱們在寶寶滿月後見啦！"
        else:
            msg = "請先到會員專區登記寶寶資料/或是預產期喔"

        # Send the final message to the user
        await interaction.user.send(msg)
        await self.client.api_utils.store_message(self.user_id, 'assistant', msg)

        if student_status == "over_31_days":
            course_info = await self.client.api_utils.get_student_mission_notifications_by_id(self.user_id)
            control_panel_view = ControlPanelView(self.client, self.user_id, course_info)
            embed = discord.Embed(
                title=f"📅 任務里程碑",
                description=control_panel_view.embed_content,
                color=discord.Color.blue()
            )
            message = await interaction.user.send(embed=embed, view=control_panel_view)
            save_control_panel_record(self.user_id, str(message.id))
            await self.client.api_utils.store_message(self.user_id, 'assistant', control_panel_view.embed_content, message_id=message.id)


