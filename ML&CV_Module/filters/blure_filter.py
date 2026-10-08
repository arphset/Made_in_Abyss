import numpy as np
import cv2

def check_blur(image):
    """
    Улучшенная проверка на размытие с адаптивной логикой.
    Для тёмных/светлых фото использует другие метрики.
    """
    gray_float = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float64)
    gray_uint8 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray_float.shape

    # Проверяем яркость
    brightness = np.mean(gray_uint8)

    # ==========================================
    # 1. АВТОКОРРЕЛЯЦИЯ (ACF)
    # ==========================================
    mean_val = np.mean(gray_float)
    std_val = np.std(gray_float) + 1e-8
    gray_norm = (gray_float - mean_val) / std_val

    fft_img = np.fft.fft2(gray_norm)
    acf_full = np.fft.ifft2(fft_img * np.conj(fft_img)).real
    acf_full = np.fft.fftshift(acf_full)

    cy, cx = h // 2, w // 2
    acf_normalized = acf_full / (acf_full[cy, cx] + 1e-8)

    lag_5_h = acf_normalized[cy - 5, cx]
    lag_5_v = acf_normalized[cy, cx - 5]
    avg_lag_5 = (abs(lag_5_h) + abs(lag_5_v)) / 2

    # ==========================================
    # 2. ГЛОБАЛЬНЫЙ ЛАПЛАСИАН
    # ==========================================
    laplacian_var = cv2.Laplacian(gray_uint8, cv2.CV_64F).var()

    # ==========================================
    # 3. ЛОКАЛЬНЫЙ ЛАПЛАСИАН (МЕДИАНА ПО БЛОКАМ)
    # ==========================================
    block_size = 64
    local_laplacians = []

    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = gray_uint8[y:y+block_size, x:x+block_size]
            lap_var = cv2.Laplacian(block, cv2.CV_64F).var()
            local_laplacians.append(lap_var)

    median_laplacian = np.median(local_laplacians) if local_laplacians else laplacian_var

    # ==========================================
    # 4. ВАРИАЦИЯ СОБЕЛЯ
    # ==========================================
    sobelx = cv2.Sobel(gray_uint8, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray_uint8, cv2.CV_64F, 0, 1, ksize=3)
    sobel_magnitude = np.sqrt(sobelx**2 + sobely**2)
    sobel_var = np.var(sobel_magnitude)

    # ==========================================
    # 5. АДАПТИВНАЯ ЛОГИКА В ЗАВИСИМОСТИ ОТ ЯРКОСТИ
    # ==========================================

    if brightness < 40:
        # ОЧЕНЬ ТЁМНОЕ ФОТО (low-key)
        # ACF и локальный лапласиан врут из-за тёмного фона
        # Используем только глобальный лапласиан и Собель

        # Для тёмных фото пороги ниже
        lap_score = min(1.0, laplacian_var / 100.0)  # Порог 100 вместо 500
        sobel_score = min(1.0, sobel_var / 800.0)    # Порог 800 вместо 300

        # Веса: Лапласиан 40%, Собель 60%
        final_sharpness = 0.40 * lap_score + 0.60 * sobel_score

        method = "тёмное фото (Лапласиан + Собель)"

    elif brightness > 220:
        # ОЧЕНЬ СВЕТЛОЕ ФОТО (high-key)
        # Аналогично тёмному, но пороги другие
        lap_score = min(1.0, laplacian_var / 150.0)
        sobel_score = min(1.0, sobel_var / 1000.0)

        final_sharpness = 0.40 * lap_score + 0.60 * sobel_score

        method = "светлое фото (Лапласиан + Собель)"

    else:
        # НОРМАЛЬНАЯ ЯРКОСТЬ (40-220)
        # Используем все 4 метрики

        score_acf = max(0.0, 1.0 - (avg_lag_5 / 0.9))
        score_lap_global = min(1.0, laplacian_var / 500.0)
        score_lap_local = min(1.0, median_laplacian / 150.0)
        score_sobel = min(1.0, sobel_var / 300.0)

        final_sharpness = (
            0.20 * score_acf +
            0.20 * score_lap_global +
            0.35 * score_lap_local +
            0.25 * score_sobel
        )

        method = "нормальное фото (все метрики)"

    # Порог: если чёткость ниже 0.45, считаем размытым
    is_blurry_final = final_sharpness < 0.45

    print(f"[1] МЕТРИКИ ЧЁТКОСТИ:")
    print(f"    Яркость: {brightness:.0f}")
    print(f"    ACF: {avg_lag_5:.3f}")
    print(f"    Лапласиан (глоб): {laplacian_var:.0f}")
    print(f"    Лапласиан (лок):  {median_laplacian:.0f}")
    print(f"    Собель (вар):     {sobel_var:.0f}")
    print(f"    Метод: {method}")
    print(f"    >>> ИТОГОВЫЙ ИНДЕКС ЧЁТКОСТИ: {final_sharpness:.2f} -> {'РАЗМЫТО' if is_blurry_final else 'ЧЁТКО'}")

    return {
        "acf_score": avg_lag_5,
        "laplacian_var": laplacian_var,
        "median_laplacian": median_laplacian,
        "sobel_var": sobel_var,
        "brightness": brightness,
        "sharpness_score": final_sharpness,
        "is_blurry": is_blurry_final
    }