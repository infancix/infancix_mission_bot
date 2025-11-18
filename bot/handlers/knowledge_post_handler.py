import discord
from datetime import datetime, date

from bot.views.task_select_view import TaskSelectView
from bot.utils.message_tracker import (
    save_task_entry_record,
)
from bot.utils.drive_file_utils import create_file_from_url, create_preview_image_from_url
from bot.config import config

async def handle_knowledge_post_start(client, user_id, mission_id):
    user_id = str(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)

    # Prepare next mission
    knowledge_type = '里程碑' if '里程碑' in mission.get('mission_type', '') else '成長週報'
    knowledge_list = await client.api_utils.get_student_milestones(
        user_id,
        query_type=knowledge_type,
        query_min_notification_day=mission['notification_day']
    )

    next_mission_id = None
    for m in knowledge_list:
        if m['notification_day'] > mission['notification_day'] and m['mission_id'] != mission_id:
            next_mission_id = m['mission_id']
            break

    mission_result = {
        **mission,
        'next_mission_id': next_mission_id
    }

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    embed, files = await build_post_embed(mission)
    if next_mission_id is None:
        if files:
            await user.send(files=files)
        else:
            await user.send(embed=embed)
    else:
        view = TaskSelectView(client, "go_next_post", mission_id, mission_result)
        if files:
            view.message = await user.send(view=view, files=files)
        else:
            view.message = await user.send(embed=embed, view=view)
        save_task_entry_record(user_id, str(view.message.id), "go_next_post", mission_id, mission_result)
        return

# -------------------- Helper Functions --------------------
async def build_post_embed(mission_info=None):
    video_url = mission_info.get('mission_video_contents', '').strip()
    image_url = mission_info.get('mission_image_contents', '').strip()
    instruction = ""
    if video_url and image_url:
        instruction = f"▶️ [教學影片]({video_url})\u2003\u2003📂 [圖文懶人包]({image_url})\n"
    elif video_url:
        instruction = f"▶️ [教學影片]({video_url})\n"

    embed = discord.Embed(
        title=f"🧠 **{mission_info['mission_title']}**",
        description=(
            f"{mission_info['mission_instruction']}\n\n"
            f"{instruction}\n"
        ),
        color=0xeeb2da
    )
    embed.set_footer(
        text=f"{mission_info['mission_type']} | 用科學育兒，用愛紀錄成長"
    )

    files = []
    if '成長週報' in mission_info['mission_type']:
        for url in mission_info['mission_image_contents'].split(','):
            if url.strip():
                file = await create_file_from_url(url.strip())
                if file:
                    files.append(file)

    return embed, files
