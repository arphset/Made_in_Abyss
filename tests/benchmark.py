"""
Замер времени отклика (задача 7.1, требование R.01.01: ≤ 30 с для файлов до 10 МБ).

Прогоняет полный серверный конвейер на тестовых изображениях и синтетических
крупных файлах (~5 и ~10 МБ): сохранение в хранилище → CV-анализ → оценка → рекомендации Ollama.

Запуск внутри контейнера приложения:
    docker exec qualityjpg_app python tests/benchmark.py            # с Ollama
    docker exec qualityjpg_app python tests/benchmark.py --no-llm   # только CV
Результат печатается таблицей и сохраняется в tests/results/benchmark_<время>.json
"""
import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime

import cv2
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'ML&CV_Module'))

from main import analyze_image  # noqa: E402
from filters.score_calculator import calculate_quality_score  # noqa: E402
from ollama.ollama_access import LLM_ERROR_PREFIX, get_recommendations  # noqa: E402

LIMIT_SECONDS = 30.0
TEST_DIR = os.path.join(PROJECT_ROOT, 'test_jpegs')
RESULTS_DIR = os.path.join(PROJECT_ROOT, 'tests', 'results')


def make_large_jpeg(path: str, target_mb: float) -> None:
    """Синтетическое «тяжёлое» фото: градиент + шум, подбираем размер под нужный объём"""
    side = 2000
    while True:
        rng = np.random.default_rng(42)
        h, w = side * 3 // 4, side
        base = np.linspace(0, 255, w, dtype=np.float32)[None, :, None].repeat(h, 0).repeat(3, 2)
        noise = rng.normal(0, 40, (h, w, 3)).astype(np.float32)
        img = np.clip(base + noise, 0, 255).astype(np.uint8)
        cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        size_mb = os.path.getsize(path) / 1024 / 1024
        if size_mb >= target_mb * 0.9 or side > 9000:
            return
        side = int(side * (target_mb / size_mb) ** 0.5 * 1.02)


def run_case(path: str, use_llm: bool) -> dict:
    size_mb = os.path.getsize(path) / 1024 / 1024
    timings = {}

    t0 = time.perf_counter()
    with open(path, 'rb') as f:
        raw = f.read()
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    timings['decode'] = time.perf_counter() - t0

    t = time.perf_counter()
    result = analyze_image(path)
    timings['cv_analysis'] = time.perf_counter() - t

    t = time.perf_counter()
    score = calculate_quality_score(result)
    timings['score'] = time.perf_counter() - t

    timings['primary_report'] = time.perf_counter() - t0  # первичный результат (R.01.01)

    if use_llm:
        t = time.perf_counter()
        recs = get_recommendations(result)
        timings['llm'] = time.perf_counter() - t
        llm_ok = LLM_ERROR_PREFIX not in recs
    else:
        timings['llm'] = 0.0
        llm_ok = None

    timings['total'] = time.perf_counter() - t0
    return {
        'file': os.path.basename(path),
        'size_mb': round(size_mb, 2),
        'resolution': f"{img.shape[1]}x{img.shape[0]}",
        'score': score['score'],
        'llm_ok': llm_ok,
        **{k: round(v, 3) for k, v in timings.items()},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-llm', action='store_true', help='не вызывать Ollama')
    parser.add_argument('--label', default='', help='метка прогона (например, before/after)')
    args = parser.parse_args()

    files = sorted(
        os.path.join(TEST_DIR, f) for f in os.listdir(TEST_DIR)
        if f.lower().endswith(('.jpg', '.jpeg', '.png'))
    )
    tmp = tempfile.mkdtemp()
    for mb in (5, 10):
        path = os.path.join(tmp, f'synthetic_{mb}mb.jpg')
        make_large_jpeg(path, mb)
        files.append(path)

    rows = []
    for i, path in enumerate(files):
        row = run_case(path, use_llm=not args.no_llm)
        row['cold_start'] = i == 0
        rows.append(row)
        flag = '❗' if row['primary_report'] > LIMIT_SECONDS or row['total'] > LIMIT_SECONDS else '  '
        print(f"{flag} {row['file'][:24]:24} {row['size_mb']:6.2f} МБ {row['resolution']:>11} | "
              f"CV {row['cv_analysis']:6.2f} с | отчёт {row['primary_report']:6.2f} с | "
              f"LLM {row['llm']:6.2f} с | всего {row['total']:6.2f} с", flush=True)

    warm = [r for r in rows if not r['cold_start']]
    summary = {
        'label': args.label,
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'cases': len(rows),
        'cold_start_primary_s': rows[0]['primary_report'],
        'warm_primary_avg_s': round(statistics.mean(r['primary_report'] for r in warm), 3),
        'warm_primary_max_s': round(max(r['primary_report'] for r in warm), 3),
        'total_avg_s': round(statistics.mean(r['total'] for r in rows), 3),
        'total_max_s': round(max(r['total'] for r in rows), 3),
        'over_limit': sum(1 for r in rows if r['total'] > LIMIT_SECONDS),
        'limit_s': LIMIT_SECONDS,
    }
    print('\nИтог:', json.dumps(summary, ensure_ascii=False, indent=2))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, f"benchmark_{args.label or 'run'}_{datetime.now():%Y%m%d_%H%M%S}.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'summary': summary, 'rows': rows}, f, ensure_ascii=False, indent=2)
    print('Сохранено:', out)


if __name__ == '__main__':
    main()
