import numpy as np
import cv2


def check_blur(image):
    """Проверка на размытие с помощью автокорреляции и Лапласиана"""
    gray_float = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float64)
    gray_uint8 = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    h, w = gray_float.shape

    # Нормализуем яркость для корректной автокорреляции
    mean_val = np.mean(gray_float)
    std_val = np.std(gray_float) + 1e-8
    gray_norm = (gray_float - mean_val) / std_val

    # Автокорреляция
    fft_img = np.fft.fft2(gray_norm)
    acf_full = np.fft.ifft2(fft_img * np.conj(fft_img)).real
    acf_full = np.fft.fftshift(acf_full)

    cy, cx = h // 2, w // 2
    acf_normalized = acf_full / (acf_full[cy, cx] + 1e-8)

    lag_5_h = acf_normalized[cy - 5, cx]
    lag_5_v = acf_normalized[cy, cx - 5]
    avg_lag_5 = (abs(lag_5_h) + abs(lag_5_v)) / 2

    # Лапласиан
    laplacian_var = cv2.Laplacian(gray_uint8, cv2.CV_64F).var()

    # Логика определения размытия
    is_blurry_acf = avg_lag_5 > 0.85
    has_texture = laplacian_var > 150
    is_blurry_final = is_blurry_acf and not has_texture

    print(f"[1] ACF: {avg_lag_5:.3f}, Лапласиан: {laplacian_var:.0f} -> {'РАЗМЫТО' if is_blurry_final else 'ЧЕТКО/ТЕКСТУРА'}")

    return {
        "acf_score": avg_lag_5,
        "laplacian_var": laplacian_var,
        "is_blurry": is_blurry_final
    }
