import os
import httpx
from openai import OpenAI


# Отключаем прокси
for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_var, None)

# Адрес Ollama из переменной окружения
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "60"))
# Модель держится в памяти Ollama между запросами (иначе выгружается через 5 минут простоя)
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "60m")
# Ограничение длины ответа: оценка + 3–5 рекомендаций укладываются с запасом
MAX_TOKENS = int(os.environ.get("OLLAMA_MAX_TOKENS", "350"))

LLM_ERROR_PREFIX = "⚠️ Ошибка связи с Ollama"

# КЛИЕНТ БЕЗ ПРОКСИ — trust_env=False игнорирует ВСЕ системные прокси.
# Создаётся один раз: переиспользует HTTP-соединение между запросами.
_client = OpenAI(
    base_url=f"{OLLAMA_HOST}/v1",
    api_key="ollama",
    http_client=httpx.Client(timeout=OLLAMA_TIMEOUT, trust_env=False),
)


def _safe_fmt(value, format_spec):
    try:
        if value is None:
            return "N/A"
        return f"{float(value):{format_spec}}"
    except (ValueError, TypeError):
        return "N/A"


def _build_prompt(data: dict):
    """
    Возвращает (блок метрик, промпт).
    Блок метрик формируется кодом и подставляется в начало отчёта — раньше LLM переписывала
    его сама (~150 лишних токенов на каждый запрос, основная часть времени ответа на CPU).
    """
    fill_rate_val = data.get('fill_rate')
    fill_rate_display = _safe_fmt(fill_rate_val * 100 if fill_rate_val is not None else None, '.1f')

    metrics_text = (
        f"ACF (автокорреляция, размытие): {_safe_fmt(data.get('acf_score'), '.3f')}\n"
        f"Лапласиан глобальный (текстура): {_safe_fmt(data.get('laplacian_var'), '.0f')}\n"
        f"Лапласиан локальный (медиана по блокам): {_safe_fmt(data.get('median_laplacian'), '.0f')}\n"
        f"Вариация градиента Собеля (чёткость краёв): {_safe_fmt(data.get('sobel_var'), '.0f')}\n"
        f"Индекс чёткости (0.0-1.0): {_safe_fmt(data.get('sharpness_score'), '.2f')}\n"
        f"Яркость: {_safe_fmt(data.get('brightness'), '.1f')}\n"
        f"Пересвет: {_safe_fmt(data.get('overexposed_pct'), '.1f')}%\n"
        f"Недосвет: {_safe_fmt(data.get('underexposed_pct'), '.1f')}%\n"
        f"Заполнение кадра: {fill_rate_display}%\n"
        f"Смещение от центра: {'Да' if data.get('is_off_center') else 'Нет'}\n"
        f"Товар найден: {'Да' if data.get('object_found', True) else 'Нет'}"
    )

    issues = data.get('issues', [])
    issues_text = ", ".join(issues) if issues else "Проблем не выявлено"

    sharpness_val = _safe_fmt(data.get('sharpness_score'), '.2f')

    # Определяем вердикт по чёткости ПРЯМО в Python
    if float(data.get('sharpness_score', 0)) > 0.7:
        sharpness_verdict = f"Фото чёткое (индекс чёткости {sharpness_val})"
    elif float(data.get('sharpness_score', 0)) > 0.50:
        sharpness_verdict = f"Приемлемая чёткость (индекс чёткости {sharpness_val})"
    else:
        sharpness_verdict = f"Фото размытое (индекс чёткости {sharpness_val})"

    # Определяем комментарий по заполнению
    try:
        fill_rate_val = float(data.get('fill_rate', 0))
    except (TypeError, ValueError):
        fill_rate_val = 0

    if fill_rate_val >= 0.30:
        fill_comment = "Заполнение кадра в норме (>= 30%). НЕ упоминай заполнение как проблему."
    elif fill_rate_val >= 0.20:
        fill_comment = f"Заполнение кадра {fill_rate_val*100:.1f}% — можно увеличить для лучшего восприятия товара."
    else:
        fill_comment = f"Заполнение кадра {fill_rate_val*100:.1f}% — критически мало, товар плохо виден."

    prompt = f"""Ты эксперт по фотографии для маркетплейсов. Дай краткий отчёт строго по формату ниже. НЕ повторяй инструкции и метрики. НЕ пиши заголовки разделов типа "ШАБЛОН" или "ПРАВИЛА".

МЕТРИКИ:
{metrics_text}

ПРОБЛЕМЫ: {issues_text}

ФРАЗА О ЧЁТКОСТИ (используй её как есть в разделе "Оценка качества"):
{sharpness_verdict}

КОММЕНТАРИЙ ПО ЗАПОЛНЕНИЮ (учти в рекомендациях):
{fill_comment}

ФОРМАТ ОТВЕТА (пример):

Оценка качества:
Фото чёткое (индекс чёткости 0.85). Товар хорошо виден, экспозиция в норме.

Рекомендации:
1. Фото готово к публикации.
2. Можно немного увеличить заполнение кадра.
3. Попробуйте добавить больше деталей в фон.

ТВОЙ ОТВЕТ (начни со строки "Оценка качества:", точно в таком же формате, только с реальными данными из МЕТРИКИ и ПРОБЛЕМЫ выше):"""

    return f"Метрики фото:\n{metrics_text}\n\n", prompt


def stream_recommendations(data: dict):
    """
    Генератор текста рекомендаций по частям (для потокового вывода в интерфейсе).
    Первым фрагментом отдаётся блок метрик, затем — ответ модели по мере генерации.
    Ошибки не пробрасываются: возвращается понятное сообщение (R.01.03).
    """
    if "error" in data:
        yield f"❌ Анализ не выполнен: {data['error']}. Проверьте имя файла и путь."
        return

    metrics_block, prompt = _build_prompt(data)
    yield metrics_block

    try:
        stream = _client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=MAX_TOKENS,
            timeout=OLLAMA_TIMEOUT,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        yield f"\n{LLM_ERROR_PREFIX}: {str(e)}. Проверьте, запущен ли сервер."


def get_recommendations(data: dict):
    """Генерирует рекомендации через локальную Ollama (целиком, без потока)"""
    return "".join(stream_recommendations(data))


def warmup():
    """Загрузить модель в память Ollama заранее, чтобы первый запрос не ждал холодного старта"""
    try:
        httpx.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": "", "keep_alive": OLLAMA_KEEP_ALIVE},
            timeout=OLLAMA_TIMEOUT,
            trust_env=False,
        )
        return True
    except Exception as e:
        print(f"Ollama недоступна при прогреве: {e}")
        return False
