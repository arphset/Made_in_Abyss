import numpy as np
import cv2

def check_brightness(image):
    """
    Проверка экспозиции с адаптивными порогами для low-key/high-key фото.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    brightness = float(np.mean(gray))

    # АДАПТИВНЫЕ ПОРОГИ
    # Для тёмных фото (low-key) пересвет только при экстремально ярких пикселях
    # Для светлых фото (high-key) недосвет только при экстремально тёмных

    if brightness < 50:
        # Low-key фото: пересвет только при > 250, недосвет при < 10
        overexposed_threshold = 250
        underexposed_threshold = 10
    elif brightness > 200:
        # High-key фото: пересвет при > 240, недосвет при < 30
        overexposed_threshold = 240
        underexposed_threshold = 30
    else:
        # Нормальное фото
        overexposed_threshold = 240
        underexposed_threshold = 15

    overexposed_pixels = np.sum(gray > overexposed_threshold)
    underexposed_pixels = np.sum(gray < underexposed_threshold)

    overexposed_pct = (overexposed_pixels / (h * w)) * 100
    underexposed_pct = (underexposed_pixels / (h * w)) * 100

    is_overexposed = overexposed_pct > 1.0
    is_underexposed = underexposed_pct > 5.0

    # Общая оценка яркости
    is_dark = brightness < 40
    is_bright = brightness > 220

    print(f"[2] Средняя яркость: {brightness:.2f} -> {'ТЕМНО' if is_dark else ('СВЕТЛО' if is_bright else 'ОК')}")
    print(f"[2.1] Гистограмма: Пересвет {overexposed_pct:.1f}%, Недосвет {underexposed_pct:.1f}%")

    return {
        "brightness": brightness,
        "overexposed_pct": overexposed_pct,
        "underexposed_pct": underexposed_pct,
        "is_overexposed": is_overexposed,
        "is_underexposed": is_underexposed,
        "is_dark": is_dark,
        "is_bright": is_bright
    }