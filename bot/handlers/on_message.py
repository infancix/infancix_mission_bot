import re

import discord

from bot.config import config
from bot.utils.utils import fetch_student_list
from bot.handlers.utils import handle_start_mission, handle_dm

async def dispatch_message(client, message):
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
                if mission_id == 1:
                    await handle_greeting_job(client, user_id)
                await handle_start_mission(client, user_id, mission_id)
            return
        else:
            return

    if isinstance(message.channel, discord.channel.DMChannel):
        await handle_dm(client, message)

async def handle_greeting_job(client, user_id = None):
    hello_message = (
        "🐾 欸～哈囉，爸媽們，我是加一，你的「寶寶照護教室」導師，咱們今天一起穩穩的～ 💪\n\n"
        "🍼 我是這麼幫你的：\n\n"
        "量身打造：根據寶寶的日齡，給你最合適的養育方法，不多不少，剛剛好～\n\n"
        "新手專屬：從換尿布到拍嗝，每一步都手把手教，這些事真的沒那麼難！\n\n"
        "安心陪伴：別怕手忙腳亂，跟著我就行！咱們不追求完美，只求越做越好。\n\n"
        "🐾 加一碎嘴：有啥不懂的記得問我，我知道你們忙，我來讓一切簡單點！\n\n"
        "🌟 第一堂課馬上開始，交給我穩穩的～"
    )

    if user_id == None:
        student_list = await fetch_student_list()
    else:
        student_list = [{'discord_id': user_id}]

    # start greeting
    client.logger.info(f"Start greeting job: {len(student_list)} student")
    for user in student_list:
        user_id = user['discord_id']
        user_discord_client = await client.fetch_user(user_id)
        await user_discord_client.send(hello_message)
        client.logger.info(f"Send hello message to user {user_id}")
    return

