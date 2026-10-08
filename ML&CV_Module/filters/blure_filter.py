import numpy as np
import cv2

def check_blur(image):
    """Улучшенная проверка на размытие"""
    gray_float = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float64)
    gray_uint8 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray_float.shape

    # Нормализуем яркость
    mean_val = np.mean(gray_float)
    std_val = np.std(gray_float) + 1e-8
    gray_norm = (gray_float - mean_val) / std_val

    # 1. Автокорреляция (глобальная оценка)
    fft_img = np.fft.fft2(gray_norm)
    acf_full = np.fft.ifft2(fft_img * np.conj(fft_img)).real
    acf_full = np.fft.fftshift(acf_full)

    cy, cx = h // 2, w // 2
    acf_normalized = acf_full / (acf_full[cy, cx] + 1e-8)

    lag_5_h = acf_normalized[cy - 5, cx]
    lag_5_v = acf_normalized[cy, cx - 5]
    avg_lag_5 = (abs(lag_5_h) + abs(lag_5_v)) / 2

    # 2. Глобальный Лапласиан
    laplacian_var = cv2.Laplacian(gray_uint8, cv2.CV_64F).var()

    # 3. НОВЫЙ АНАЛИЗ: Локальный Лапласиан по блокам
    # Разбиваем фото на блоки 8x8 и считаем лапласиан для каждого
    block_size = 64
    local_laplacians = []

    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = gray_uint8[y:y+block_size, x:x+block_size]
            lap_var = cv2.Laplacian(block, cv2.CV_64F).var()
            local_laplacians.append(lap_var)

    # Используем МЕДИАНУ вместо среднего (устойчива к выбросам)
    median_laplacian = np.median(local_laplacians) if local_laplacians else laplacian_var

    # 4. НОВЫЙ АНАЛИЗ: Высокочастотная энергия через FFT
    magnitude_spectrum = np.abs(fft_img)

    # Создаём маску для высоких частот (внешняя область спектра)
    mask = np.ones((h, w), dtype=np.uint8)
    cv2.circle(mask, (cx, cy), min(h, w) // 8, 0, -1)  # Вырезаем центр (низкие частоты)

    high_freq_energy = np.sum(magnitude_spectrum * mask)
    total_energy = np.sum(magnitude_spectrum)
    high_freq_ratio = high_freq_energy / (total_energy + 1e-8)

    # 5. КОМБИНИРОВАННАЯ ОЦЕНКА РАЗМЫТИЯ
    # Нормализуем метрики в диапазон 0-1
    acf_score = avg_lag_5  # 0-1, чем выше — тем размытее

    # Лапласиан: нормализуем относительно типичных значений
    # Для чёткого фото: 500-2000, для размытого: 0-100
    lap_score = min(laplacian_var / 1000, 1.0)  # 0-1, чем выше — тем чётче
    median_lap_score = min(median_laplacian / 500, 1.0)

    # Высокочастотная энергия: для чёткого фото > 0.1, для размытого < 0.05
    hf_score = min(high_freq_ratio * 10, 1.0)  # 0-1, чем выше — тем чётче

    # Итоговый score размытия (0 = чётко, 1 = размыто)
    # ACF даёт 40% веса, Лапласиан 30%, медиана 20%, HF 10%
    blur_score = (
        acf_score * 0.4 +
        (1 - lap_score) * 0.3 +
        (1 - median_lap_score) * 0.2 +
        (1 - hf_score) * 0.1
    )

    # Порог: если blur_score > 0.6 — фото размытое
    is_blurry_final = blur_score > 0.6

    print(f"[1] ACF: {avg_lag_5:.3f}, Лапласиан: {laplacian_var:.0f}, Медиана: {median_laplacian:.0f}")
    print(f"    HF ratio: {high_freq_ratio:.3f}, Blur score: {blur_score:.3f}")
    print(f"    -> {'РАЗМЫТО' if is_blurry_final else 'ЧЁТКО'}")

    return {
        "acf_score": avg_lag_5,
        "laplacian_var": laplacian_var,
        "median_laplacian": median_laplacian,
        "high_freq_ratio": high_freq_ratio,
        "blur_score": blur_score,
        "is_blurry": is_blurry_final
    }