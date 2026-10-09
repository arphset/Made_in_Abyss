import cv2
import numpy as np
from ultralytics import YOLO
from openai import OpenAI
from ollama.ollama_access import get_recommendations
from filters.blure_filter import check_blur
from filters.brightness_filter import check_brightness
from filters.YOLO import detect_objects_yolo
import os

def analyze_image(image_path):
    image = cv2.imread(image_path)
    if image is None:
        return {"error": "Картинка не найдена"}

    h, w = image.shape[:2]
    print(f"--- Анализ: {image_path} ({w}x{h}) ---")

    # Сначала YOLO — чтобы получить маску объекта
    yolo_data = detect_objects_yolo(image)

    # Создаём бинарную маску из bounding boxes
    object_mask = None
    if yolo_data.get("object_found", False) and len(yolo_data.get("boxes", [])) > 0:
        object_mask = np.zeros((h, w), dtype=np.uint8)
        for box in yolo_data["boxes"]:
            x1, y1, x2, y2 = box
            # Добавляем небольшой отступ (10 пикселей) для захвата краёв объекта
            x1 = max(0, x1 - 10)
            y1 = max(0, y1 - 10)
            x2 = min(w, x2 + 10)
            y2 = min(h, y2 + 10)
            object_mask[y1:y2, x1:x2] = 255
        print(f"[0] Маска объекта создана: {np.sum(object_mask > 0)} пикселей")

    # Метрика 1: Размытие (с маской, если есть)
    blur_data = check_blur(image, mask=object_mask)

    # Метрика 2: Яркость (по всему фото)
    brightness_data = check_brightness(image)

    # Итоговый вердикт
    issues = []

    if blur_data["is_blurry"]:
        issues.append("Размыто или смаз движения")

    if brightness_data["is_overexposed"]:
        issues.append("Пересвет (потеря деталей в светах)")
    if brightness_data["is_underexposed"]:
        issues.append("Недосвет (провал в тенях)")
    if brightness_data["is_dark"]:
        issues.append("Слишком темно (общая экспозиция)")
    if brightness_data["is_bright"]:
        issues.append("Общий пересвет кадра")

    # Проверка заполнения
    fill_rate = yolo_data.get("fill_rate", 0)
    if fill_rate < 0.30:
        issues.append(f"Малое заполнение кадра ({fill_rate*100:.1f}%, рекомендуется >30%)")

    if yolo_data["composition_bad"]:
        issues.extend(yolo_data["issues_comp"])

    if not issues:
        print("\n✅ ФОТО ОТЛИЧНОЕ! Можно публиковать.")
    else:
        print(f"\n❌ ПРОБЛЕМЫ: {', '.join(issues)}")

    return {
        "acf_score": blur_data["acf_score"],
        "laplacian_var": blur_data["laplacian_var"],
        "brightness": brightness_data["brightness"],
        "overexposed_pct": brightness_data["overexposed_pct"],
        "fill_rate": yolo_data["fill_rate"],
        "is_off_center": yolo_data["is_off_center"],
        "composition_bad": yolo_data["composition_bad"],
        "object_found": yolo_data["object_found"],
        "issues": issues,
        "median_laplacian": blur_data.get("median_laplacian", 0),
        "sobel_var": blur_data.get("sobel_var", 0),
        "sharpness_score": blur_data.get("sharpness_score", 0),
        "blur_method": blur_data.get("method", "неизвестно"),
        "is_blurry": blur_data.get("is_blurry", False),
        "is_motion_blur": blur_data.get("is_motion_blur", False),
        "underexposed_pct": brightness_data["underexposed_pct"],
        "is_dark": brightness_data["is_dark"],
        "is_bright": brightness_data["is_bright"],
        "is_overexposed": brightness_data["is_overexposed"],
        "is_underexposed": brightness_data["is_underexposed"],
    }