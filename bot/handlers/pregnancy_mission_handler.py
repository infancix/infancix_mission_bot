import discord
from datetime import datetime, date

from bot.views.task_select_view import TaskSelectView
from bot.utils.decorator import exception_handler
from bot.utils.drive_file_utils import create_file_from_url
from bot.utils.message_tracker import save_task_entry_record
from bot.config import config

async def handle_pregnancy_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    mission = await client.api_utils.get_mission_info(mission_id)
    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'current_step': 1
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    if int(mission_id) == config.pregnancy_register_mission:
        embed = get_pregnancy_registration_embed()
        await user.send(embed=embed)
    else:
        student_info = await client.api_utils.get_student_profile(user_id)
        embed = await build_pregnancy_embed(mission, student_info['due_date'])
        if int(mission_id) < 125: # Under week 30
            await user.send(embed=embed)
        else:
            view = TaskSelectView(client, "baby_born", mission_id, timeout=604800) # 7days = 604800 seconds
            view.message = await user.send(embed=embed, view=view)
            save_task_entry_record(user_id, str(view.message.id), "baby_born", mission_id)

        student_mission_info['current_step'] = 4 # end mission
        await client.api_utils.update_student_mission_status(**student_mission_info)

    await client.api_utils.store_message(user_id, 'assistant', "Sending pregnancy mission message")

@exception_handler(user_friendly_message="登記失敗，請稍後再試一次！或是尋求客服協助喔！")
async def process_pregnancy_registrater_message(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = client.openai_utils.load_thread()
            student_mission_info['thread_id'] = thread_id
            await client.api_utils.update_student_mission_status(**student_mission_info)
        mission_result = client.openai_utils.get_reply_message(assistant_id, thread_id, message.content)

    if mission_result.get('is_ready', False) == False:
        await message.channel.send(mission_result['message'])
        await client.api_utils.store_message(user_id, assistant_id, mission_result['message'])
        client.logger.info(f"Assistant response: {mission_result}")
    else:
        await client.api_utils.update_student_profile(
            user_id,
            message.author.name,
            '懷孕中',
            mission_result['due_date']
        )
        # Mission end
        student_mission_info['current_step'] = 4
        await client.api_utils.update_student_mission_status(**student_mission_info)
        
        # Send new mission to user
        mission_id = get_pregnancy_current_mission(mission_result['due_date'])
        if mission_id < 102:
            msg = "登記完成，孕養報會在第 7 周發送給您！"
            await message.channel.send(msg)
        elif mission_id <= 125:
            mission = await client.api_utils.get_mission_info(mission_id)
            embed = await build_pregnancy_embed(mission, mission_result['due_date'])
            await message.channel.send(embed=embed)
            student_mission_info = {
                **mission,
                'user_id': user_id,
                'current_step': 1,
                'total_steps': 1
            }
            await client.api_utils.update_student_mission_status(**student_mission_info)
        elif mission_id <= 135:
            mission = await client.api_utils.get_mission_info(mission_id)
            embed = await build_pregnancy_embed(mission, mission_result['due_date'])
            view = TaskSelectView(client, "baby_born", mission_id, timeout=604800) # 7days = 604800 seconds
            view.message = await message.channel.send(embed=embed, view=view)
            save_task_entry_record(user_id, str(view.message.id), "baby_born", mission_id)
            student_mission_info = {
                **mission,
                'user_id': user_id,
                'current_step': 1,
                'total_steps': 1
            }
            await client.api_utils.update_student_mission_status(**student_mission_info)
        else:
            msg = "登記完成，已經沒有符合週期的孕養報了！"
            view = TaskSelectView(client, "baby_born", mission_id, timeout=604800) # 7days = 604800 seconds
            view.message = await message.channel.send(msg, view=view)
            save_task_entry_record(user_id, str(view.message.id), "baby_born", mission_id)

        client.logger.info(f"Pregnancy mission completed for user {user_id} with due date {mission_result['due_date']}")

# -------------------- Helper Functions --------------------
def get_pregnancy_registration_embed():
    embed = discord.Embed(
        title="📝 請問您的預產期?",
        description="範例: 2025-05-01",
        color=discord.Color.blue()
    )
    return embed

def get_pregnancy_current_mission(due_date_str):
    due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    age = (due_date - date.today()).days
    week = (280 - age) // 7
    mission_id = 102 + (week-7)
    return mission_id

async def build_pregnancy_embed(mission_info, due_date_str):
    due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
    age = (due_date - date.today()).days
    week = (280 - age) // 7
    embed = discord.Embed(
        title=f"🎉 恭喜寶寶滿 {week} 週啦！",
        description=(
            f"📅 距離預產期還有 {age} 天\n"
            f"[👉點我查看孕養報]({mission_info['mission_image_contents']})\n"
        ),
        color=discord.Color.green()
    )
    embed.set_thumbnail(url="https://infancixbaby120.com/discord_assets/logo.png")
    embed.set_footer(text="建議使用手機閱讀孕養報，閱讀體驗最佳！")
    return embed
