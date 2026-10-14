# QualityJPG («Made in Abyss»)

Учебный проект (дисциплина «Технологии создания и поддержки ПО», автор — Ерёмин Аким, ПИ21/1).
Веб-система оценки качества фото товаров для маркетплейсов: CV-метрики (резкость, экспозиция,
композиция) + текстовые рекомендации от локальной LLM (Ollama). Интерфейс на русском (U.01.03).

Документы курса (ТЗ, декомпозиция, UML) лежат в родительской папке `projpo/`, вне репозитория.

## Статус спринтов
- ✅ Спринт 1 — MVP: загрузка, валидация (JPG/PNG ≤ 10 МБ), хранилище, ML-анализ, отчёт, спиннер.
- ✅ Спринт 2 — PostgreSQL, запись результатов, рекомендации, копирование (текст/JSON), обработка ошибок ML.
- ✅ Спринт 3 (коммит `14b8aaf`) — аутентификация, роли seller/admin, админ-панель, журнал действий, защита файлов.
- ✅ Спринт 4 (коммит `f94e42b`) — оптимизация отклика (среднее 24,8 → 12,0 с, макс. 33,2 → 20,1 с), 43 автотеста, документация
  (`README.md`, `docs/USER_GUIDE.md`, `docs/TEST_REPORT.md`). Все задачи декомпозиции закрыты.
  Возможные доработки: сохранение входа после F5 (cookie), смена дефолтного пароля админа.

## Код
- `frontend/app.py` — точка входа: тема, миграции БД + сид админа (`st.cache_resource`), экран входа,
  `st.navigation(position="hidden")` + своя верхняя панель (`st.page_link`).
- `frontend/views/analyze.py` — загрузка и анализ фото (бывший код app.py из спринтов 1–2).
- `frontend/views/history.py` — «Мои проверки» (только свои записи, S.01.03).
- `frontend/views/admin.py` — админ-панель: вкладки Статистика / Отчёты проверок / Журнал действий / Пользователи.
  Начинается с `require_admin()` (403 для продавца).
- `frontend/auth.py` — вход/регистрация (регистрация только как seller), `current_user`, `log_action`, `ACTION_LABELS`.
- `frontend/theme.py` — общий дизайн: canvas-фон с частицами, кнопка музыки, весь CSS. Все страницы должны
  выглядеть одинаково — новые стили добавлять сюда.
- `frontend/report_view.py` — `format_recommendations`, `render_report_details`, превью, `fmt_dt` (часовой пояс).
- `frontend/storage.py` — файловое хранилище `frontend/uploads/` (UUID-имена, проверка имени против path traversal).
  Файл читать только после получения записи через `get_analysis_by_id(id, requester)`.
- `database/repository.py` — `DatabaseRepository` (psycopg2, сырой SQL), глобальный `db_repo`.
- `database/security.py` — хэш паролей PBKDF2-SHA256 (stdlib).
- `database/init.sql` + `database/migrations/*.sql` — схема. Миграции идемпотентные, выполняются при старте
  приложения (`ensure_schema`) и при первой инициализации тома Postgres.
- `ML&CV_Module/` — `main.analyze_image(path)`, `filters/` (blur, brightness, YOLO, score_calculator),
  `ollama/ollama_access`: `stream_recommendations` (генератор: блок метрик кодом + ответ LLM потоком),
  `get_recommendations`, `warmup`. YOLO кэшируется в `filters/YOLO.get_model()` (с lock).
- `tests/` — `run_tests.py` (unittest + streamlit AppTest, отдельная БД `qualityjpg_test`, временные uploads),
  `benchmark.py` (замер R.01.01). Протоколы → `tests/results/`.

## БД (PostgreSQL 16)
- `analysis_results` — проверка: метрики, `issues`/`penalties` (JSONB), `ai_recommendations`, `storage_filename`,
  `user_id` (NULL у записей до спринта 3). `fill_rate` хранится долей (0–1).
- `users` (login, password_hash, role ∈ seller/admin), `activity_log` (action, details, analysis_id).
- Время обработки: `cv_time_ms`, `llm_time_ms`, `total_time_ms` (миграция 003); норматив 30 с.
- «Успешное» фото: `overall_score >= 6.0` (константа `SUCCESS_SCORE` в repository.py).
- Даты группируются по `APP_TIMEZONE` (Europe/Moscow).

## Запуск
- `docker compose up -d` в корне репозитория: контейнеры `qualityjpg_app` (Streamlit :8501) и `qualityjpg_db` (:5432).
  Ollama — на хосте (`host.docker.internal:11434`).
- Тесты: `docker exec qualityjpg_app python tests/run_tests.py`; замер: `python tests/benchmark.py`.
- Папки `frontend/`, `database/`, `.streamlit/`, `ML&CV_Module/`, `tests/`, `test_jpegs/` смонтированы в контейнер, но Streamlit на Windows не видит
  изменений файлов → после правок Python-кода: `docker restart qualityjpg_app`.
- Админ по умолчанию: `ADMIN_LOGIN`/`ADMIN_PASSWORD` из docker-compose (создаётся, только если логина ещё нет).
- Вход хранится в `st.session_state` → после F5 или прямого перехода по URL нужно войти заново.

## Подводные камни
- Streamlit **1.41.1**: нет `row_height` у `st.dataframe`; страницы не класть в папку `pages/` (авто-MPA).
- AppTest: после `st.rerun()` дерево устаревает, а `st.navigation` не исполняет вложенную страницу —
  страницы тестировать прямым `AppTest.from_file(views/...)` с `session_state['user']`.
- Значения numpy перед записью в БД приводить к нативным типам (`.item()`), иначе psycopg2 ломается.
- В Git Bash для `docker exec -w /app ...` нужен `MSYS_NO_PATHCONV=1`.
- SSH до GitHub иногда даёт ложную ошибку «access rights» — просто повторить команду.
- Коммиты спринтов до сих пор шли прямо в `main`; перед коммитом/пушем всё равно уточнять у пользователя.

## Граф кода (codebase-memory-mcp)
- `.codebase-memory/graph.db.zst` — сжатый граф кода (функции, классы, вызовы, импорты), `artifact.json` — коммит
  и время индексации. Создаётся `index_repository(persistence=true)`; после заметных правок переиндексировать и
  закоммитить вместе с кодом.
- Для структурных вопросов (кто вызывает, зависимости, архитектура) сначала `search_graph` / `trace_path` /
  `get_architecture`, для строк и литералов — обычный grep.
