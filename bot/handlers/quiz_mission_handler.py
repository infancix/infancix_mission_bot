import discord

from bot.views.quiz import QuizView
from bot.views.task_select_view import TaskSelectView
from bot.handlers.utils import get_user_id, send_reward_and_log, add_task_instructions
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
    mission_status = await client.api_utils.get_student_mission_status(user_id, mission_id)

    # Mission start
    student_mission_info = {
        **mission,
        'user_id': user_id,
        'assistant_id': config.get_assistant_id(mission_id),
        'current_step': 1
    }
    await client.api_utils.update_student_mission_status(**student_mission_info)

    task_instructions = f"{mission['mission_type']}\n\n"
    if mission['mission_video_contents'] and mission['mission_video_contents'].strip():
        task_instructions += f"🎥 影片教學\n▶️ [{mission['mission_title']}]({mission['mission_video_contents']})\n\n"

    if mission['mission_image_contents'] and mission['mission_image_contents'].strip():
        task_instructions += f"📖 圖文懶人包\n ▶️"
        for url in mission['mission_image_contents'].strip().split(','):
            task_instructions += f" [點擊]({url})"

    embed = discord.Embed(
        title=f"🎖{mission['mission_title']}🎖",
        description=task_instructions,
        color=discord.Color.blue()
    )
    
    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    view = TaskSelectView(client, "go_quiz", mission_id)
    view.message = await user.send(embed=embed, view=view)
    save_task_entry_record(user_id, str(view.message.id), "go_quiz", mission_id)
    await client.api_utils.store_message(user_id, 'assistant', task_instructions)

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
        color=discord.Color.purple()
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

    quiz_summary = (
        f"--------------------------\n\n"
        f"挑戰結束！🎉 答對 {correct}/{total} 題，"
    )
    if correct >= 2:
        quiz_summary += "恭喜掌握了這堂課的知識！🎓"
    else:
        quiz_summary += "加油！還有一些地方需要加強，別氣餒！"

    await interaction.channel.send(quiz_summary)
    await interaction.client.api_utils.store_message(user_id, 'assistant', quiz_summary)

    student_mission_info['current_step'] = 4
    student_mission_info['score'] = float(correct) / total
    await interaction.client.api_utils.update_student_mission_status(**student_mission_info)
    await send_reward_and_log(interaction.client, user_id, mission_id, 20)

@exception_handler(user_friendly_message="加一暫時無法回答，請稍後再試一次喔！或是管理員協助處理。")
async def handle_class_question(client, message, student_mission_info):
    user_id = get_user_id(message)
    mission_id = student_mission_info['mission_id']

    assistant_id = student_mission_info['assistant_id']
    if student_mission_info.get('thread_id', None):
        thread_id = student_mission_info['thread_id']
    else:
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
