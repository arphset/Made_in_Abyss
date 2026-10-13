import os
import re
import uuid
from typing import Dict, List, Optional

import cv2
import numpy as np

# Файловое хранилище (I_FILE_STORAGE на диаграмме компонентов, D.01.02).
# Папка не раздаётся Streamlit как статика: файлы читаются только сервером
# после проверки прав на соответствующую запись в БД (S.01.03, задача 7.2).
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Имя файла в хранилище: UUID + расширение, никаких путей
_STORAGE_NAME_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(jpg|jpeg|png)$')


def save_image(original_name: str, img_array: np.ndarray):
    """Сохранить изображение под уникальным UUID. Возвращает (путь, имя в хранилище)."""
    ext = os.path.splitext(original_name)[1].lower()
    unique_name = str(uuid.uuid4()) + ext
    path = os.path.join(UPLOAD_DIR, unique_name)
    cv2.imwrite(path, img_array)
    return path, unique_name


def _resolve(storage_filename: str) -> Optional[str]:
    """Безопасное получение пути: отсекает подмену имени (../, абсолютные пути)"""
    if not storage_filename or not _STORAGE_NAME_RE.match(storage_filename):
        return None
    path = os.path.join(UPLOAD_DIR, storage_filename)
    return path if os.path.isfile(path) else None


def read_image(storage_filename: str) -> Optional[np.ndarray]:
    """Прочитать изображение (BGR). Вызывать только после проверки прав на запись в БД."""
    path = _resolve(storage_filename)
    if path is None:
        return None
    return cv2.imread(path, cv2.IMREAD_COLOR)


def make_thumbnail(storage_filename: str, size: int = 96) -> Optional[bytes]:
    """JPEG-превью для таблиц админ-панели"""
    img = read_image(storage_filename)
    if img is None:
        return None
    h, w = img.shape[:2]
    scale = size / max(h, w)
    thumb = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode('.jpg', thumb, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return buf.tobytes() if ok else None


def storage_overview(db_filenames: List[str]) -> Dict:
    """Сверка хранилища с БД: число файлов, объём, «осиротевшие» файлы и записи без файла"""
    files = {f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))}
    total_bytes = sum(os.path.getsize(os.path.join(UPLOAD_DIR, f)) for f in files)
    db_set = set(db_filenames)
    return {
        'files': len(files),
        'size_mb': round(total_bytes / 1024 / 1024, 2),
        'orphan_files': len(files - db_set),
        'missing_files': len(db_set - files),
    }
