import discord
import schedule
import asyncio
import datetime

from bot.config import config
from bot.utils.message_tracker import (
    save_greeting_message_record,
    load_greeting_message_records,
    load_control_panel_records,
    load_quiz_message_records,
    load_task_entry_records
)
from bot.views.control_panel import ControlPanelView
from bot.views.task_select_view import TaskSelectView
from bot.views.optin_class import OptinClassView
from bot.views.quiz import QuizView

async def run_scheduler():
    while True:
        schedule.run_pending()
        await asyncio.sleep(10)

def scheduled_job(client):
    today = datetime.datetime.now()

    # Daily job
    asyncio.create_task(daily_job(client))

async def daily_job(client):
    client.logger.debug('Running job now...')

    target_channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if target_channel is None or not isinstance(target_channel, discord.TextChannel):
        raise Exception('Invalid channel')

    student_list = await client.api_utils.get_all_students_mission_notifications()
    for user_id in student_list:
        try:
            couser_info = student_list[user_id].get('todays_course', {})
            if couser_info and couser_info['mission_status'] != 'Completed':
                mission_id = couser_info['mission_id']
                await target_channel.send(f"START_MISSION_{mission_id} <@{user_id}>")
            await asyncio.sleep(2)
        except Exception as e:
            client.logger.error(f"Failed to send control panel to user: {user_id}, {str(e)}")

async def handle_greeting_job(client, user_id = None):
    hello_message = (
        "🐾 欸～新手爸媽們！我是加一，你的「寶寶照護教室」導師！\n\n"
        "照顧寶寶是不是覺得像進入新手村？\n"
        "別怕，有我罩你！💪 交給我，穩穩的！😆 \n"
        "奶瓶怎麼選？尿布怎麼換？寶寶半夜哭鬧怎麼辦？\n"
        "專屬課程手把手帶你\n"
        "讓你穩穩當當晉升帶娃高手！🍼\n\n"
        "📣 有問題？盡管問！ 課堂直接解答，別再半夜上網查到懷疑人生～📲\n"
        "新手爸媽，不用怕，你肯定行！ 加一帶你穩穩走～💪\n"
        "📌 快來看看課程重點，直接登記加入！ 🌟\n"
        "四個月大以上的寶寶也可以登記喔！"
    )

    if user_id == None:
        student_list = await client.api_utils.fetch_student_list()
    else:
        student_list = [{'discord_id': user_id}]

    # start greeting
    client.logger.info(f"Start greeting job: {len(student_list)} student")
    for user in student_list:
        files = [
            discord.File("bot/resource/mission_bot_1.png"),
            discord.File("bot/resource/mission_bot_2.png"),
            discord.File("bot/resource/mission_bot_3.png"),
            discord.File("bot/resource/mission_bot_4.png")
        ]
        user_id = user['discord_id']
        user = await client.fetch_user(user_id)
        view = OptinClassView(client, user_id)
        view.message = await user.send(hello_message, view=view, files=files)
        client.logger.info(f"Send hello message to user {user_id}")

        save_greeting_message_record(str(user_id), str(view.message.id))
        await client.api_utils.store_message(user_id, 'assistant', hello_message)

        await asyncio.sleep(5)

    return

async def load_messages(client):
    await load_greeting_message(client)
    client.logger.info("Finished loading greeting messages")

    await load_control_panel_message(client)
    client.logger.info("Finished loading control panel messages")

    await load_task_entry_messages(client)
    client.logger.info("Finished loading task entry messages")

    await load_quiz_message(client)
    client.logger.info("Finished loading quiz messages")

    return

async def load_greeting_message(client):
    records = load_greeting_message_records()
    for user_id, message_id in records.items():
        channel = await client.fetch_user(user_id)
        try:
            message = await channel.fetch_message(int(message_id))
            view = OptinClassView(client, user_id)
            await message.edit(view=view)
            client.logger.info(f"✅ Restored optin-view for user {user_id}")
        except Exception as e:
            await channel.send("課程邀請已經過期囉，麻煩找管理員處理喔")
            client.logger.warning(f"⚠️ Failed to restore for {user_id}: {e}")

async def load_control_panel_message(client):
    records = load_control_panel_records()
    for user_id, message_id in records.items():
        channel = await client.fetch_user(user_id)
        try:
            message = await channel.fetch_message(int(message_id))
            course_info = await client.api_utils.get_student_mission_notifications_by_id(user_id)
            view = ControlPanelView(client, user_id, course_info)
            embed = discord.Embed(
                title=f"📅 任務佈告欄",
                description=view.embed_content,
                color=discord.Color.blue()
            )
            await message.edit(embed=embed, view=view)
            client.logger.info(f"✅ Restored control-panel for user {user_id}")
        except Exception as e:
            await channel.send("儀表板過期囉！ 輸入\"/任務佈告欄\" 重新呼叫喔！")
            client.logger.warning(f"⚠️ Failed to restore for {user_id}: {e}")

async def load_task_entry_messages(client):
    records = load_task_entry_records()
    for user_id, (message_id, task_type, mission_id) in records.items():
        channel = await client.fetch_user(user_id)
        try:
            message = await channel.fetch_message(int(message_id))
            view = TaskSelectView(client, task_type, mission_id)
            await message.edit(view=view)
            client.logger.info(f"✅ Restore task-entry for user {user_id}")
        except Exception as e:
            await channel.send("任務已過期囉！ 輸入\"/任務佈告欄\" 即可透過儀表板重新解任務喔！")
            client.logger.warning(f"⚠️ Failed to restore task entry for {user_id}: {e}")

async def load_quiz_message(client):
    records = load_quiz_message_records()
    for user_id, (message_id, mission_id, current_round, correct_cnt) in records.items():
        channel = await client.fetch_user(user_id)
        try:
            mission = await client.api_utils.get_mission_info(mission_id)
            student_mission_info = {
                **mission,
                'user_id': user_id,
                'assistant_id': config.MISSION_BOT_ASSISTANT,
                'mission_id': mission_id,
                'current_step': 3,
                'score': correct_cnt / 5.0,
            }
            await client.api_utils.update_student_mission_status(**student_mission_info)

            message = await channel.fetch_message(int(message_id))
            view = QuizView(client, mission_id, current_round, correct_cnt, student_mission_info)
            await message.edit(view=view)
            client.logger.info(f"✅ Restored quiz for user {user_id}")
        except Exception as e:
            await channel.send("⏰挑戰時間已到！下次再努力喔\n輸入\"/任務佈告欄\" 即可透過儀表板重新解任務喔！")
            client.logger.warning(f"⚠️ Failed to restore quiz for {user_id}: {e}")

async def send_reward_and_log(client, user_id, mission_id, reward):
    target_channel = await client.fetch_user(user_id)
    is_photo_mission = mission_id in config.photo_mission_list

    # Send the ending message to the user
    ending_msg = (
        "🎉 恭喜你完成今日任務！\n\n"
        "🎁 你獲得了以下獎勵：\n"
        f"> 🪙 金幣 Coin：+{reward}\n"
    )
    if is_photo_mission:
        mission = await client.api_utils.get_mission_info(int(mission_id))
        ending_msg += f"> 🧩 回憶碎片：1 片《{mission['photo_mission']}》\n"

    await target_channel.send(ending_msg)
    await client.api_utils.store_message(user_id, 'assistant', ending_msg)

    # Add gold to user
    await client.api_utils.add_gold(
        user_id,
        gold=int(reward)
    )

    # Send log to Background channel
    channel = client.get_channel(config.BACKGROUND_LOG_CHANNEL_ID)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise Exception('Invalid channel')

    msg_task = f"MISSION_{mission_id}_FINISHED <@{user_id}>"
    await channel.send(msg_task)

def get_user_id(source: discord.Interaction | discord.Message) -> str:
    if isinstance(source, discord.Interaction):
        return str(source.user.id)
    else:
        return str(source.author.id)
