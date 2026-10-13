"""
Запуск всех тестов (задача 7.3) с сохранением протокола.

    docker exec qualityjpg_app python tests/run_tests.py

Тесты работают на отдельной БД qualityjpg_test и временной папке хранилища (см. testenv.py).
Протокол сохраняется в tests/results/test_report_<время>.txt
"""
import io
import os
import sys
import time
import unittest
from datetime import datetime

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTS_DIR)

import testenv  # noqa: E402  (до импорта модулей проекта)


class _Tee(io.TextIOBase):
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for stream in self.streams:
            stream.write(s)
        return len(s)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def main():
    buffer = io.StringIO()
    out = _Tee(sys.stderr, buffer)
    out.write(f"QualityJPG — протокол тестирования, {datetime.now():%d.%m.%Y %H:%M:%S}\n")
    out.write(f"Ollama: {'доступна' if testenv.ollama_available() else 'НЕДОСТУПНА (LLM-тесты пропущены)'}\n\n")

    suite = unittest.defaultTestLoader.discover(TESTS_DIR, pattern='test_*.py')
    started = time.perf_counter()
    result = unittest.TextTestRunner(stream=out, verbosity=2).run(suite)
    elapsed = time.perf_counter() - started

    out.write(f"\nИтого: {result.testsRun} тестов за {elapsed:.1f} с — "
              f"успешно {result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)}, "
              f"провалено {len(result.failures)}, ошибок {len(result.errors)}, пропущено {len(result.skipped)}\n")

    results_dir = os.path.join(TESTS_DIR, 'results')
    os.makedirs(results_dir, exist_ok=True)
    path = os.path.join(results_dir, f"test_report_{datetime.now():%Y%m%d_%H%M%S}.txt")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(buffer.getvalue())
    print(f"Протокол сохранён: {path}")

    testenv.cleanup()
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
