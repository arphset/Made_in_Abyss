"""Модульные тесты: пароли, файловое хранилище, расчёт оценки, форматирование отчёта"""
import os
import unittest

import cv2
import numpy as np

import testenv  # noqa: F401  (изолированное окружение)
import storage
from database.security import hash_password, verify_password
from filters.score_calculator import calculate_quality_score
from report_view import format_recommendations


class PasswordHashingTest(unittest.TestCase):
    """S.01.01: пароли хранятся только в виде хэша"""

    def test_hash_is_not_plain_and_salted(self):
        h1, h2 = hash_password('secret123'), hash_password('secret123')
        self.assertNotIn('secret123', h1)
        self.assertNotEqual(h1, h2, "одинаковые пароли должны давать разные хэши (соль)")

    def test_verify(self):
        stored = hash_password('secret123')
        self.assertTrue(verify_password('secret123', stored))
        self.assertFalse(verify_password('secret124', stored))
        self.assertFalse(verify_password('secret123', 'мусор'))
        self.assertFalse(verify_password('secret123', None))


class StorageTest(unittest.TestCase):
    """D.01.02 / 7.2: файлы под UUID, защита от подмены пути"""

    def setUp(self):
        img = np.full((120, 200, 3), 128, dtype=np.uint8)
        ok, buf = cv2.imencode('.jpg', img)
        self.raw = buf.tobytes()

    def test_save_original_keeps_bytes(self):
        path, name = storage.save_original('Фото товара.JPG', self.raw)
        self.assertTrue(name.endswith('.jpg'))
        self.assertEqual(os.path.dirname(path), storage.UPLOAD_DIR)
        with open(path, 'rb') as f:
            self.assertEqual(f.read(), self.raw, "оригинал должен сохраняться без перекодирования")
        self.assertEqual(storage.read_image(name).shape, (120, 200, 3))
        self.assertIsNotNone(storage.make_thumbnail(name))

    def test_path_traversal_rejected(self):
        for bad in ('../app.py', '/etc/passwd', '..\\x.jpg', 'not-a-uuid.jpg', '', None,
                    '00000000-0000-0000-0000-000000000000.exe'):
            self.assertIsNone(storage.read_image(bad), bad)

    def test_storage_overview(self):
        _, name = storage.save_original('a.jpg', self.raw)
        overview = storage.storage_overview([name, 'missing.jpg'])
        self.assertGreaterEqual(overview['files'], 1)
        self.assertEqual(overview['missing_files'], 1)


class ScoreCalculatorTest(unittest.TestCase):
    """F.01.03: итоговая оценка и вердикт"""

    def test_perfect_photo(self):
        score = calculate_quality_score({'sharpness_score': 0.9, 'fill_rate': 0.5, 'object_found': True})
        self.assertEqual(score['score'], 10.0)
        self.assertEqual(score['verdict'], 'Отлично')
        self.assertEqual(score['penalties'], [])

    def test_bad_photo_is_clamped(self):
        score = calculate_quality_score({
            'sharpness_score': 0.1, 'is_motion_blur': True, 'is_dark': True, 'is_overexposed': True,
            'is_bright': True, 'object_found': False, 'is_off_center': True,
        })
        self.assertEqual(score['score'], 1.0)
        self.assertEqual(score['verdict'], 'Критично')
        self.assertGreaterEqual(len(score['penalties']), 5)


class FormatRecommendationsTest(unittest.TestCase):
    def test_markdown_is_cleaned(self):
        html = format_recommendations("## Рекомендации:\n**1. Добавьте свет**\nЯркость: 120")
        self.assertIn('<h4', html)
        self.assertIn('1. Добавьте свет', html)
        self.assertNotIn('**', html)
        self.assertEqual(format_recommendations(''), '')


if __name__ == '__main__':
    unittest.main()
