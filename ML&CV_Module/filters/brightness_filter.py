import numpy as np
import cv2


def check_brightness(image):
    """Проверка яркости и экспозиции"""
    gray_uint8 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray_uint8.shape
    total_pixels = h * w

    brightness = np.mean(gray_uint8)

    # Проверка общей яркости
    is_dark = brightness < 40
    is_bright = brightness > 220
    light_status = "ТЕМНО" if is_dark else ("ПЕРЕСВЕТ" if is_bright else "ОК")
    print(f"[2] Средняя яркость: {brightness:.2f} -> {light_status}")

    # Гистограмма для проверки пересветов и недосветов
    hist = cv2.calcHist([gray_uint8], [0], None, [256], [0, 256])

    overexposed_pixels = np.sum(hist[240:256])
    overexposed_pct = (overexposed_pixels / total_pixels) * 100

    underexposed_pixels = np.sum(hist[0:15])
    underexposed_pct = (underexposed_pixels / total_pixels) * 100

    is_overexposed = overexposed_pct > 1.0
    is_underexposed = underexposed_pct > 5.0

    print(f"[2.1] Гистограмма: Пересвет {overexposed_pct:.1f}%, Недосвет {underexposed_pct:.1f}%")

    return {
        "brightness": brightness,
        "overexposed_pct": overexposed_pct,
        "underexposed_pct": underexposed_pct,
        "is_dark": is_dark,
        "is_bright": is_bright,
        "is_overexposed": is_overexposed,
        "is_underexposed": is_underexposed
    }