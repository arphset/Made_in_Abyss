def calculate_quality_score(analysis_result: dict) -> dict:
    score = 10.0
    penalties = []

    # 1. Размытие
    if analysis_result.get("is_blurry"):
        score -= 2.5
        penalties.append("Размытие: -2.5")

    # 2. Экспозиция (НЕ штрафуем дважды за темноту!)
    is_dark = analysis_result.get("is_dark", False)
    is_underexposed = analysis_result.get("is_underexposed", False)

    if is_dark and is_underexposed:
        # Оба флага — это одно и то же, штрафуем только один раз (больший)
        score -= 1.5
        penalties.append("Тёмная экспозиция: -1.5")
    elif is_dark:
        score -= 1.5
        penalties.append("Слишком темно: -1.5")
    elif is_underexposed:
        score -= 1.0
        penalties.append("Недосвет: -1.0")

    if analysis_result.get("is_overexposed"):
        score -= 1.5
        penalties.append(f"Пересвет ({analysis_result['overexposed_pct']:.1f}%): -1.5")

    if analysis_result.get("is_bright"):
        score -= 1.5
        penalties.append("Общий пересвет: -1.5")

    # 3. Заполнение кадра
    fill_rate = analysis_result.get("fill_rate", 0)
    if fill_rate < 0.15:
        score -= 2.0
        penalties.append(f"Заполнение {fill_rate*100:.0f}%: -2.0")
    elif fill_rate < 0.30:
        score -= 0.5
        penalties.append(f"Заполнение {fill_rate*100:.0f}%: -0.5")

    # 4. Композиция
    if analysis_result.get("is_off_center"):
        score -= 0.5
        penalties.append("Смещение от центра: -0.5")

    # 5. Товар не найден
    if not analysis_result.get("object_found", True):
        score -= 3.0
        penalties.append("Товар не найден: -3.0")

    score = max(1.0, min(10.0, score))

    if score >= 9.0:
        verdict = "Отлично"
        emoji = ""
    elif score >= 7.5:
        verdict = "Хорошо"
        emoji = "✅"
    elif score >= 6.0:
        verdict = "Удовлетворительно"
        emoji = "️"
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