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

    def get_capture_date(self, image_data: Union[bytes, io.BytesIO, Image.Image]) -> Optional[datetime]:
        """
        獲取圖片拍攝日期
        輸入: bytes、BytesIO 對象或 PIL Image
        輸出: datetime 對象，如果無法獲取則返回 None
        """
        try:
            # 如果是 PIL Image，直接使用
            if isinstance(image_data, Image.Image):
                pil_image = image_data
            else:
                # 轉換為 BytesIO 再轉為 PIL Image
                bytesio = self._ensure_bytesio(image_data)
                pil_image = self._bytesio_to_pil(bytesio)
                
            if not pil_image:
                self.logger.warning("無法轉換為 PIL Image，無法獲取拍攝日期")
                return None

            # 獲取 EXIF 數據
            exif_data = pil_image._getexif()
            if not exif_data:
                self.logger.info("圖片沒有 EXIF 數據")
                return None

            # 查找拍攝日期相關的 EXIF 標籤
            # 按優先順序嘗試不同的日期標籤
            date_tags = [
                'DateTime',           # 圖片修改日期
                'DateTimeOriginal',   # 原始拍攝日期（最準確）
                'DateTimeDigitized'   # 數位化日期
            ]

            for tag_name in date_tags:
                # 找到對應的標籤 ID
                tag_id = None
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == tag_name:
                        tag_id = orientation
                        break
                
                if tag_id and tag_id in exif_data:
                    date_string = exif_data[tag_id]
                    try:
                        # EXIF 日期格式通常是 "YYYY:MM:DD HH:MM:SS"
                        capture_date = datetime.strptime(date_string, "%Y:%m:%d %H:%M:%S")
                        self.logger.info(f"成功獲取拍攝日期: {capture_date} (來源: {tag_name})")
                        return capture_date
                    except ValueError as e:
                        self.logger.warning(f"無法解析日期格式 '{date_string}': {str(e)}")
                        continue

            self.logger.info("EXIF 數據中沒有找到拍攝日期信息")
            return None

        except Exception as e:
            self.logger.error(f"獲取拍攝日期時出錯: {str(e)}")
            return None

    def get_capture_date_string(self, image_data: Union[bytes, io.BytesIO, Image.Image], 
                               format_string: str = "%Y-%m-%d") -> Optional[str]:
        """
        獲取圖片拍攝日期的字符串格式
        輸入: 圖片數據和格式字符串
        輸出: 格式化的日期字符串，如果無法獲取則返回 None
        """
        capture_date = self.get_capture_date(image_data)
        if capture_date:
            return capture_date.strftime(format_string)
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
            upload_time = datetime.now()

            url = f"https://{self.bucket_name}.s3.amazonaws.com/{unique_filename}"
            self.logger.info(f"Successfully uploaded image: {url}")
            return {
                'url': url,
                's3_key': unique_filename,
                'upload_date': upload_time.isoformat()
            }

        except Exception as e:
            self.logger.error(f"Upload error: {str(e)}")
            return None

class S3ImageUtils:
    def __init__(self, bucket_name: str):
        self.logger = setup_logger("S3ImageUtils")
        self.image_processor = ImageProcessor(self.logger)
        self.s3_handler = S3Handler(bucket_name, self.logger)
    
    def init_image_info(self):
        return {
            's3_url': None,
            'filename': '',
            'original_filename': '',
            's3_key': '',
            'file_size': 0,
            'capture_date_string': None,
            'upload_date': None,
            'processed': False,
            'error_message': None
        }

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
            result = self.init_image_info()

            image_data = await self.download_discord_attachment(attachment_url)
            if not image_data:
                self.logger.error("Image download failed")
                result['error_message'] = "圖片下載失敗"
                return result

            original_filename, file_ext = await self.get_filename_and_extension_from_url(attachment_url)
            self.logger.info(f"原始檔案: {original_filename}, 副檔名: {file_ext}")
            result['original_filename'] = original_filename
            result['filename'] = original_filename

            if file_ext.lower() in ['.heic', '.heif']:
                self.logger.info("檢測到 HEIC/HEIF 格式，開始轉換為 JPEG")
                converted_data = self.image_processor.convert_heic_to_jpeg(image_data)
                if not converted_data:
                    result['error_message'] = "HEIC 轉換失敗"
                    self.logger.error(result['error_message'])
                    return result
                image_data = converted_data
                result['filename'] = os.path.splitext(original_filename)[0] + ".jpg"
                self.logger.info(f"HEIC 轉換成功，新檔名: {result['filename']}")

            self.logger.info("開始旋轉圖片處理")
            rotated_data = self.image_processor.rotate_image(image_data)
            if not rotated_data:
                result['error_message'] = "圖片旋轉失敗"
                self.logger.error(result['error_message'])
                return result
            image_data = rotated_data
            self.logger.info("圖片旋轉處理完成")

            self.logger.info("獲取圖片拍攝日期")
            capture_date_string = self.image_processor.get_capture_date_string(image_data, "%Y-%m-%d %H:%M:%S")
            if capture_date_string:
                result['capture_date_string'] = capture_date_string
                self.logger.info(f"拍攝日期: {capture_date_string}")
            else:
                self.logger.info("無法獲取圖片拍攝日期")

            self.logger.info("開始壓縮圖片")
            compressed_data = self.image_processor.compress_image(image_data)
            if not compressed_data:
                result['error_message'] = "圖片壓縮失敗"
                self.logger.error(result['error_message'])
                return result
            image_data = compressed_data
            self.logger.info("圖片壓縮完成")

            image_data.seek(0)
            result['file_size'] = len(image_data.getvalue())
            self.logger.info(f"最終檔案大小: {result['file_size']} bytes")

            self.logger.info("開始上傳到 S3")
            s3_result = self.s3_handler.upload_image(image_data, result['filename'])
            if s3_result:
                result['s3_url'] = s3_result['url']
                result['s3_key'] = s3_result['s3_key']
                result['upload_date'] = s3_result['upload_date']
                result['processed'] = True
                self.logger.info(f"✅ 圖片處理完成!")
                self.logger.info(f"S3 URL: {result['s3_url']}")
                self.logger.info(f"S3 Key: {result['s3_key']}")
                self.logger.info(f"檔案大小: {result['file_size']} bytes")
                if result.get('capture_date_string'):
                    self.logger.info(f"拍攝日期: {result['capture_date_string']}")
            else:
                result['error_message'] = "S3 上傳失敗"
                self.logger.error(result['error_message'])

            return result

        except Exception as e:
            result['error_message'] = f"處理過程發生錯誤: {str(e)}"
            self.logger.error(result['error_message'], exc_info=True)
            return result
