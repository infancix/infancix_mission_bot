import uuid
import aiohttp
import io
import os
import boto3
from PIL import Image, ExifTags
from datetime import datetime, timedelta
from typing import Optional, Union
from pathlib import Path

from bot.logger import setup_logger

class ImageProcessor:
    def __init__(self, logger):
        self.MAX_SIZE = (1024, 1024)  # 最大圖片尺寸
        self.QUALITY = 85  # JPEG 壓縮品質
        self.MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        self.ALLOWED_TYPES = ['image/jpeg', 'image/png']
        self.ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.heic', '.heif']
        self.logger = logger

    def rotate_image(self, image: Union[bytes, io.BytesIO, str]) -> Optional[io.BytesIO]:
        try:
            for orientation in ExifTags.TAGS.keys():
                if ExifTags.TAGS[orientation] == 'Orientation':
                    break

            exif = image._getexif()
            if exif is not None:
                # 根據 EXIF 方向信息旋轉圖片
                if orientation in exif:
                    if exif[orientation] == 3:
                        image = image.rotate(180, expand=True)
                    elif exif[orientation] == 6:
                        image = image.rotate(270, expand=True)
                    elif exif[orientation] == 8:
                        image = image.rotate(90, expand=True)
            return image
        except (AttributeError, KeyError, IndexError):
            # 處理沒有 EXIF 數據的情況
            return None

    def compress_image(self, image: Union[bytes, io.BytesIO, str]) -> Optional[io.BytesIO]:
        """
        壓縮圖片並返回 BytesIO 對象
        """

        try:
            # 轉換為 RGB 模式（如果是 RGBA）
            if image.mode == 'RGBA':
                image = image.convert('RGB')

            # 調整圖片大小，保持比例
            image.thumbnail(self.MAX_SIZE)

            # 保存為 JPEG 格式的 BytesIO 對象
            output = io.BytesIO()
            image.save(output,
                      format='JPEG',
                      quality=self.QUALITY,
                      optimize=True)
            output.seek(0)
            return output

        except Exception as e:
            self.logger.error(f"Image compression error: {str(e)}")
            return None

    def convert_heif_to_jpeg(image: Union[bytes, io.BytesIO, str]):
        image = Image.open(image)
        output = io.BytesIO()
        image.save(output, format="JPEG")
        return output.getvalue()

class S3Handler:
    def __init__(self, bucket_name: str, logger):
        self.logger = logger
        self.s3_client = boto3.client('s3')
        self.bucket_name = bucket_name
        self.ALLOWED_FOLDER = 'baby_images/'

    def _generate_unique_filename(self, original_filename: str) -> str:
        """生成唯一的檔案名稱"""
        ext = os.path.splitext(original_filename)[1].lower()
        return f"{self.ALLOWED_FOLDER}{uuid.uuid4()}{ext}"

    def upload_image(self, image_data: io.BytesIO, original_filename: str) -> Optional[str]:
        """
        上傳圖片到 S3
        返回: 成功時返回 URL，失敗時返回 None
        """
        try:
            # 生成唯一檔案名稱
            unique_filename = self._generate_unique_filename(original_filename)

            # 上傳到 S3
            self.s3_client.upload_fileobj(image_data,
                self.bucket_name,
                unique_filename,
                ExtraArgs={
                    'ContentType': 'image/jpeg',
                    'Metadata': {
                        'upload-date': datetime.now().isoformat(),
                        'original-filename': original_filename
                    }
                }
            )

            # 返回公開 URL
            url = f"https://{self.bucket_name}.s3.amazonaws.com/{unique_filename}"
            self.logger.info(f"Successfully uploaded image: {url}")
            return url

        except Exception as e:
            self.logger.error(f"Upload error: {str(e)}")
            return None

class S3ImageUtils:
    def __init__(self, bucket_name: str):
        self.logger = setup_logger("S3ImageUtils")
        self.image_processor = ImageProcessor(self.logger)
        self.s3_handler = S3Handler(bucket_name, self.logger)

    async def download_discord_attachment(self, attachment_url: str) -> Optional[io.BytesIO]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment_url) as response:
                    if response.status != 200:
                        self.logger.error(f"Failed to download image: {response.status}")
                        return None

                    data = await response.read()
                    return io.BytesIO(data)
        except Exception as e:
            self.logger.error(f"Download error: {str(e)}")
            return None

    async def process_discord_attachment(self, attachment) -> Optional[str]:
        try:
            # 檢查是否為有效的圖片類型
            file_ext = os.path.splitext(attachment.filename)[1].lower()
            if file_ext not in self.image_processor.ALLOWED_EXTENSIONS:
                self.logger.error(f"Invalid file type: {file_ext}")
                return None

            # 下載圖片
            image_data = await self.download_discord_attachment(attachment.url)
            if not image_data:
                self.logger.error("Image download failed")
                return None

            # 打開圖片進行處理
            if file_ext in ['.heic', '.heif']:
                image = self.image_processor.convert_heif_to_jpeg(image_data)
            else:
                image = Image.open(image_data)

            rotated_image = self.image_processor.rotate_image(image)
            if not rotated_image:
                self.logger.error("Image rotate failed")
                return None

            # 壓縮圖片
            compressed_image = self.image_processor.compress_image(rotated_image)
            if not compressed_image:
                self.logger.error("Image compression failed")
                return None

            # 使用現有的 S3Handler 上傳圖片
            return self.s3_handler.upload_image(compressed_image, attachment.filename)

        except Exception as e:
            self.logger.error(f"Processing error: {str(e)}")
            return None

async def handle_discord_image(attachment):
    handler = S3ImageHandler("infancix-app-storage-jp")
    url = await handler.process_discord_attachment(attachment)
    if url:
        print(f"Successfully uploaded to: {url}")
    else:
        print("Upload failed")

