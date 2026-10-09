import numpy as np
import cv2

def check_blur(image, mask=None):
    """
    Проверка на размытие.
    Если mask передан — анализируем только область объекта (игнорируем фон).
    """
    gray_float = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float64)
    gray_uint8 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray_float.shape

    brightness = np.mean(gray_uint8)

    # Если есть маска — применяем её ко всем расчётам
    if mask is not None and np.sum(mask) > 0:
        # Создаём изображение только с объектом (фон = серый 128)
        gray_object = gray_uint8.copy()
        gray_object[mask == 0] = 128

        gray_object_float = gray_object.astype(np.float64)
        mean_obj = np.mean(gray_object_float[mask > 0])
        std_obj = np.std(gray_object_float[mask > 0]) + 1e-8
        gray_norm = np.zeros_like(gray_object_float)
        gray_norm[mask > 0] = (gray_object_float[mask > 0] - mean_obj) / std_obj
    else:
        gray_object = gray_uint8
        mean_val = np.mean(gray_float)
        std_val = np.std(gray_float) + 1e-8
        gray_norm = (gray_float - mean_val) / std_val

    # ACF
    fft_img = np.fft.fft2(gray_norm)
    acf_full = np.fft.ifft2(fft_img * np.conj(fft_img)).real
    acf_full = np.fft.fftshift(acf_full)
    cy, cx = h // 2, w // 2
    acf_normalized = acf_full / (acf_full[cy, cx] + 1e-8)
    lag_5_h = acf_normalized[cy - 5, cx]
    lag_5_v = acf_normalized[cy, cx - 5]
    avg_lag_5 = (abs(lag_5_h) + abs(lag_5_v)) / 2

    # Лапласиан (по объекту, если есть маска)
    laplacian_var = cv2.Laplacian(gray_object, cv2.CV_64F).var()

    # Локальный лапласиан
    block_size = 64
    local_laplacians = []
    for y in range(0, h - block_size, block_size):
        for x in range(0, w - block_size, block_size):
            block = gray_object[y:y+block_size, x:x+block_size]
            block_mask = mask[y:y+block_size, x:x+block_size] if mask is not None else None

            # Считаем только если блок содержит объект (>30% пикселей)
            if block_mask is None or np.sum(block_mask) > (block_size * block_size * 0.3):
                lap_var = cv2.Laplacian(block, cv2.CV_64F).var()
                local_laplacians.append(lap_var)

    median_laplacian = np.median(local_laplacians) if local_laplacians else laplacian_var

    # Собель
    sobelx = cv2.Sobel(gray_object, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray_object, cv2.CV_64F, 0, 1, ksize=3)
    sobel_magnitude = np.sqrt(sobelx**2 + sobely**2)
    sobel_var = np.var(sobel_magnitude)

    # Motion blur detection
    mean_sobelx = np.mean(np.abs(sobelx))
    mean_sobely = np.mean(np.abs(sobely))
    max_dir = max(mean_sobelx, mean_sobely)
    min_dir = min(mean_sobelx, mean_sobely) + 1e-8
    direction_ratio = max_dir / min_dir
    is_motion_blur = direction_ratio > 3.0 and avg_lag_5 > 0.85

    # Взвешенная оценка
    if brightness < 40:
        lap_score = min(1.0, laplacian_var / 100.0)
        sobel_score = min(1.0, sobel_var / 800.0)
        final_sharpness = 0.40 * lap_score + 0.60 * sobel_score
        method = "тёмное фото"
    elif brightness > 220:
        lap_score = min(1.0, laplacian_var / 150.0)
        sobel_score = min(1.0, sobel_var / 1000.0)
        final_sharpness = 0.40 * lap_score + 0.60 * sobel_score
        method = "светлое фото"
    else:
        score_acf = max(0.0, 1.0 - (avg_lag_5 / 0.9))
        score_lap_global = min(1.0, laplacian_var / 500.0)
        score_lap_local = min(1.0, median_laplacian / 150.0)
        score_sobel = min(1.0, sobel_var / 1000.0)

        final_sharpness = (
            0.20 * score_acf +
            0.20 * score_lap_global +
            0.45 * score_lap_local +
            0.15 * score_sobel
        )

        if is_motion_blur:
            final_sharpness *= 0.7
            method = "motion blur detected"
        else:
            method = "нормальное фото" + (" (по маске объекта)" if mask is not None else "")

    is_blurry_final = final_sharpness < 0.50

    print(f"[1] МЕТРИКИ ЧЁТКОСТИ{' (по маске объекта)' if mask is not None else ''}:")
    print(f"    ACF: {avg_lag_5:.3f}, Лапласиан: {laplacian_var:.0f}, Медиана: {median_laplacian:.0f}")
    print(f"    Собель: {sobel_var:.0f}, Индекс: {final_sharpness:.2f} -> {'РАЗМЫТО' if is_blurry_final else 'ЧЁТКО'}")

    return {
        "acf_score": avg_lag_5,
        "laplacian_var": laplacian_var,
        "median_laplacian": median_laplacian,
        "sobel_var": sobel_var,
        "sharpness_score": final_sharpness,
        "is_blurry": is_blurry_final,
        "is_motion_blur": is_motion_blur,
        "method": method
    }