from openai import OpenAI

def get_recommendations(data: dict):
    """Генерирует рекомендации через локальную Ollama"""

    # 1. ПРОВЕРКА НА ОШИБКУ
    if "error" in data:
        return f"❌ Анализ не выполнен: {data['error']}. Проверьте имя файла и путь."

    # 2. БЕЗОПАСНОЕ форматирование (защита от numpy типов)
    def safe_fmt(value, format_spec):
        try:
            return f"{float(value):{format_spec}}"
        except (ValueError, TypeError):
            return "N/A"

    # Собираем метрики
    fill_rate_val = data.get('fill_rate')
    fill_rate_display = safe_fmt(fill_rate_val * 100 if fill_rate_val is not None else None, '.1f')

    metrics_text = (
        f"ACF (размытие): {safe_fmt(data.get('acf_score'), '.3f')}\n"
        f"Лапласиан (текстура): {safe_fmt(data.get('laplacian_var'), '.0f')}\n"
        f"Яркость: {safe_fmt(data.get('brightness'), '.1f')}\n"
        f"Пересвет: {safe_fmt(data.get('overexposed_pct'), '.1f')}%\n"
        f"Заполнение кадра: {fill_rate_display}%\n"
        f"Смещение от центра: {'Да' if data.get('is_off_center') else 'Нет'}"
    )

    issues = data.get('issues', [])
    issues_text = ", ".join(issues) if issues else "Проблем не выявлено"

    # 3. ПРОМПТ (изначальный + корректировки)
    prompt = f"""
Ты эксперт по фотографии для маркетплейсов (Wildberries/Ozon).

ТЕХНИЧЕСКИЕ МЕТРИКИ ФОТО:
{metrics_text}

ВЫЯВЛЕННЫЕ ПРОБЛЕМЫ: {issues_text}

ЗАДАЧА:
Составь краткий отчёт о качестве фото.

СТРУКТУРА ОТВЕТА (строго соблюдай):

1. Заголовок: "Метрики фото:"
2. Перечисли все метрики из раздела "ТЕХНИЧЕСКИЕ МЕТРИКИ ФОТО" в том же формате.
3. Заголовок: "Оценка качества:"
4. Дай честную оценку фото на основе метрик и проблем (1-2 предложения).
5. Заголовок: "Советы:"
6. Дай 2-3 конкретных совета по улучшению (если проблем нет — похвали и скажи, что можно публиковать).

ВАЖНЫЕ ПРАВИЛА:
- НЕ используй символы #, *, `, _ в ответе.
- НЕ дублируй метрики — выведи их ТОЛЬКО ОДИН РАЗ в разделе "Метрики фото:".
- НЕ пиши технические предупреждения или ошибки.
- НЕ отвечай в форме диалога ("Конечно!", "Вот ваш отчёт").
- Пиши кратко, по делу, на русском языке.
- Опирайся ТОЛЬКО на переданные метрики.
"""

    client = OpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama"
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