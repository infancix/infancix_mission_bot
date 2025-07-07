import discord
from datetime import datetime, date

from bot.utils.decorator import exception_handler
from bot.config import config

async def handle_pregnancy_mission_start(client, user_id, mission_id):
    user_id = str(user_id)
    student_info = await client.api_utils.get_student_profile(user_id)
    mission = await client.api_utils.get_mission_info(mission_id)
    embed = build_pregnancy_embed(mission, student_info)
    
    user = await client.fetch_user(user_id)
    if user.dm_channel is None:
        await user.create_dm()

    await user.send(embed=embed)
    await client.api_utils.store_message(user_id, 'assistant', "Sending pregnancy mission message")

@exception_handler(user_friendly_message="任務處理失敗，請稍後再試一次！或是尋求客服協助喔！")
async def process_message(client, message, student_mission_info):
    user_id = str(message.author.id)
    mission_id = student_mission_info['mission_id']

    # getting assistant reply
    async with message.channel.typing():
        assistant_id = config.get_assistant_id(mission_id)
        thread_id = student_mission_info.get('thread_id', None)
        if thread_id is None:
            thread_id = client.openai_utils.load_thread()
            student_mission_info['thread_id'] = thread_id
        bot_response = client.openai_utils.get_reply_message(assistant_id, thread_id, message.content)
            
    if bot_response.get('is_ready', False) == False:
        await message.channel.send(bot_response['message'])
        await client.api_utils.store_message(user_id, assistant_id, bot_response['message'])
        client.logger.info(f"Assitant response: {bot_response}")
    else:
        await client.api_utils.update_student_profile(
            user_id,
            bot_response.get('student_name', message.author.name),
            bot_response.get('gender', None),
            '懷孕中',
            bot_response['due_date']
        )
        
        msg = "登記完成，孕養報會自動發送給你，請耐心等待！"
        await message.channel.send(msg)
        client.logger.info(f"Pregnancy mission completed for user {user_id} with due date {bot_response['due_date']}")

# -------------------- Helper Functions --------------------
def build_pregnancy_embed(mission_info=None, student_info=None):
    est_due_date = datetime.strptime(student_info['est_due_date'], '%Y-%m-%d').date()
    age = (est_due_date - datetime.now()).days
    week = (280-age) // 7
    embed = discord.Embed(
        title=f"🎉 恭喜寶寶滿 {week} 週啦！",
        description=f"[點我閱讀完整孕養報](mission_info['mission_image_contents'])",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    return embed
