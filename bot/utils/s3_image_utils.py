import uuid
import aiohttp
import io
import os
import boto3
import pyheif
from PIL import Image, ExifTags
from datetime import datetime, timedelta
from typing import Optional, Union
from pathlib import Path
from urllib.parse import urlparse

from bot.logger import setup_logger

class ImageProcessor:
    def __init__(self, logger):
        self.MAX_SIZE = (1024, 1024)  # 最大圖片尺寸
        self.QUALITY = 85  # JPEG 壓縮品質
        self.MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
        self.ALLOWED_TYPES = ['image/jpeg', 'image/png']
        self.ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.heic', '.heif']
        self.logger = logger

    def _ensure_bytesio(self, image_data: Union[bytes, io.BytesIO, Image.Image]) -> io.BytesIO:
        """確保輸入被轉換為 BytesIO 對象"""
        # 如果是 PIL Image，轉換為 BytesIO
        if isinstance(image_data, Image.Image):
            output = io.BytesIO()
            image_data.save(output, format='JPEG', quality=self.QUALITY)
            output.seek(0)
            return output

        # 如果是 bytes，轉換為 BytesIO
        elif isinstance(image_data, bytes):
            return io.BytesIO(image_data)

        # 如果已經是 BytesIO，確保指標在開頭
        elif isinstance(image_data, io.BytesIO):
            image_data.seek(0)
            return image_data

        # 不支援的類型
        else:
            self.logger.error(f"不支援的輸入類型: {type(image_data)}")
            raise TypeError(f"不支援的輸入類型: {type(image_data)}")

    def _bytesio_to_pil(self, bytesio: io.BytesIO) -> Optional[Image.Image]:
        """將 BytesIO 轉換為 PIL Image"""
        try:
            bytesio.seek(0)
            return Image.open(bytesio)
        except Exception as e:
            self.logger.error(f"無法將 BytesIO 轉換為 PIL Image: {str(e)}")
            return None

    def convert_heic_to_jpeg(self, image_data: Union[bytes, io.BytesIO]) -> Optional[io.BytesIO]:
        """
        將 HEIC 圖像轉換為 JPEG
        輸入: bytes 或 BytesIO 對象
        輸出: BytesIO 對象，包含 JPEG 數據
        """
        try:
            # 確保輸入是 BytesIO
            bytesio = self._ensure_bytesio(image_data)

            # 從 BytesIO 讀取 bytes
            bytesio.seek(0)
            image_bytes = bytesio.read()

            # 使用 pyheif 讀取 HEIC 文件
            heif_file = pyheif.read(image_bytes)

            # 轉換為 PIL Image
            image = Image.frombytes(heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw",
                heif_file.mode,
                heif_file.stride,
            )

            # 轉換為 JPEG BytesIO
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=self.QUALITY)
            output.seek(0)
            self.logger.info(f"HEIC 轉換成功: size={len(output.getvalue())}")
            return output
        except Exception as e:
            self.logger.error(f"HEIC 轉換失敗: {str(e)}")
            return None

    def rotate_image(self, image_data: Union[io.BytesIO, Image.Image]) -> Optional[io.BytesIO]:
        try:
            bytesio = self._ensure_bytesio(image_data)
            pil_image = self._bytesio_to_pil(bytesio)
            if not pil_image:
                self.logger.warning("無法轉換為 PIL Image，返回原始數據")
                bytesio.seek(0)
                return bytesio

            # 處理 EXIF 旋轉
            try:
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break
                exif = pil_image._getexif()
                if exif is not None and orientation in exif:
                    if exif[orientation] == 3:
                        pil_image = pil_image.rotate(180, expand=True)
                    elif exif[orientation] == 6:
                        pil_image = pil_image.rotate(270, expand=True)
                    elif exif[orientation] == 8:
                        pil_image = pil_image.rotate(90, expand=True)
            except (AttributeError, KeyError, IndexError, TypeError) as e:
                self.logger.warning(f"讀取 EXIF 數據時出錯: {str(e)}")
                # 繼續執行，不要因為 EXIF 讀取失敗就中斷

            # 轉換回 BytesIO
            output = io.BytesIO()
            pil_image.save(output, format='JPEG', quality=self.QUALITY)
            output.seek(0)
            return output

        except Exception as e:
            self.logger.error(f"旋轉圖片時出錯: {str(e)}")
            # 嘗試返回原始數據
            if isinstance(image_data, io.BytesIO):
                image_data.seek(0)
                return image_data
            return None

    def compress_image(self, image_data: Union[io.BytesIO, Image.Image]) -> Optional[io.BytesIO]:
        try:
            bytesio = self._ensure_bytesio(image_data)

            # 檢查是否需要壓縮
            bytesio.seek(0)
            current_size = len(bytesio.getvalue())
            if current_size <= self.MAX_FILE_SIZE:
                self.logger.info(f"圖片已經足夠小 ({current_size} bytes)，不需要壓縮")
                bytesio.seek(0)
                return bytesio

            # 轉換為 PIL Image 進行處理
            pil_image = self._bytesio_to_pil(bytesio)
            if not pil_image:
                self.logger.warning("無法轉換為 PIL Image，返回原始數據")
                bytesio.seek(0)
                return bytesio

            # 轉換為 RGB 模式（如果是 RGBA）
            if pil_image.mode == 'RGBA':
                pil_image = pil_image.convert('RGB')

            # 調整圖片大小，保持比例
            pil_image.thumbnail(self.MAX_SIZE)

            # 保存為 JPEG 格式的 BytesIO 對象
            output = io.BytesIO()
            pil_image.save(output, format='JPEG', quality=self.QUALITY, optimize=True)
            output.seek(0)
            return output

        except Exception as e:
            self.logger.error(f"Image compression error: {str(e)}")
            if isinstance(image_data, io.BytesIO):
                image_data.seek(0)
                return image_data
            return None

class S3Handler:
    def __init__(self, bucket_name: str, logger):
        self.logger = logger
        self.s3_client = boto3.client('s3')
        self.bucket_name = bucket_name
        self.ALLOWED_FOLDER = 'baby_images/'

    def _generate_unique_filename(self, original_filename: str) -> str:
        """生成唯一的檔案名稱"""
        ext = os.path.splitext(original_filename)[1].lower()
        if ext.lower() in ['.heic', '.heif']:
            ext = '.jpg'
        return f"{self.ALLOWED_FOLDER}{uuid.uuid4()}{ext}"

    def upload_image(self, image_data: io.BytesIO, original_filename: str) -> Optional[str]:
        try:
            if not isinstance(image_data, io.BytesIO):
                self.logger.error(f"upload_image: 輸入不是 BytesIO 物件，而是 {type(image_data)}")
                return None

            # 生成唯一檔案名稱
            unique_filename = self._generate_unique_filename(original_filename)

            # 確保指標在開頭
            image_data.seek(0)

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

    async def get_filename_and_extension_from_url(self, url):
        parsed_url = urlparse(url)
        path = parsed_url.path  # e.g. /attachments/.../IMG_1564.jpg
        filename = os.path.basename(path)  # e.g. IMG_1564.jpg
        name, ext = os.path.splitext(filename)
        return filename, ext.lower()

    async def check_discord_attachment(self, attachment) -> bool:
        file_ext = os.path.splitext(attachment.filename)[1].lower()
        self.logger.info(f"處理文件: {attachment.filename}, 類型: {file_ext}")
        if file_ext not in self.image_processor.ALLOWED_EXTENSIONS:
            self.logger.error(f"Invalid file type: {file_ext}")
            return False
        else:
            return True

    async def process_discord_attachment(self, attachment_url) -> Optional[str]:
        try:
            image_data = await self.download_discord_attachment(attachment_url)
            if not image_data:
                self.logger.error("Image download failed")
                return None
            
            filename, file_ext = await self.get_filename_and_extension_from_url(attachment_url)

            # 處理 HEIC/HEIF 格式
            if file_ext in ['.heic', '.heif']:
                image_data = self.image_processor.convert_heic_to_jpeg(image_data)
                if not image_data:
                    self.logger.error("HEIC 轉換失敗")
                    return None
                filename = os.path.splitext(filename)[0] + ".jpg"

            # 旋轉圖片
            image_data = self.image_processor.rotate_image(image_data)
            if not image_data:
                self.logger.error("Image rotate failed")
                return None

            # 壓縮圖片
            image_data = self.image_processor.compress_image(image_data)
            if not image_data:
                self.logger.error("Image compression failed")
                return None

            # 使用現有的 S3Handler 上傳圖片
            return self.s3_handler.upload_image(image_data, filename)

        except Exception as e:
            self.logger.error(f"Processing error: {str(e)}")
            return None
