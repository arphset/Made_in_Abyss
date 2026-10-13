"""Тесты ML/CV-модуля и интеграции с Ollama (A.01.02, F.02.01, F.02.02, R.01.01, R.01.03)"""
import os
import tempfile
import time
import unittest

import cv2
import numpy as np

import testenv
from main import analyze_image
from filters.YOLO import get_model
from ollama.ollama_access import LLM_ERROR_PREFIX, get_recommendations, stream_recommendations

REQUIRED_KEYS = {
    'acf_score', 'laplacian_var', 'median_laplacian', 'sobel_var', 'sharpness_score', 'brightness',
    'overexposed_pct', 'underexposed_pct', 'fill_rate', 'is_off_center', 'object_found', 'issues',
}


def sample_images():
    return sorted(
        os.path.join(testenv.TEST_IMAGES_DIR, f) for f in os.listdir(testenv.TEST_IMAGES_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    )


class CvAnalysisTest(unittest.TestCase):

    def test_all_sample_images_analyzed(self):
        images = sample_images()
        self.assertGreater(len(images), 0, "нет тестовых изображений в test_jpegs/")
        for path in images:
            with self.subTest(image=os.path.basename(path)):
                result = analyze_image(path)
                self.assertNotIn('error', result)
                self.assertTrue(REQUIRED_KEYS <= result.keys(), REQUIRED_KEYS - result.keys())
                self.assertIsInstance(result['issues'], list)
                self.assertGreaterEqual(result['fill_rate'], 0)

    def test_missing_file_returns_error_instead_of_crash(self):
        """R.01.03: сбой анализа — понятное сообщение, а не исключение"""
        result = analyze_image('/nonexistent/photo.jpg')
        self.assertIn('error', result)

    def test_yolo_model_loaded_once(self):
        """7.1: модель кэшируется, а не грузится с диска на каждый анализ"""
        self.assertIs(get_model(), get_model())

    def test_10mb_image_primary_report_within_limit(self):
        """R.01.01: первичный отчёт для файла ~10 МБ — с большим запасом до 30 с"""
        rng = np.random.default_rng(0)
        img = np.clip(rng.normal(128, 50, (3000, 4000, 3)), 0, 255).astype(np.uint8)
        path = os.path.join(tempfile.mkdtemp(), 'big.jpg')
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 97])
        size_mb = os.path.getsize(path) / 1024 / 1024
        self.assertGreater(size_mb, 8)

        started = time.perf_counter()
        result = analyze_image(path)
        elapsed = time.perf_counter() - started
        self.assertNotIn('error', result)
        self.assertLess(elapsed, 15, f"CV-анализ {size_mb:.1f} МБ занял {elapsed:.1f} с")


@unittest.skipUnless(testenv.ollama_available(), "Ollama недоступна")
class OllamaRecommendationsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = analyze_image(sample_images()[0])

    def test_recommendations_format_and_time(self):
        started = time.perf_counter()
        recs = get_recommendations(self.result)
        elapsed = time.perf_counter() - started
        self.assertNotIn(LLM_ERROR_PREFIX, recs)
        self.assertTrue(recs.startswith('Метрики фото:'), "блок метрик подставляется кодом")
        self.assertIn('Рекомендации', recs)
        self.assertLess(elapsed, 30, f"рекомендации заняли {elapsed:.1f} с")

    def test_stream_first_chunk_is_immediate(self):
        """Потоковый вывод: блок метрик отдаётся сразу, без ожидания LLM"""
        stream = stream_recommendations(self.result)
        started = time.perf_counter()
        first = next(stream)
        self.assertLess(time.perf_counter() - started, 0.5)
        self.assertTrue(first.startswith('Метрики фото:'))
        rest = ''.join(stream)
        self.assertTrue(rest.strip())


class OllamaFailureTest(unittest.TestCase):

    def test_unreachable_ollama_gives_readable_message(self):
        """R.01.03: недоступность LLM не роняет приложение"""
        import ollama.ollama_access as oa
        import httpx
        from openai import OpenAI
        original = oa._client
        oa._client = OpenAI(base_url="http://127.0.0.1:9/v1", api_key="x",
                            http_client=httpx.Client(timeout=2, trust_env=False), max_retries=0)
        try:
            recs = get_recommendations(analyze_image(sample_images()[0]))
        finally:
            oa._client = original
        self.assertIn(LLM_ERROR_PREFIX, recs)
        self.assertTrue(recs.startswith('Метрики фото:'))

    def test_analysis_error_passthrough(self):
        self.assertTrue(get_recommendations({'error': 'Картинка не найдена'}).startswith('❌'))


if __name__ == '__main__':
    unittest.main()
