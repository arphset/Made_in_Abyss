"""
Интеграционный тест полного сценария (задача 7.3):
регистрация продавца → загрузка фото → сохранение в хранилище → ML/CV-анализ → рекомендации Ollama →
запись в БД → отчёт продавцу → недоступность чужому продавцу → просмотр администратором → статистика/журнал.
Повторяет шаги диаграммы последовательностей «Загрузка и анализ фото» и «Просмотр статистики».
"""
import os
import time
import unittest
import uuid
from datetime import date, timedelta

import cv2

import testenv
import storage
from database import db_repo
from main import analyze_image
from filters.score_calculator import calculate_quality_score
from ollama.ollama_access import LLM_ERROR_PREFIX, get_recommendations

PERIOD = (date.today() - timedelta(days=1), date.today() + timedelta(days=1))
RESPONSE_LIMIT_S = 30.0


class FullScenarioTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        images = sorted(f for f in os.listdir(testenv.TEST_IMAGES_DIR) if f.lower().endswith(('.jpg', '.png')))
        cls.image_name = images[0]
        with open(os.path.join(testenv.TEST_IMAGES_DIR, cls.image_name), 'rb') as f:
            cls.raw = f.read()

    def test_full_chain(self):
        # 1. Регистрация и вход продавца (S.01.01)
        login = 'seller_' + uuid.uuid4().hex[:6]
        db_repo.create_user(login, 'pass123')
        seller = db_repo.authenticate(login, 'pass123')
        self.assertEqual(seller['role'], 'seller')
        db_repo.log_action(seller['id'], 'login')

        # 2. Загрузка: оригинал в файловое хранилище под UUID (шаг 3 диаграммы, D.01.02)
        started = time.perf_counter()
        file_path, storage_name = storage.save_original(self.image_name, self.raw)
        self.assertTrue(os.path.isfile(file_path))
        db_repo.log_action(seller['id'], 'upload', f"{self.image_name} → {storage_name}")

        # 3. ML/CV-анализ и оценка (шаги 4–7, F.01.02)
        result = analyze_image(file_path)
        self.assertNotIn('error', result)
        score = calculate_quality_score(result)
        cv_ms = int((time.perf_counter() - started) * 1000)

        # 4. Рекомендации (F.02.02); без Ollama — понятное сообщение (R.01.03)
        llm_started = time.perf_counter()
        recs = get_recommendations(result)
        llm_ms = int((time.perf_counter() - llm_started) * 1000)
        total_ms = int((time.perf_counter() - started) * 1000)
        if testenv.ollama_available():
            self.assertNotIn(LLM_ERROR_PREFIX, recs)
            self.assertIn('Рекомендации', recs)
        self.assertLess(total_ms / 1000, RESPONSE_LIMIT_S, f"полный цикл занял {total_ms / 1000:.1f} с (R.01.01)")

        # 5. Запись в БД (шаг 8, D.01.01)
        img = cv2.imread(file_path)
        analysis_id = db_repo.save_analysis_result({
            'filename': self.image_name,
            'storage_filename': storage_name,
            'user_id': seller['id'],
            'overall_score': score['score'],
            'verdict': score['verdict'],
            'metrics': {
                'sharpness': {'acf_score': result['acf_score'], 'sharpness_index': result['sharpness_score']},
                'exposure': {'brightness': result['brightness']},
                'composition': {'fill_rate_pct': result['fill_rate'] * 100, 'object_found': result['object_found']},
            },
            'summary': {'issues': result['issues']},
            'penalties': score['penalties'],
            'ai_recommendations': recs,
            'timings': {'cv_ms': cv_ms, 'llm_ms': llm_ms, 'total_ms': total_ms},
            'file_info': {'resolution': f"{img.shape[1]}x{img.shape[0]}", 'file_size_kb': len(self.raw) / 1024},
        })
        db_repo.log_action(seller['id'], 'analysis_ok', self.image_name, analysis_id)

        # 6. Отчёт продавцу: своя история и полный отчёт (F.01.03, S.01.03)
        history = db_repo.get_user_reports(seller['id'])
        self.assertEqual([str(r['id']) for r in history], [analysis_id])
        record = db_repo.get_analysis_by_id(analysis_id, requester=seller)
        self.assertEqual(record['overall_score'], score['score'])
        self.assertEqual(record['ai_recommendations'], recs)
        self.assertEqual(record['total_time_ms'], total_ms)
        self.assertIsNotNone(storage.read_image(record['storage_filename']), "файл связан с записью по UUID")

        # 7. Чужой продавец не видит ни запись, ни историю (S.01.03, 7.2)
        intruder = db_repo.create_user('intruder_' + uuid.uuid4().hex[:6], 'pass123')
        self.assertIsNone(db_repo.get_analysis_by_id(analysis_id, requester=intruder))
        self.assertEqual(db_repo.get_user_reports(intruder['id']), [])

        # 8. Администратор видит проверку, статистику и журнал (F.03.01, F.03.02)
        admin = testenv.admin_user()
        self.assertIsNotNone(db_repo.get_analysis_by_id(analysis_id, requester=admin))
        reports = db_repo.get_reports(*PERIOD, user_ids=[seller['id']], include_anonymous=False)
        self.assertEqual([r['login'] for r in reports], [login])
        self.assertGreaterEqual(db_repo.get_period_summary(*PERIOD)['total'], 1)
        top = {u['login']: u['checks'] for u in db_repo.get_top_users(*PERIOD)}
        self.assertEqual(top[login], 1)
        actions = [r['action'] for r in db_repo.get_activity_log(*PERIOD, user_ids=[seller['id']])]
        self.assertEqual(set(actions), {'login', 'upload', 'analysis_ok'})


if __name__ == '__main__':
    unittest.main()
