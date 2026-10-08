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

    # Метрика 1: Размытие
    blur_data = check_blur(image)

    # Метрика 2: Яркость
    brightness_data = check_brightness(image)

    # Метрика 3: YOLO
    yolo_data = detect_objects_yolo(image)

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
        "issues": issues
    }


if __name__ == "__main__":
    # Получаем путь к папке, где лежит сам main.py
    current_dir = os.path.dirname(os.path.abspath(__file__))
    image_path = os.path.join(current_dir, "t.jpg")

    # 1. Анализируем фото
    data = analyze_image(image_path)

    print("\nГенерирую рекомендации через LLM...\n")

    # 2. Получаем и ПЕЧАТАЕМ ответ
    llm_response = get_recommendations(data)
    print(llm_response)