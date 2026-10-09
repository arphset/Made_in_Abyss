def calculate_quality_score(analysis_result: dict) -> dict:
    """
    Рассчитывает итоговую оценку качества фото по 10-балльной шкале.
    Смягчённые штрафы, без дублирования за темноту.
    """
    score = 10.0
    penalties = []

    # 1. РАЗМЫТИЕ с мягким переходом
    sharpness_score = analysis_result.get("sharpness_score", 1.0)
    is_blurry = (
        analysis_result.get("is_blurry", False) or
        (sharpness_score < 0.50)
    )

    if sharpness_score < 0.50:
        # Полное размытие
        score -= 3.5
        penalties.append("Размытие: -3.5")
    elif sharpness_score < 0.70:
        # МЯГКИЙ переход: максимум -2.0 вместо -3.5
        penalty = 2.0 * (0.70 - sharpness_score) / 0.20
        penalty = round(penalty, 1)
        score -= penalty
        penalties.append(f"Пограничная чёткость: -{penalty}")

    # 2. MOTION BLUR
    if analysis_result.get("is_motion_blur", False):
        score -= 1.5
        penalties.append("Смаз движения: -1.5")

    # 3. ЭКСПОЗИЦИЯ (БЕЗ ДУБЛИРОВАНИЯ!)
    is_dark = analysis_result.get("is_dark", False)
    is_underexposed = analysis_result.get("is_underexposed", False)
    is_overexposed = analysis_result.get("is_overexposed", False)
    is_bright = analysis_result.get("is_bright", False)

    # Если и dark, и underexposed — это одно и то же, штрафуем один раз (больший)
    if is_dark and is_underexposed:
        score -= 1.5
        penalties.append("Тёмная экспозиция: -1.5")
    elif is_dark:
        score -= 1.5
        penalties.append("Слишком темно: -1.5")
    elif is_underexposed:
        score -= 1.0
        penalties.append("Недосвет: -1.0")

    if is_overexposed:
        score -= 1.5
        penalties.append(f"Пересвет ({analysis_result.get('overexposed_pct', 0):.1f}%): -1.5")

    if is_bright:
        score -= 1.5
        penalties.append("Общий пересвет: -1.5")

    # 4. ЗАПОЛНЕНИЕ КАДРА
    fill_rate = analysis_result.get("fill_rate", 0)
    try:
        fill_rate = float(fill_rate)
    except (ValueError, TypeError):
        fill_rate = 0

    object_found = analysis_result.get("object_found", True)

    if not object_found:
        score -= 3.0
        penalties.append("Товар не найден: -3.0")
    elif fill_rate < 0.10:
        score -= 2.5
        penalties.append(f"Заполнение {fill_rate*100:.0f}%: -2.5")
    elif fill_rate < 0.20:
        score -= 1.5
        penalties.append(f"Заполнение {fill_rate*100:.0f}%: -1.5")
    elif fill_rate < 0.30:
        score -= 0.5
        penalties.append(f"Заполнение {fill_rate*100:.0f}%: -0.5")

    # 5. КОМПОЗИЦИЯ
    if analysis_result.get("is_off_center", False):
        score -= 0.5
        penalties.append("Смещение от центра: -0.5")

    # Ограничиваем диапазон [1.0, 10.0]
    score = max(1.0, min(10.0, score))

    # Текстовый вердикт
    if score >= 9.0:
        verdict = "Отлично"
        emoji = "🏆"
    elif score >= 7.5:
        verdict = "Хорошо"
        emoji = "✅"
    elif score >= 6.0:
        verdict = "Удовлетворительно"
        emoji = "⚠️"
    elif score >= 4.0:
        verdict = "Плохо"
        emoji = "❌"
    else:
        verdict = "Критично"
        emoji = "🚫"

    return {
        "score": round(score, 1),
        "verdict": verdict,
        "emoji": emoji,
        "penalties": penalties,
        "max_score": 10.0
    }