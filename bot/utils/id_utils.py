def to_base36(num):
    """轉換數字為 36 進制字串"""
    if num == 0:
        return '0'
    alphabet = '0123456789abcdefghijklmnopqrstuvwxyz'
    result = ''
    while num > 0:
        result = alphabet[num % 36] + result
        num //= 36
    return result

def encode_ids(baby_id, book_id):
    """將 baby_id 和 book_id 編碼成 code"""
    num = int(baby_id) * 10000 + int(book_id)
    return to_base36(num)
