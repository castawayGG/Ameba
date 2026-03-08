# models/media_file.py
# Модель для централизованной медиатеки (фото, видео, аудио)
from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger
from sqlalchemy.sql import func
from core.database import Base


class MediaFile(Base):
    """
    Запись о медиафайле, загруженном в медиатеку.
    Поддерживает изображения (JPEG/PNG), видео (MP4), аудио (OGG/MP3).
    """
    __tablename__ = 'media_files'

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)           # сохранённое имя файла на диске
    original_name = Column(String(255), nullable=False)      # оригинальное имя файла
    mime_type = Column(String(100), nullable=False)          # MIME-тип: image/jpeg, video/mp4, audio/ogg
    size_bytes = Column(BigInteger, default=0)               # размер файла в байтах
    description = Column(Text, nullable=True)                # необязательное описание
    uploaded_by = Column(String(50), nullable=True)          # пользователь, загрузивший файл
    created_at = Column(DateTime, server_default=func.now(), index=True)

    def __repr__(self):
        return f"<MediaFile {self.original_name} ({self.mime_type})>"

    @property
    def is_image(self):
        return self.mime_type and self.mime_type.startswith('image/')

    @property
    def is_video(self):
        return self.mime_type and self.mime_type.startswith('video/')

    @property
    def is_audio(self):
        return self.mime_type and self.mime_type.startswith('audio/')

    @property
    def size_human(self):
        """Возвращает размер файла в человекочитаемом формате."""
        size = self.size_bytes or 0
        for unit in ('Б', 'КБ', 'МБ', 'ГБ'):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} ТБ"
