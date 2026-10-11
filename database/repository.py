import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime
from typing import Optional, List, Dict

class DatabaseRepository:
    def __init__(self):
        self.db_url = os.environ.get('DATABASE_URL')
        if not self.db_url:
            raise ValueError("DATABASE_URL не установлен в переменных окружения")

    def get_connection(self):
        """Получить подключение к БД"""
        return psycopg2.connect(self.db_url)

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
            resolution, file_size_kb
        ) VALUES (
            %(filename)s, %(storage_filename)s, %(overall_score)s, %(verdict)s,
            %(acf_score)s, %(laplacian_global)s, %(laplacian_local_median)s,
            %(sobel_variance)s, %(sharpness_index)s,
            %(brightness)s, %(overexposed_pct)s, %(underexposed_pct)s,
            %(fill_rate)s, %(is_off_center)s, %(object_found)s,
            %(issues)s, %(penalties)s, %(ai_recommendations)s,
            %(resolution)s, %(file_size_kb)s
        ) RETURNING id
        """

        # Извлекаем метрики с проверкой структуры
        metrics = data.get('metrics', {})
        sharpness = metrics.get('sharpness', {})
        exposure = metrics.get('exposure', {})
        composition = metrics.get('composition', {})

        # Подготавливаем данные с значениями по умолчанию
        params = {
            'filename': data.get('filename', ''),
            'storage_filename': data.get('storage_filename', data.get('filename', '')),
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
            'file_size_kb': data.get('file_info', {}).get('file_size_kb', 0)
        }

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

    def get_analysis_by_id(self, analysis_id: str) -> Optional[Dict]:
        """Получить полный результат анализа по ID"""
        query = """
            SELECT * FROM analysis_results WHERE id = %(id)s
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, {'id': analysis_id})
                    return cur.fetchone()
        except Exception as e:
            print(f"Ошибка получения данных из БД: {e}")
            raise

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