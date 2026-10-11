-- Таблица для хранения результатов анализа фото
CREATE TABLE IF NOT EXISTS analysis_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    storage_filename VARCHAR(255) NOT NULL,
    upload_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Основные метрики
    overall_score FLOAT NOT NULL,
    verdict VARCHAR(100),

    -- Метрики резкости
    acf_score FLOAT,
    laplacian_global FLOAT,
    laplacian_local_median FLOAT,
    sobel_variance FLOAT,
    sharpness_index FLOAT,

    -- Метрики экспозиции
    brightness FLOAT,
    overexposed_pct FLOAT,
    underexposed_pct FLOAT,

    -- Метрики композиции
    fill_rate FLOAT,
    is_off_center BOOLEAN DEFAULT FALSE,
    object_found BOOLEAN DEFAULT TRUE,

    -- Проблемы и рекомендации
    issues JSONB,
    penalties JSONB,
    ai_recommendations TEXT,

    -- Информация о файле
    resolution VARCHAR(50),
    file_size_kb FLOAT
);

-- Индексы для ускорения запросов
CREATE INDEX idx_analysis_upload_date ON analysis_results(upload_date DESC);
CREATE INDEX idx_analysis_score ON analysis_results(overall_score);
CREATE INDEX idx_analysis_filename ON analysis_results(filename);

-- Таблица для статистики (агрегированные данные)
CREATE TABLE IF NOT EXISTS analysis_stats (
    id SERIAL PRIMARY KEY,
    stat_date DATE UNIQUE NOT NULL,
    total_analyses INTEGER DEFAULT 0,
    avg_score FLOAT,
    min_score FLOAT,
    max_score FLOAT
);