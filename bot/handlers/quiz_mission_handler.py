import discord
from datetime import datetime, date
from dateutil.relativedelta import relativedelta

from bot.views.quiz import QuizView
from bot.views.task_select_view import TaskSelectView
from bot.handlers.utils import get_user_id
from bot.utils.message_tracker import (
    save_quiz_message_record,
    save_task_entry_record
)
from bot.utils.decorator import exception_handler
from bot.config import config

async def handle_quiz_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    baby_info = await client.api_utils.get_baby_profile(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    embed = build_quiz_mission_embed(mission, baby_info)

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'assistant_id': config.get_assistant_id(mission_id),
        'current_step': 1
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    view = TaskSelectView(client, "go_quiz", mission_id)
    view.message = await user.send(embed=embed, view=view)
    save_task_entry_record(user_id, str(view.message.id), "go_quiz", mission_id)

async def handle_quiz_round(client, message, student_mission_info, current_round=0, correct=0):
    user_id = get_user_id(message)
    mission_id = int(student_mission_info['mission_id'])
    student_mission_info['current_step'] = 2
    await client.api_utils.update_student_mission_status(**student_mission_info)

    # Start quiz
    total_rounds = 3
    quiz = client.mission_quiz[str(mission_id)][current_round]
    question = quiz['question'].replace('？', ':grey_question:')
    task_request = f"🌟 **{question}**\n"
    for option in quiz['options']:
        task_request += f"{option['option']}\n"

    embed = discord.Embed(
        title=f"🏆 挑戰任務 - 第 {current_round+1} 題",
        description=task_request,
        color=0xeeb2da
    )

    view = QuizView(client, mission_id, current_round, correct, student_mission_info)
    view.message = await message.channel.send(embed=embed, view=view)

    # save record
    save_quiz_message_record(str(message.author.id), str(view.message.id), mission_id, current_round, correct)
    return

async def send_quiz_summary(interaction, correct, student_mission_info):
    user_id = get_user_id(interaction)
    mission_id = student_mission_info['mission_id']
    total = 3
    reward = 20

    quiz_summary = (
        f"🎉 答對 {correct}/{total} 題\n\n"
        f"你獲得獎勵：🪙 金幣 Coin：+{reward}\n"
    )

    embed = discord.Embed(
        title="💫 挑戰結束",
        description=quiz_summary,
        color=0xeeb2da
    )

    await interaction.channel.send(embed=embed)
    await interaction.client.api_utils.store_message(user_id, 'assistant', quiz_summary)
    await interaction.client.api_utils.add_gold(user_id, gold=int(reward))

    student_mission_info['current_step'] = 4
    student_mission_info['score'] = float(correct) / total
    await interaction.client.api_utils.update_student_mission_status(**student_mission_info)

    # Send log to Background channel
    channel = interaction.client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise Exception('Invalid channel')

    msg_task = f"MISSION_{mission_id}_FINISHED <@{user_id}>"
    await channel.send(msg_task)

@exception_handler(user_friendly_message="加一暫時無法回答，請稍後再試一次喔！或是管理員協助處理。")
async def handle_class_question(client, message, student_mission_info):
    user_id = get_user_id(message)
    mission_id = student_mission_info['mission_id']

    assistant_id = student_mission_info.get('assistant_id', None)
    thread_id = student_mission_info.get('thread_id', None)
    if assistant_id is None or thread_id is None:
        assistant_id = config.get_assistant_id(mission_id)
        # create a new thread and add task-instructions
        thread_id = client.openai_utils.load_thread()
        student_mission_info['thread_id'] = thread_id
        await client.api_utils.update_student_mission_status(**student_mission_info)

        mission = await client.api_utils.get_mission_info(mission_id)
        add_task_instructions(client, mission, thread_id)

    async with message.channel.typing():
        response = await client.openai_utils.get_reply_message(assistant_id, thread_id, message.content)
        client.logger.info(f"Assitant response: {response}")

    if student_mission_info['current_step'] < 4:
        view = TaskSelectView(client, "go_quiz", mission_id)
        view.message = await message.channel.send(response['message'], view=view)
        save_task_entry_record(user_id, str(view.message.id), "go_quiz", mission_id)
    else:
        await message.channel.send(response['message'])

    await client.api_utils.store_message(user_id, 'assistant', response['message'])

# -------------------- Helper Functions --------------------
def build_quiz_mission_embed(mission_info=None, baby_info=None):
    # Prepare description based on style
    birthday = datetime.strptime(baby_info['birthdate'], '%Y-%m-%d').date()
    diff = relativedelta(date.today(), birthday)
    year = diff.years
    months = diff.months
    days = diff.days
    if year > 0:
        author = f"🧸今天{baby_info['baby_name']} 出生滿 {year} 年 {months} 個月 {days} 天"
    elif months > 0:
        author = f"🧸今天{baby_info['baby_name']} 出生滿 {months} 個月 {days} 天"
    else:
        author = f"🧸今天{baby_info['baby_name']} 出生滿 {days} 天"

    video_url = mission_info.get('mission_video_contents', '').strip()
    image_url = mission_info.get('mission_image_contents', '').strip()
    instruction = ""
    if video_url and image_url:
        instruction = f"▶️ [教學影片]({video_url})\u2003\u2003📂 [圖文懶人包]({image_url})\n"
    elif video_url:
        instruction = f"▶️ [教學影片]({video_url})\n"

    desc = (
        f"{mission_info['mission_instruction']}\n\n"
        f"{instruction}\n"
    )
    embed = discord.Embed(
        title=mission_info['mission_title'],
        description=desc,
        color=0xeeb2da
    )
    embed.set_author(name=author)
    embed.set_footer(
        icon_url="https://infancixbaby120.com/discord_assets/baby120_footer_logo.png",
        text="點選下方 `指令` 可查看更多功能"
    )
    return embed

def add_task_instructions(client, mission, thread_id):
    mission_instructions = f"""
        這是這次課程的主題和課程影片字幕：
        ## 課程內容：{mission['mission_title']}
        ## 影片字幕: {mission['transcription']}
    """
    client.openai_utils.add_task_instruction(thread_id, mission_instructions)
