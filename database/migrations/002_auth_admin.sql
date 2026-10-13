-- Спринт 3: аутентификация, роли, журнал действий (S.01.01, S.01.02, F.03.01)
-- Скрипт идемпотентный: выполняется и при первой инициализации контейнера БД,
-- и при каждом старте приложения (для уже существующих баз).

-- Пользователи системы (задача 4.1/5.1): роль seller или admin
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    login VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'seller' CHECK (role IN ('seller', 'admin')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE
);

-- Привязка проверки к пользователю (приватность истории S.01.03, активность F.03.01).
-- Записи, созданные до Спринта 3, остаются с user_id = NULL.
ALTER TABLE analysis_results
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_analysis_user ON analysis_results(user_id);

-- Журнал операций пользователей (вход, загрузка фото, анализ, ошибки, отказы в доступе)
CREATE TABLE IF NOT EXISTS activity_log (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(32) NOT NULL,
    details TEXT,
    analysis_id UUID REFERENCES analysis_results(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id);
