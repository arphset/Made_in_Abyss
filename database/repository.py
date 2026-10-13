import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import date, datetime
from typing import Optional, List, Dict

from .security import hash_password, verify_password

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations')

# Порог «успешного» фото: вердикт «Удовлетворительно» и выше (см. score_calculator)
SUCCESS_SCORE = 6.0

# Часовой пояс для группировки статистики по дням и отображения дат
APP_TIMEZONE = os.environ.get('APP_TIMEZONE', 'Europe/Moscow')


class DatabaseRepository:
    def __init__(self):
        self.db_url = os.environ.get('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL не установлен в переменных окружения")

    def get_connection(self):
        """Получить подключение к БД"""
        return psycopg2.connect(self.db_url)

    def _fetch_all(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params or {})
                return cur.fetchall()

    def _fetch_one(self, query: str, params: Optional[Dict] = None) -> Optional[Dict]:
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params or {})
                return cur.fetchone()

    # ==========================================
    # СХЕМА И МИГРАЦИИ
    # ==========================================
    def ensure_schema(self):
        """Применить миграции из database/migrations (идемпотентные SQL-скрипты)"""
        files = sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith('.sql'))
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for name in files:
                    with open(os.path.join(MIGRATIONS_DIR, name), encoding='utf-8') as f:
                        cur.execute(f.read())
            conn.commit()

    def ensure_admin(self, login: str, password: str):
        """Создать учётную запись администратора, если её ещё нет"""
        if not login or not password:
            return
        query = """
            INSERT INTO users (login, password_hash, role)
            VALUES (%(login)s, %(password_hash)s, 'admin')
            ON CONFLICT (login) DO NOTHING
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, {'login': login, 'password_hash': hash_password(password)})
            conn.commit()

    # ==========================================
    # ПОЛЬЗОВАТЕЛИ И АУТЕНТИФИКАЦИЯ (S.01.01)
    # ==========================================
    def create_user(self, login: str, password: str, role: str = 'seller') -> Dict:
        """Зарегистрировать пользователя. ValueError, если логин занят."""
        query = """
            INSERT INTO users (login, password_hash, role)
            VALUES (%(login)s, %(password_hash)s, %(role)s)
            RETURNING id, login, role
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, {'login': login, 'password_hash': hash_password(password), 'role': role})
                    user = cur.fetchone()
                conn.commit()
                return dict(user)
        except psycopg2.errors.UniqueViolation:
            raise ValueError("Пользователь с таким логином уже существует")

    def authenticate(self, login: str, password: str) -> Optional[Dict]:
        """Проверить логин и пароль. Возвращает пользователя или None."""
        user = self._fetch_one(
            "SELECT id, login, role, password_hash FROM users WHERE login = %(login)s",
            {'login': login}
        )
        if not user or not verify_password(password, user['password_hash']):
            return None
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %(id)s", {'id': user['id']})
            conn.commit()
        return {'id': user['id'], 'login': user['login'], 'role': user['role']}

    def get_users_overview(self) -> List[Dict]:
        """Список пользователей с количеством проверок (для админки)"""
        query = """
            SELECT u.id, u.login, u.role, u.created_at, u.last_login,
                   COUNT(a.id) AS checks,
                   ROUND(AVG(a.overall_score)::numeric, 2)::float AS avg_score,
                   MAX(a.upload_date) AS last_check
            FROM users u
            LEFT JOIN analysis_results a ON a.user_id = u.id
            GROUP BY u.id
            ORDER BY checks DESC, u.login
        """
        return self._fetch_all(query)

    # ==========================================
    # ЖУРНАЛ ДЕЙСТВИЙ
    # ==========================================
    def log_action(self, user_id: Optional[int], action: str, details: str = '',
                   analysis_id: Optional[str] = None):
        """Записать операцию пользователя. Ошибки журнала не прерывают работу приложения."""
        query = """
            INSERT INTO activity_log (user_id, action, details, analysis_id)
            VALUES (%(user_id)s, %(action)s, %(details)s, %(analysis_id)s)
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, {'user_id': user_id, 'action': action,
                                        'details': details, 'analysis_id': analysis_id})
                conn.commit()
        except Exception as e:
            print(f"Ошибка записи в журнал действий: {e}")

    def get_activity_log(self, date_from: date, date_to: date,
                         user_ids: Optional[List[int]] = None,
                         actions: Optional[List[str]] = None,
                         limit: int = 500) -> List[Dict]:
        query = """
            SELECT l.created_at, u.login, u.role, l.action, l.details, l.analysis_id
            FROM activity_log l
            LEFT JOIN users u ON u.id = l.user_id
            WHERE (l.created_at AT TIME ZONE %(tz)s)::date BETWEEN %(date_from)s AND %(date_to)s
              AND (%(user_ids)s::int[] IS NULL OR l.user_id = ANY(%(user_ids)s::int[]))
              AND (%(actions)s::text[] IS NULL OR l.action = ANY(%(actions)s::text[]))
            ORDER BY l.created_at DESC
            LIMIT %(limit)s
        """
        return self._fetch_all(query, {
            'tz': APP_TIMEZONE, 'date_from': date_from, 'date_to': date_to,
            'user_ids': user_ids or None, 'actions': actions or None, 'limit': limit
        })

    def save_analysis_result(self, data: Dict) -> str:
        """Сохранить результат анализа в БД. Возвращает ID записи."""
        query = """
        INSERT INTO analysis_results (
            filename, storage_filename, overall_score, verdict,
            acf_score, laplacian_global, laplacian_local_median,
            sobel_variance, sharpness_index,
            brightness, overexposed_pct, underexposed_pct,
            fill_rate, is_off_center, object_found,
            issues, penalties, ai_recommendations,
            resolution, file_size_kb, user_id
        ) VALUES (
            %(filename)s, %(storage_filename)s, %(overall_score)s, %(verdict)s,
            %(acf_score)s, %(laplacian_global)s, %(laplacian_local_median)s,
            %(sobel_variance)s, %(sharpness_index)s,
            %(brightness)s, %(overexposed_pct)s, %(underexposed_pct)s,
            %(fill_rate)s, %(is_off_center)s, %(object_found)s,
            %(issues)s, %(penalties)s, %(ai_recommendations)s,
            %(resolution)s, %(file_size_kb)s, %(user_id)s
        ) RETURNING id
        """

        # Извлекаем метрики с проверкой структуры
        metrics = data.get('metrics', {})
        sharpness = metrics.get('sharpness', {})
        exposure = metrics.get('exposure', {})
        composition = metrics.get('composition', {})

        storage_filename = data.get('storage_filename')
        if not storage_filename:
            raise ValueError("storage_filename пустой: файл не был сохранён на диск перед записью в БД")

        # Подготавливаем данные с значениями по умолчанию
        params = {
            'filename': data.get('filename', ''),
            'storage_filename': storage_filename,
            'overall_score': data.get('overall_score', 0),
            'verdict': data.get('verdict', ''),

            # Метрики резкости
            'acf_score': sharpness.get('acf_score', 0),
            'laplacian_global': sharpness.get('laplacian_global', 0),
            'laplacian_local_median': sharpness.get('laplacian_local_median', 0),
            'sobel_variance': sharpness.get('sobel_gradient_variance', 0),
            'sharpness_index': sharpness.get('sharpness_index', 0),

            # Метрики экспозиции
            'brightness': exposure.get('brightness', 0),
            'overexposed_pct': exposure.get('overexposed_pct', 0),
            'underexposed_pct': exposure.get('underexposed_pct', 0),

            # Метрики композиции
            'fill_rate': composition.get('fill_rate_pct', 0) / 100 if composition.get('fill_rate_pct') else 0,
            'is_off_center': composition.get('is_off_center', False),
            'object_found': composition.get('object_found', True),

            # Остальные данные
            'issues': json.dumps(data.get('summary', {}).get('issues', []), ensure_ascii=False),
            'penalties': json.dumps(data.get('penalties', []), ensure_ascii=False),
            'ai_recommendations': data.get('ai_recommendations', ''),
            'resolution': data.get('file_info', {}).get('resolution', ''),
            'file_size_kb': data.get('file_info', {}).get('file_size_kb', 0),
            'user_id': data.get('user_id')
        }

        # numpy-скаляры (np.float64, np.bool_ и т.п.) приводим к нативным типам Python:
        # psycopg2 подставляет их в SQL как "np.float64(...)" (repr из NumPy 2)
        params = {k: v.item() if hasattr(v, 'item') else v for k, v in params.items()}

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    result_id = cur.fetchone()[0]
                    conn.commit()
                    return str(result_id)
        except Exception as e:
            print(f"Ошибка сохранения в БД: {e}")
            raise

    def get_all_analyses(self, limit: int = 50) -> List[Dict]:
        """Получить все результаты анализа (для админки)"""
        query = """
            SELECT id, filename, upload_date, overall_score, verdict,
                   resolution, file_size_kb
            FROM analysis_results
            ORDER BY upload_date DESC
            LIMIT %(limit)s
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, {'limit': limit})
                    return cur.fetchall()
        except Exception as e:
            print(f"Ошибка получения данных из БД: {e}")
            raise

    def get_analysis_by_id(self, analysis_id: str, requester: Optional[Dict] = None) -> Optional[Dict]:
        """
        Получить полный результат анализа по ID.
        Если передан requester, проверяются права: продавец видит только свои проверки,
        администратор — любые (S.01.02, S.01.03).
        """
        query = """
            SELECT a.*, u.login
            FROM analysis_results a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.id = %(id)s
        """
        record = self._fetch_one(query, {'id': analysis_id})
        if record and requester and requester.get('role') != 'admin' and record['user_id'] != requester.get('id'):
            return None
        return record

    # ==========================================
    # ПРОВЕРКИ (ОТЧЁТЫ)
    # ==========================================
    _REPORT_COLUMNS = """
        a.id, a.filename, a.storage_filename, a.upload_date, a.overall_score, a.verdict,
        a.issues, a.resolution, a.file_size_kb, a.user_id, u.login
    """

    def get_reports(self, date_from: date, date_to: date,
                    user_ids: Optional[List[int]] = None,
                    verdicts: Optional[List[str]] = None,
                    include_anonymous: bool = True,
                    limit: int = 500) -> List[Dict]:
        """Отчёты всех проверок с фильтрами по дате, пользователю и вердикту (задача 6.3)"""
        query = f"""
            SELECT {self._REPORT_COLUMNS}
            FROM analysis_results a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE (a.upload_date AT TIME ZONE %(tz)s)::date BETWEEN %(date_from)s AND %(date_to)s
              AND (
                    (a.user_id IS NULL AND %(include_anonymous)s)
                    OR (a.user_id IS NOT NULL
                        AND (%(user_ids)s::int[] IS NULL OR a.user_id = ANY(%(user_ids)s::int[])))
              )
              AND (%(verdicts)s::text[] IS NULL OR a.verdict = ANY(%(verdicts)s::text[]))
            ORDER BY a.upload_date DESC
            LIMIT %(limit)s
        """
        return self._fetch_all(query, {
            'tz': APP_TIMEZONE, 'date_from': date_from, 'date_to': date_to,
            'user_ids': user_ids or None, 'verdicts': verdicts or None,
            'include_anonymous': include_anonymous, 'limit': limit
        })

    def get_user_reports(self, user_id: int, limit: int = 200) -> List[Dict]:
        """История проверок одного пользователя (приватность истории S.01.03)"""
        query = f"""
            SELECT {self._REPORT_COLUMNS}
            FROM analysis_results a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE a.user_id = %(user_id)s
            ORDER BY a.upload_date DESC
            LIMIT %(limit)s
        """
        return self._fetch_all(query, {'user_id': user_id, 'limit': limit})

    def get_all_storage_filenames(self) -> List[str]:
        rows = self._fetch_all("SELECT storage_filename FROM analysis_results")
        return [r['storage_filename'] for r in rows]

    # ==========================================
    # АГРЕГИРОВАННАЯ СТАТИСТИКА (задача 6.1, F.03.01)
    # ==========================================
    def _period_params(self, date_from: date, date_to: date) -> Dict:
        return {'tz': APP_TIMEZONE, 'date_from': date_from, 'date_to': date_to, 'success': SUCCESS_SCORE}

    def get_period_summary(self, date_from: date, date_to: date) -> Dict:
        """Количество проверок, доля успешных/неуспешных, средняя оценка, активные пользователи"""
        params = self._period_params(date_from, date_to)
        summary = dict(self._fetch_one("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE overall_score >= %(success)s) AS success,
                COUNT(*) FILTER (WHERE overall_score < %(success)s) AS failed,
                ROUND(AVG(overall_score)::numeric, 2)::float AS avg_score,
                COUNT(DISTINCT user_id) AS active_users
            FROM analysis_results
            WHERE (upload_date AT TIME ZONE %(tz)s)::date BETWEEN %(date_from)s AND %(date_to)s
        """, params))
        errors = self._fetch_one("""
            SELECT COUNT(*) AS analysis_errors
            FROM activity_log
            WHERE action = 'analysis_error'
              AND (created_at AT TIME ZONE %(tz)s)::date BETWEEN %(date_from)s AND %(date_to)s
        """, params)
        summary['analysis_errors'] = errors['analysis_errors']
        return summary

    def get_daily_stats(self, date_from: date, date_to: date) -> List[Dict]:
        """Проверки по дням: всего / успешные / неуспешные"""
        query = """
            SELECT
                (upload_date AT TIME ZONE %(tz)s)::date AS day,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE overall_score >= %(success)s) AS success,
                COUNT(*) FILTER (WHERE overall_score < %(success)s) AS failed,
                ROUND(AVG(overall_score)::numeric, 2)::float AS avg_score
            FROM analysis_results
            WHERE (upload_date AT TIME ZONE %(tz)s)::date BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY day
            ORDER BY day
        """
        return self._fetch_all(query, self._period_params(date_from, date_to))

    def get_verdict_distribution(self, date_from: date, date_to: date) -> List[Dict]:
        query = """
            SELECT COALESCE(verdict, '—') AS verdict, COUNT(*) AS count
            FROM analysis_results
            WHERE (upload_date AT TIME ZONE %(tz)s)::date BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY verdict
        """
        return self._fetch_all(query, self._period_params(date_from, date_to))

    def get_top_users(self, date_from: date, date_to: date, limit: int = 10) -> List[Dict]:
        """Активность пользователей: топ по количеству загрузок за период"""
        query = """
            SELECT
                COALESCE(u.login, 'Без учётной записи') AS login,
                COUNT(*) AS checks,
                COUNT(*) FILTER (WHERE a.overall_score >= %(success)s) AS success,
                ROUND(AVG(a.overall_score)::numeric, 2)::float AS avg_score,
                MAX(a.upload_date) AS last_check
            FROM analysis_results a
            LEFT JOIN users u ON u.id = a.user_id
            WHERE (a.upload_date AT TIME ZONE %(tz)s)::date BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY u.login
            ORDER BY checks DESC
            LIMIT %(limit)s
        """
        params = self._period_params(date_from, date_to)
        params['limit'] = limit
        return self._fetch_all(query, params)

    def get_top_issues(self, date_from: date, date_to: date, limit: int = 10) -> List[Dict]:
        """Самые частые дефекты. Уточнения в скобках (проценты) отбрасываются для группировки."""
        query = r"""
            SELECT regexp_replace(issue, '\s*\(.*\)\s*$', '') AS issue, COUNT(*) AS count
            FROM analysis_results a,
                 jsonb_array_elements_text(COALESCE(a.issues, '[]'::jsonb)) AS issue
            WHERE (a.upload_date AT TIME ZONE %(tz)s)::date BETWEEN %(date_from)s AND %(date_to)s
            GROUP BY 1
            ORDER BY count DESC
            LIMIT %(limit)s
        """
        params = self._period_params(date_from, date_to)
        params['limit'] = limit
        return self._fetch_all(query, params)

    def get_statistics(self) -> Dict:
        """Получить общую статистику по анализам"""
        query = """
            SELECT
                COUNT(*) as total_analyses,
                ROUND(AVG(overall_score)::numeric, 2) as avg_score,
                ROUND(MIN(overall_score)::numeric, 2) as min_score,
                ROUND(MAX(overall_score)::numeric, 2) as max_score
            FROM analysis_results
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query)
                    return cur.fetchone()
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            raise