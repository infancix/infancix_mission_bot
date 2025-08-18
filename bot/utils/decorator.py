import functools
import traceback

def exception_handler(user_friendly_message="操作失敗，請稍後再試一次"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            client = args[0]  # 預設第一個參數是 client
            message = args[1] # 預設第二個是 Discord message
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                prefix = f"Exception in {func.__name__}"
                error_traceback = traceback.format_exc()
                client.logger.error(f"{prefix}: {str(e)}\n{error_traceback}")
                await message.channel.send(user_friendly_message)
        return wrapper
    return decorator
