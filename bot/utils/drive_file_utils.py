import re
from io import BytesIO
from pathlib import Path
import aiohttp
import discord

def extract_google_drive_file_id(url):
    patterns = [
        r'/d/([a-zA-Z0-9-_]+)',  # https://drive.google.com/file/d/FILE_ID/view
        r'id=([a-zA-Z0-9-_]+)',   # https://drive.google.com/open?id=FILE_ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None

def get_google_drive_download_url(file_id):
    """Convert Google Drive file ID to direct download URL"""
    return f"https://drive.google.com/uc?export=download&id={file_id}"

def get_google_drive_preview_image_url(file_id):
    return f"https://drive.google.com/uc?export=view&id={file_id}"

def create_preview_image_from_url(url):
    file_id = extract_google_drive_file_id(url)
    if not file_id:
        return None
    return get_google_drive_preview_image_url(file_id)

async def create_file_from_url(url, cache_dir="cache"):
    file_id = extract_google_drive_file_id(url)
    if not file_id:
        return None
    
    cache_path = Path(cache_dir)
    cache_path.mkdir(exist_ok=True)
    cached_file_path = cache_path / f"{file_id}.png"
    if cached_file_path.exists():
        return discord.File(cached_file_path, filename=cached_file_path.name)

    async with aiohttp.ClientSession() as session:
        async with session.get(get_google_drive_download_url(file_id)) as response:
            if response.status == 200:
                data = await response.read()
                with open(cached_file_path, 'wb') as f:
                    f.write(data)
                return discord.File(BytesIO(data), filename=cached_file_path.name)
    return None
