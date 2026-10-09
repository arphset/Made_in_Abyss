from ultralytics import YOLO
import numpy as np


def detect_objects_yolo(image):
    """Обнаружение объектов с помощью YOLO"""
    model = YOLO('yolov8n.pt')
    results = model(image, verbose=False)

    h, w = image.shape[:2]
    image_area = h * w
    img_cx, img_cy = w / 2, h / 2

    max_fill_rate = 0
    total_fill_rate = 0
    max_confidence = 0
    object_count = 0
    object_found = False

    all_centers_x = []
    all_centers_y = []

    # ✅ НОВОЕ: создаём список для bounding boxes
    boxes_list = []

    for box in results[0].boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        conf = float(box.conf[0].cpu().numpy())

        # ✅ НОВОЕ: добавляем координаты в список
        boxes_list.append((int(x1), int(y1), int(x2), int(y2)))

        obj_area = (x2 - x1) * (y2 - y1)
        fill_rate = obj_area / image_area

        total_fill_rate += fill_rate
        object_count += 1

        obj_cx = (x1 + x2) / 2
        obj_cy = (y1 + y2) / 2
        all_centers_x.append(obj_cx)
        all_centers_y.append(obj_cy)

        if fill_rate > max_fill_rate:
            max_fill_rate = fill_rate
            max_confidence = conf
            object_found = True

    # Проверка центрирования группы объектов
    group_cx = np.mean(all_centers_x) if all_centers_x else img_cx
    group_cy = np.mean(all_centers_y) if all_centers_y else img_cy

    tolerance_x = w * 0.25
    tolerance_y = h * 0.25

    dist_x = abs(group_cx - img_cx)
    dist_y = abs(group_cy - img_cy)

    is_off_center = dist_x > tolerance_x or dist_y > tolerance_y

    # Оценка композиции
    composition_bad = False
    issues_comp = []

    if not object_found or (total_fill_rate < 0.05 and max_confidence < 0.4):
        print("[3] YOLO: Товар не обнаружен")
        issues_comp.append("Вероятно, товара нет в кадре")
        composition_bad = True
    else:
        if total_fill_rate < 0.15:
            issues_comp.append(f"Товары занимают всего {total_fill_rate*100:.0f}% кадра. Критически мало.")
            composition_bad = True
        elif total_fill_rate < 0.30:
            issues_comp.append(f"Товары занимают {total_fill_rate*100:.0f}% (рекомендуется >30%). Можно приблизить.")

        status_center = "ОК" if not is_off_center else "СМЕЩЕН"
        print(f"[3] YOLO: Найдено {object_count} шт. Суммарно: {total_fill_rate*100:.1f}%, Центр группы: {status_center}")

    if issues_comp:
        print(f"    -> Композиция: {', '.join(issues_comp)}")

    return {
        "fill_rate": total_fill_rate if object_found else 0,
        "max_fill_rate": max_fill_rate,
        "max_confidence": max_confidence,
        "object_count": object_count,
        "object_found": object_found,
        "is_off_center": is_off_center,
        "composition_bad": composition_bad,
        "issues_comp": issues_comp,
        "boxes": boxes_list  # ✅ Теперь boxes_list определён
    }