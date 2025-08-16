import os
import json
from datetime import datetime, timedelta

gender_map = {
    'f': '女孩',
    'm': '男孩'
}

def get_western_zodiac(birthday, lang_version='zh') -> str:
    """
    Get the Western zodiac sign based on the birth date.
    :param birthday: Baby's birthday in 'YYYY-MM-DD' format.
    :return: Western zodiac sign as a string.
    """
    if lang_version == 'zh':
        western_zodiac = [
            ("摩羯座", (1, 20)), ("水瓶座", (2, 19)), ("雙魚座", (3, 20)), ("白羊座", (4, 20)),
            ("金牛座", (5, 21)), ("雙子座", (6, 21)), ("巨蟹座", (7, 22)), ("獅子座", (8, 22)),
            ("處女座", (9, 23)), ("天秤座", (10, 23)), ("天蠍座", (11, 22)), ("射手座", (12, 21)),
            ("摩羯座", (12, 31))  # Capricorn spans into January
        ]
    else: # Assuming English as the default language
        western_zodiac = [
            ("Capricorn", (1, 20)), ("Aquarius", (2, 19)), ("Pisces", (3, 20)), ("Aries", (4, 20)),
            ("Taurus", (5, 21)), ("Gemini", (6, 21)), ("Cancer", (7, 22)), ("Leo", (8, 22)),
            ("Virgo", (9, 23)), ("Libra", (10, 23)), ("Scorpio", (11, 22)), ("Sagittarius", (12, 21)),
            ("Capricorn", (12, 31))  # Capricorn spans into January
        ]
    birth_date = datetime.strptime(birthday, "%Y-%m-%d")
    for zodiac, (month, day) in western_zodiac:
        if (birth_date.month == month and birth_date.day <= day) or (birth_date.month == month - 1 and birth_date.day > day):
            return zodiac
    return None

def get_baby_intro(baby_name, gender, birthday, lang_version='zh'):
    with open(os.path.join('bot', 'resource', f'baby_intro_{lang_version}.json'), 'r', encoding='utf-8') as file:
        baby_intro = json.load(file)

    gender = gender_map[gender]
    if lang_version == 'en':
        gender = 'Girl' if gender == '女孩' else 'Boy'
    zodiac_sign = get_western_zodiac(birthday, lang_version)
    if zodiac_sign in baby_intro.get(gender, {}):
        intro = baby_intro[gender][zodiac_sign]
    else:
        intro = baby_intro[gender]['default']

    birthday = datetime.strptime(birthday, "%Y-%m-%d")
    if lang_version == 'zh':
        formatted_birthday = birthday.strftime("%Y年%m月%d日")
    else:
        formatted_birthday = birthday.strftime("%B %d, %Y")
        formatted_birthday = formatted_birthday.replace(birthday.strftime("%d"), str(int(birthday.strftime("%d"))))

    return intro.format(baby_name=baby_name, birthday=formatted_birthday)

def get_family_intro(mission_id, relation, lang_version='zh'):
    with open(os.path.join('bot', 'resource', f'family_intro_{lang_version}.json'), 'r', encoding='utf-8') as file:
        family_intro = json.load(file)

    mission_id = str(mission_id)
    if relation in family_intro.get(mission_id, {}):
        return family_intro[mission_id][relation]
    else:
        return family_intro[mission_id]['其它稱謂']
