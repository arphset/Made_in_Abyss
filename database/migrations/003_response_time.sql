-- Спринт 4: замер времени отклика (задача 7.1, требование R.01.01 — не более 30 секунд)
-- cv_time_ms    — сохранение файла + CV-анализ (первичный отчёт)
-- llm_time_ms   — генерация рекомендаций Ollama
-- total_time_ms — от нажатия «Анализировать» до готового отчёта с рекомендациями
ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS cv_time_ms INTEGER;
ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS llm_time_ms INTEGER;
ALTER TABLE analysis_results ADD COLUMN IF NOT EXISTS total_time_ms INTEGER;
