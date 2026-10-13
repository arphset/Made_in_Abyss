"""
Изолированное окружение для тестов: отдельная БД qualityjpg_test и временное файловое хранилище.
Рабочая БД и папка frontend/uploads не затрагиваются.

Импортировать ДО модулей проекта: репозиторий читает DATABASE_URL при импорте.
"""
import os
import shutil
import socket
import sys
import tempfile
from urllib.parse import urlparse, urlunparse

import psycopg2
from psycopg2 import sql

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(PROJECT_ROOT, 'frontend')
ML_DIR = os.path.join(PROJECT_ROOT, 'ML&CV_Module')
DATABASE_DIR = os.path.join(PROJECT_ROOT, 'database')
TEST_IMAGES_DIR = os.path.join(PROJECT_ROOT, 'test_jpegs')

TEST_DB_NAME = 'qualityjpg_test'
ADMIN_LOGIN = 'test_admin'
ADMIN_PASSWORD = 'test_admin_pass'

for path in (ML_DIR, FRONTEND_DIR, PROJECT_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

_prod_url = os.environ.get('DATABASE_URL')
if not _prod_url:
    raise RuntimeError("DATABASE_URL не задан: запускайте тесты в контейнере приложения")
if urlparse(_prod_url).path.lstrip('/') == TEST_DB_NAME:
    raise RuntimeError("testenv уже применён")

TEST_DB_URL = urlunparse(urlparse(_prod_url)._replace(path='/' + TEST_DB_NAME))


def _recreate_test_database():
    """Пересоздать тестовую БД и применить схему так же, как при первом запуске Postgres"""
    admin_conn = psycopg2.connect(_prod_url)
    admin_conn.autocommit = True
    with admin_conn.cursor() as cur:
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DB_NAME)))
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB_NAME)))
    admin_conn.close()

    conn = psycopg2.connect(TEST_DB_URL)
    with conn, conn.cursor() as cur:
        with open(os.path.join(DATABASE_DIR, 'init.sql'), encoding='utf-8') as f:
            cur.execute(f.read())
    conn.close()


_recreate_test_database()
os.environ['DATABASE_URL'] = TEST_DB_URL
os.environ['ADMIN_LOGIN'] = ADMIN_LOGIN
os.environ['ADMIN_PASSWORD'] = ADMIN_PASSWORD

from database import db_repo  # noqa: E402
import storage  # noqa: E402

# Миграции и админ — тем же кодом, что и при старте приложения
db_repo.ensure_schema()
db_repo.ensure_admin(ADMIN_LOGIN, ADMIN_PASSWORD)

# Временное файловое хранилище вместо frontend/uploads
TEMP_UPLOAD_DIR = tempfile.mkdtemp(prefix='qualityjpg_uploads_')
storage.UPLOAD_DIR = TEMP_UPLOAD_DIR


def cleanup():
    shutil.rmtree(TEMP_UPLOAD_DIR, ignore_errors=True)


def ollama_available() -> bool:
    url = urlparse(os.environ.get('OLLAMA_HOST', 'http://localhost:11434'))
    try:
        with socket.create_connection((url.hostname, url.port or 11434), timeout=2):
            return True
    except OSError:
        return False


def admin_user() -> dict:
    return db_repo.authenticate(ADMIN_LOGIN, ADMIN_PASSWORD)
