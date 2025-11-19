import discord
from bot.config import config

BUCKETS = [
    ("1–12 個月", "1-12"),
    ("13–24 個月", "13-24"),
    ("25–36 個月", "25-36"),
]

def months_in_bucket(bucket_code: str) -> list[int]:
    if bucket_code == "1-12":
        return list(range(1, 13))      # 1~12
    if bucket_code == "13-24":
        return list(range(13, 25))     # 13~24
    if bucket_code == "25-36":
        return list(range(25, 37))     # 25~36
    return []

def calculate_spacer(label_text: str, max_spaces: int = 40) -> str:
    label_text_length = sum(2 if '\u4e00' <= char <= '\u9fff' else 1 for char in label_text)
    spaces = max_spaces - label_text_length - 1
    return '\u2000' * max(1, spaces)

def setup_label(mission):
    title = f"{mission['mission_title']}"
    if mission['mission_status'] == 'Completed':
        title += " ✅"
    return f"{title}"

class KnowledgeMenuView(discord.ui.View):
    TYPE_LABEL = {
        "care": "里程碑",
        "growth": "成長週報",
    }

    def __init__(self, client, timeout: float = 3600):
        super().__init__(timeout=timeout)
        self.client = client
        self.bucket_code: str | None = None      # "1-12" / "13-24" / "25-36"
        self.selected_month: int | None = None   # 1 ~ 36
        self.knowledge_type: str | None = None   # "care" / "growth"
        self.build_level1()                      # 先選年齡區間

    # 小工具
    def clear_items(self):
        for c in list(self.children):
            self.remove_item(c)

    async def update_view(self, itx: discord.Interaction):
        await itx.response.edit_message(view=self)

    # Level 1：選年齡區間
    def build_level1(self):
        self.clear_items()
        self.bucket_code = None
        self.selected_month = None
        self.knowledge_type = None

        for label, code in BUCKETS:
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
            )

            async def bucket_cb(itx: discord.Interaction, c=code):
                self.bucket_code = c
                self.build_level2_months()
                await self.update_view(itx)

            btn.callback = bucket_cb
            self.add_item(btn)

    # Level 2：選月份（1月~12月 / 13~24 / 25~36）
    def build_level2_months(self):
        self.clear_items()

        current_row = 0
        months = months_in_bucket(self.bucket_code)
        for idx, month in enumerate(months):
            row = (idx // 3)
            btn = discord.ui.Button(
                label=f"{month}月",
                style=discord.ButtonStyle.primary,
                row=row,
            )
            current_row = row

            async def month_cb(itx: discord.Interaction, mv=month):
                self.selected_month = mv
                self.build_level3_type()
                await self.update_view(itx)

            btn.callback = month_cb
            self.add_item(btn)
        
        # 返回到年齡區間
        back = discord.ui.Button(
            label="返回年齡區間",
            style=discord.ButtonStyle.secondary,
            row=current_row + 1,
        )

        async def back_cb(itx: discord.Interaction):
            self.build_level1()
            await self.update_view(itx)

        back.callback = back_cb
        self.add_item(back)

    # Level 3：選知識類型（五大照護 / 成長週報）
    def build_level3_type(self):
        self.clear_items()

        type_buttons = [
            ("五大照護里程碑", "care"),
            ("成長週報", "growth"),
        ]

        for label, code in type_buttons:            
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
            )

            async def type_cb(itx: discord.Interaction, t=code, lbl=label):
                self.knowledge_type = t
                await self.handle_type_click(itx, t)

            btn.callback = type_cb
            self.add_item(btn)

        # 返回到月份選擇
        back = discord.ui.Button(
            label="返回月份選擇",
            style=discord.ButtonStyle.secondary,
        )

        async def back_cb(itx: discord.Interaction):
            self.build_level2_months()
            await self.update_view(itx)

        back.callback = back_cb
        self.add_item(back)

    # 最後一步：依「月齡 + 類型」呼叫 API，送出里程碑 dropdown
    async def handle_type_click(self, itx: discord.Interaction, knowledge_type: str):
        user_id = str(itx.user.id)
        month_val = self.selected_month
        type_label = self.TYPE_LABEL.get(knowledge_type, "內容")

        knowledge_list = await self.client.api_utils.get_student_milestones(
            user_id,
            month_id=month_val,
            query_type=self.TYPE_LABEL.get(knowledge_type, None),
        )

        view = discord.ui.View()
        view.add_item(KnowledgePostSelect(self.client, user_id, knowledge_list))

        embed = discord.Embed(
            title=f"📚 {month_val}個月的{type_label}",
            description="請從下拉選單中選擇想查看的內容：\n\n🔒 **專屬內容提示**\n> 部分內容僅提供已購買繪本的家長查看喔！",
            color=0xeeb2da,
        )

        await itx.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True,
        )

class KnowledgePostSelect(discord.ui.Select):
    def __init__(self, client, user_id, knowledge_list):
        options = []
        for mission in knowledge_list:
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
                    label=mission['mission_title'],
                    description=description,
                    value=f"{mission_id}_{mission_available}"
                )
            )

        mission = knowledge_list[0]
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
