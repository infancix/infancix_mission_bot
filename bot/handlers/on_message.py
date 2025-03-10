import re
import discord
from discord.ui import View

from bot.config import config
from bot.handlers.record_mission_handler import handle_record_mission_start, handle_record_mission_dm
from bot.handlers.video_mission_handler import handle_video_mission_start, handle_video_mission_dm
from bot.views.optin_class import OptinClassView

async def handle_dm(client, message):
    if (
        message.author == client.user
        and message.channel.id != config.BACKGROUND_LOG_CHANNEL_ID
    ):
        return

    if message.channel.id == config.BACKGROUND_LOG_CHANNEL_ID:
        if len(message.mentions) == 1 and message.mentions[0].id == config.MISSION_BOT and 'START_GREETING_ALL' in message.content:
            await handle_greeting_job(client)
            return
        elif len(message.mentions) == 2 and message.mentions[0].id == config.MISSION_BOT and 'START_GREETING' in message.content:
            await handle_greeting_job(client, message.mentions[1].id)
            return
        elif len(message.mentions) == 1:
            user_id = message.mentions[0].id
            match = re.search(r'START_MISSION_(\d+)', message.content)
            if match:
                mission_id = int(match.group(1))
                await handle_start_mission(client, user_id, mission_id)
            return
        else:
            return

    if isinstance(message.channel, discord.channel.DMChannel):
        user_id = str(message.author.id)
        student_mission_info = await client.api_utils.get_student_is_in_mission(user_id)
        if not bool(student_mission_info):
            client.api_utils.store_message(str(user_id), 'user', message.content)
            reply_msg = "加一現在不在喔，有問題可以找 <@1287675308388126762>"
            await message.channel.send(reply_msg)
            client.api_utils.store_message(str(user_id), 'assistant', reply_msg)
        else:
            student_mission_info['mission_id'] = int(student_mission_info['mission_id'])
            if student_mission_info['mission_id'] in config.record_mission_list:
                await handle_record_mission_dm(client, message, student_mission_info)
            else:
                await handle_video_mission_dm(client, message, student_mission_info)
        return

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

    files = [
        discord.File("bot/resource/mission_bot_1.png"),
        discord.File("bot/resource/mission_bot_2.png"),
        discord.File("bot/resource/mission_bot_3.png"),
        discord.File("bot/resource/mission_bot_4.png")
    ]

    if user_id == None:
        student_list = await client.api_utils.fetch_student_list()
    else:
        student_list = [{'discord_id': user_id}]

    view = OptinClassView(client, user_id)
    # start greeting
    client.logger.info(f"Start greeting job: {len(student_list)} student")
    for user in student_list:
        user_id = user['discord_id']
        user = await client.fetch_user(user_id)
        view.message = await user.send(hello_message, view=view, files=files)
        client.logger.info(f"Send hello message to user {user_id}")
        await client.api_utils.store_message(user_id, 'assistant', hello_message)
    return

async def handle_start_mission(client, user_id, mission_id):
    mission_id = int(mission_id)
    if mission_id in config.record_mission_list:
        await handle_record_mission_start(client, user_id, mission_id)
    else:
        await handle_video_mission_start(client, user_id, mission_id)


