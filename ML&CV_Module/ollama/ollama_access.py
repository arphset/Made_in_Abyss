from openai import OpenAI

def get_recommendations(data: dict):
    """Генерирует рекомендации через локальную Ollama"""

    # 1. ПРОВЕРКА НА ОШИБКУ (Если картинка не найдена, дальше не идём)
    if "error" in data:
        return f"❌ Анализ не выполнен: {data['error']}. Проверьте имя файла и путь."

    # 2. БЕЗОПАСНОЕ форматирование (защита от типа 'str' вместо 'float')
        # 2. БЕЗОПАСНОЕ форматирование (теперь работает и с numpy типами)
    def safe_fmt(value, format_spec):
        try:
            # Принудительно превращаем в обычный float.
            # Это решает проблему с numpy.float64
            return f"{float(value):{format_spec}}"
        except (ValueError, TypeError):
            return "N/A"

    # Собираем метрики безопасно
    metrics_text = (
        f"ACF (размытие): {safe_fmt(data.get('acf_score'), '.3f')}\n"
        f"Лапласиан (текстура): {safe_fmt(data.get('laplacian_var'), '.0f')}\n"
        f"Яркость: {safe_fmt(data.get('brightness'), '.1f')}\n"
        f"Пересвет: {safe_fmt(data.get('overexposed_pct'), '.1f')}%\n"
        f"Заполнение кадра: {safe_fmt(data.get('fill_rate') * 100 if isinstance(data.get('fill_rate'), (int, float)) else None, '.1f')}%\n"
        f"Смещение от центра: {'Да' if data.get('is_off_center') else 'Нет'}"
    )

    issues = data.get('issues', [])
    issues_text = ", ".join(issues) if issues else "Проблем не выявлено"

    prompt = f"""
    Ты эксперт по фотографии для маркетплейсов (Wildberries/Ozon).

    ТЕХНИЧЕСКИЕ МЕТРИКИ ФОТО:
    {metrics_text}

    ВЫЯВЛЕННЫЕ ПРОБЛЕМЫ: {issues_text}

    ЗАДАЧА:
    Дай 3 конкретных совета, как перефоткать этот товар.
    - Если проблем нет, похвали фото и скажи, что можно публиковать.
    - Пиши кратко, по делу, используй эмодзи.
    - Опирайся ТОЛЬКО на переданные метрики.
    - Не забудь сделать мини-отчёт, написав метрики.
    - Не отвечай в форме диалога, просто сделай отчёт с советами, метриками.
    - Не используй в ответах символ #, а также *, а также технические предупреждения или ошибки не выводи, если не по теме.
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