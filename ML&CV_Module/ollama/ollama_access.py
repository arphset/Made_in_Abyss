import os
import httpx
from openai import OpenAI

# ==========================================
# ПРИНУДИТЕЛЬНО ОТКЛЮЧАЕМ ПРОКСИ
# ==========================================
# 1. Удаляем переменные окружения
for proxy_var in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_var, None)

def get_recommendations(data: dict):
    """Генерирует рекомендации через локальную Ollama"""

    if "error" in data:
        return f"❌ Анализ не выполнен: {data['error']}. Проверьте имя файла и путь."

    def safe_fmt(value, format_spec):
        try:
            if value is None:
                return "N/A"
            return f"{float(value):{format_spec}}"
        except (ValueError, TypeError):
            return "N/A"

    fill_rate_val = data.get('fill_rate')
    fill_rate_display = safe_fmt(fill_rate_val * 100 if fill_rate_val is not None else None, '.1f')

    metrics_text = (
        f"ACF (автокорреляция, размытие): {safe_fmt(data.get('acf_score'), '.3f')}\n"
        f"Лапласиан глобальный (текстура): {safe_fmt(data.get('laplacian_var'), '.0f')}\n"
        f"Лапласиан локальный (медиана по блокам): {safe_fmt(data.get('median_laplacian'), '.0f')}\n"
        f"Вариация градиента Собеля (чёткость краёв): {safe_fmt(data.get('sobel_var'), '.0f')}\n"
        f"Индекс чёткости (0.0-1.0): {safe_fmt(data.get('sharpness_score'), '.2f')}\n"
        f"Яркость: {safe_fmt(data.get('brightness'), '.1f')}\n"
        f"Пересвет: {safe_fmt(data.get('overexposed_pct'), '.1f')}%\n"
        f"Недосвет: {safe_fmt(data.get('underexposed_pct'), '.1f')}%\n"
        f"Заполнение кадра: {fill_rate_display}%\n"
        f"Смещение от центра: {'Да' if data.get('is_off_center') else 'Нет'}\n"
        f"Товар найден: {'Да' if data.get('object_found', True) else 'Нет'}"
    )

    issues = data.get('issues', [])
    issues_text = ", ".join(issues) if issues else "Проблем не выявлено"

    sharpness_val = safe_fmt(data.get('sharpness_score'), '.2f')

    prompt = f"""
Ты эксперт по фотографии для маркетплейсов (Wildberries/Ozon).
Анализируй метрики и давай краткий отчёт. СТРОГО следуй формату.

ТЕХНИЧЕСКИЕ МЕТРИКИ ФОТО:
{metrics_text}

ВЫЯВЛЕННЫЕ ПРОБЛЕМЫ: {issues_text}

ИНСТРУКЦИЯ ПО ОЦЕНКЕ ЧЁТКОСТИ:
- Индекс чёткости {sharpness_val} — это КОНКРЕТНОЕ значение, не диапазон.
- Если значение > 0.7: напиши "Фото чёткое (индекс чёткости {sharpness_val})"
- Если значение 0.45-0.7: напиши "Приемлемая чёткость (индекс чёткости {sharpness_val})"
- Если значение < 0.45: напиши "Фото размытое (индекс чёткости {sharpness_val})"
- НИКОГДА не выдумывай диапазоны. Используй ТОЛЬКО реальное значение из метрик.

ПРИМЕР ПРАВИЛЬНОГО ОТВЕТА:
---
Метрики фото:
ACF (автокорреляция, размытие): 0.300
Лапласиан глобальный (текстура): 1500
Лапласиан локальный (медиана по блокам): 800
Вариация градиента Собеля (чёткость краёв): 2000
Индекс чёткости (0.0-1.0): 0.85
Яркость: 120.0
Пересвет: 0.5%
Недосвет: 2.0%
Заполнение кадра: 45.0%
Смещение от центра: Нет
Товар найден: Да

Оценка качества:
Фото чёткое (индекс чёткости 0.85). Товар хорошо виден, экспозиция в норме.

Рекомендации:
1. Фото готово к публикации.
2. Можно немного увеличить заполнение кадра для лучшего восприятия товара.
3. Попробуйте добавить больше деталей в фон для контекста.
---

ВАЖНЫЕ ПРАВИЛА:
- ОТВЕЧАЙ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ. Не используй латиницу, китайские иероглифы или другие языки.
- НЕ используй символы #, *, `, _ в ответе.
- НЕ пиши технические предупреждения или ошибки.
- НЕ отвечай в форме диалога ("Конечно!", "Вот ваш отчёт", "Здравствуйте").
- НЕ используй английские слова (например, "post-processing", "marketplace", "fill rate"). Пиши только по-русски.
- Пиши кратко, по делу.
- Опирайся ТОЛЬКО на переданные метрики.

ТВОЙ ОТВЕТ (строго в том же формате, что и пример выше):
"""

    # КЛИЕНТ БЕЗ ПРОКСИ — trust_env=False игнорирует ВСЕ системные прокси
    client = OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        http_client=httpx.Client(
            timeout=60.0,
            trust_env=False  # ← КЛЮЧЕВОЙ ПАРАМЕТР: игнорирует HTTP_PROXY, ALL_PROXY и т.д.
        )
    )

    try:
        response = client.chat.completions.create(
            model="qwen2.5:3b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            timeout=60
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Ошибка связи с Ollama: {str(e)}. Проверьте, запущен ли сервер."