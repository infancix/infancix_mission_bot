import os
import re
import aiohttp
from io import BytesIO
from discord import File

def extract_drive_id(url: str) -> str:
    if "drive.google.com" in url:
        parts = url.split("/d/")
        if len(parts) > 1:
            return parts[1].split("/")[0]
    raise ValueError("Invalid Google Drive URL")

async def download_drive_image(url: str, save_dir: str = "cache") -> File:
    file_id = extract_drive_id(url)
    os.makedirs(save_dir, exist_ok=True)
    file_path = os.path.join(save_dir, f"{file_id}.png")

    if os.path.exists(file_path):
        return File(fp=open(file_path, "rb"), filename=f"{file_id}.png")

    match = re.search(r"https://drive\.google\.com/file/d/([^/]+)/preview", url)
    if match:
        file_id = match.group(1)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise Exception(f"Download failed for {file_id}")
                data = await resp.read()

    with open(file_path, "wb") as f:
        f.write(data)

    return File(fp=open(file_path, "rb"), filename=f"{file_id}.png")
