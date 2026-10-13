import json
import os

import cv2
import numpy as np
import streamlit as st

from main import analyze_image
from ollama.ollama_access import get_recommendations
from filters.score_calculator import calculate_quality_score

from database import db_repo
from auth import current_user, log_action
from report_view import safe_float, render_recommendations
import storage

# Страница «Анализ фото» (функционал продавца, доступен и администратору — F.03.02)
user = current_user()

def validate_image(file):
    MAX_SIZE = 10 * 1024 * 1024
    if file.size > MAX_SIZE:
        return False, "Файл слишком большой (" + str(round(file.size / 1024 / 1024, 1)) + " МБ). Максимум 10 МБ."
    allowed = ['.jpg', '.jpeg', '.png']
    if os.path.splitext(file.name)[1].lower() not in allowed:
        return False, "Неподдерживаемый формат. Допустимые: JPG, PNG."
    try:
        file_bytes = np.asarray(bytearray(file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError
        return True, img
    except:
        return False, "Файл повреждён или не является изображением."

# Заголовок
st.markdown('<div class="app-title">📸 QualityJPG</div>', unsafe_allow_html=True)
st.markdown('<div class="app-subtitle">AI-анализ качества фото для маркетплейсов</div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("", type=['jpg', 'jpeg', 'png'], label_visibility="collapsed")

# Сброс сессии при загрузке нового файла
if uploaded_file and st.session_state.get('current_file_name') != uploaded_file.name:
    st.session_state['current_file_name'] = uploaded_file.name
    st.session_state['analysis_done'] = False
    st.session_state['analysis_result'] = None
    st.session_state['recs'] = None
    st.session_state['storage_filename'] = None
    st.session_state['db_analysis_id'] = None
if uploaded_file:
    is_valid, result = validate_image(uploaded_file)

    if not is_valid:
        st.error("⛔ " + result)
    else:
        img_array = result

        col1, col2 = st.columns([1.3, 0.7])

        with col1:
            st.image(img_array, channels="BGR", use_container_width=True)
            st.caption("📷 " + uploaded_file.name + " • " + str(img_array.shape[1]) + "×" + str(img_array.shape[0]) + " px")

        with col2:
            st.subheader("⚙️ Параметры анализа")
            st.write("Система проверит:")
            st.info("🔍 Резкость и текстуру (ACF + Laplacian)")
            st.info("💡 Экспозицию и баланс света")
            st.info("📐 Композицию и заполнение кадра")

        # Кнопка с уникальным ключом
        analyze_button = st.button(
            "🔍 Анализировать фото",
            type="primary",
            use_container_width=True,
            key="analyze_btn_main"
        )

        if analyze_button:
            st.session_state['analysis_done'] = True
            st.session_state['analysis_result'] = None
            st.session_state['recs'] = None
            st.session_state['storage_filename'] = None
            st.session_state['db_analysis_id'] = None

        # Показываем результаты, если анализ был выполнен
        if st.session_state.get('analysis_done'):
            try:
                # Если результаты ещё не посчитаны — считаем
                if st.session_state.get('analysis_result') is None:
                    with st.spinner("⏳ Нейросеть анализирует изображение..."):
                        file_path, storage_name = storage.save_image(uploaded_file.name, img_array)
                        log_action('upload', f"{uploaded_file.name} → {storage_name}")
                        try:
                            st.session_state['analysis_result'] = analyze_image(file_path)
                        except Exception as ml_error:
                            # R.01.03: сбой ML-модуля не роняет приложение
                            st.session_state['analysis_result'] = {"error": "Не удалось проанализировать фото, попробуйте позже"}
                            print(f"Ошибка ML-модуля: {ml_error}")
                        st.session_state['storage_filename'] = storage_name
                        if "error" in st.session_state['analysis_result']:
                            log_action('analysis_error', f"{uploaded_file.name}: {st.session_state['analysis_result']['error']}")

                    if "error" not in st.session_state['analysis_result']:
                        with st.spinner(" Формирую рекомендации..."):
                            st.session_state['recs'] = get_recommendations(st.session_state['analysis_result'])
                    else:
                        st.session_state['recs'] = None

                analysis_result = st.session_state['analysis_result']
                recs = st.session_state.get('recs')

                # Проверяем наличие ошибки
                if "error" in analysis_result:
                    st.error("❌ " + analysis_result["error"])
                else:
                    # Рассчитываем итоговую оценку качества
                    score_data = calculate_quality_score(analysis_result)

                    st.markdown("---")
                    st.subheader(" Результаты проверки")

                    # Карточка с итоговой оценкой
                    st.markdown(f"""
                    <div class="score-card">
                        <div class="score-value">{score_data['emoji']} {score_data['score']}/10</div>
                        <div class="score-verdict">{score_data['verdict']}</div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Детализация штрафов
                    if score_data["penalties"]:
                        st.subheader("📉 Что снизило оценку:")
                        for penalty in score_data["penalties"]:
                            st.markdown(f'<div class="penalty-item">{penalty}</div>', unsafe_allow_html=True)

                    # Метрики
                    st.subheader(" Детальные метрики")

                    # Первая строка: основные метрики
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("ACF Score", f"{analysis_result['acf_score']:.3f}")
                    m2.metric("Яркость", f"{analysis_result['brightness']:.0f}")
                    m3.metric("Заполнение", f"{analysis_result['fill_rate']*100:.1f}%")
                    m4.metric("Индекс чёткости", f"{analysis_result.get('sharpness_score', 0):.2f}")

                    # Вторая строка: расширенные метрики резкости
                    st.markdown("---")
                    st.markdown("#### 🔬 Метрики резкости")

                    r1, r2, r3 = st.columns(3)
                    r1.metric(
                        "Лапласиан (глобальный)",
                        f"{analysis_result.get('laplacian_var', 0):.0f}",
                        help="Дисперсия лапласиана по всему изображению. Высокое значение = много текстур."
                    )
                    r2.metric(
                        "Лапласиан (локальный, медиана)",
                        f"{analysis_result.get('median_laplacian', 0):.0f}",
                        help="Медиана лапласиана по блокам 64x64. Устойчива к тёмным/светлым фонам."
                    )
                    r3.metric(
                        "Вариация градиента Собеля",
                        f"{analysis_result.get('sobel_var', 0):.0f}",
                        help="Измеряет чёткость краёв объектов. Лучше лапласиана для тёмных фото."
                    )

                    # Третья строка: экспозиция
                    st.markdown("#### 💡 Метрики экспозиции")

                    e1, e2 = st.columns(2)
                    e1.metric("Пересвет", f"{analysis_result.get('overexposed_pct', 0):.1f}%")
                    e2.metric("Недосвет", f"{analysis_result.get('underexposed_pct', 0):.1f}%")

                    if analysis_result['issues']:
                        st.warning("⚠️ Выявлено проблем: " + str(len(analysis_result['issues'])))
                        for issue in analysis_result['issues']:
                            st.text("• " + issue)
                    else:
                        st.success("✅ Фото соответствует стандартам!")

                    if recs and st.session_state.get('db_analysis_id'):
                        st.success(f"✅ Результат сохранён в БД (ID: {st.session_state['db_analysis_id'][:8]}...)")
                    elif recs:
                        # Сохранение результата в базу данных (один раз на анализ, а не на каждый rerun)
                        try:
                            export_data_for_db = {
                                'filename': uploaded_file.name,
                                'user_id': user['id'],
                                # Из session_state: локальная переменная не переживает rerun Streamlit
                                'storage_filename': st.session_state['storage_filename'],
                                'overall_score': score_data['score'],
                                'verdict': score_data['verdict'],
                                'metrics': {
                                    'sharpness': {
                                        'acf_score': round(safe_float(analysis_result.get('acf_score')), 3),
                                        'laplacian_global': round(safe_float(analysis_result.get('laplacian_var')), 1),
                                        'laplacian_local_median': round(safe_float(analysis_result.get('median_laplacian')), 1),
                                        'sobel_gradient_variance': round(safe_float(analysis_result.get('sobel_var')), 1),
                                        'sharpness_index': round(safe_float(analysis_result.get('sharpness_score')), 2)
                                    },
                                    'exposure': {
                                        'brightness': round(safe_float(analysis_result.get('brightness')), 1),
                                        'overexposed_pct': round(safe_float(analysis_result.get('overexposed_pct')), 1),
                                        'underexposed_pct': round(safe_float(analysis_result.get('underexposed_pct')), 1)
                                    },
                                    'composition': {
                                        'fill_rate_pct': round(safe_float(analysis_result.get('fill_rate')) * 100, 1),
                                        'is_off_center': bool(analysis_result.get('is_off_center', False)),
                                        'object_found': bool(analysis_result.get('object_found', True))
                                    }
                                },
                                'summary': {
                                    'issues': analysis_result.get('issues', [])
                                },
                                'penalties': score_data.get('penalties', []),
                                'ai_recommendations': recs,
                                'file_info': {
                                    'resolution': f"{img_array.shape[1]}x{img_array.shape[0]}",
                                    'file_size_kb': round(uploaded_file.size / 1024, 1)
                                }
                            }

                            analysis_id = db_repo.save_analysis_result(export_data_for_db)
                            st.session_state['db_analysis_id'] = str(analysis_id)
                            log_action('analysis_ok', f"{uploaded_file.name}: {score_data['score']}/10 ({score_data['verdict']})", str(analysis_id))
                            st.success(f"✅ Результат сохранён в БД (ID: {str(analysis_id)[:8]}...)")

                        except Exception as db_error:
                            st.warning(f"⚠️ Не удалось сохранить в БД: {db_error}")

                    if recs:
                        render_recommendations(recs)

                        # Переключатель формата копирования
                        st.markdown("### 📋 Копирование результатов")
                        export_format = st.radio(
                            "Выберите формат:",
                            options=["📝 Текст", "🔧 JSON"],
                            horizontal=True,
                            label_visibility="collapsed",
                            key="export_format_radio"
                        )

                        if export_format == "📝 Текст":
                            st.code(recs, language="text")
                            st.caption("📋 Скопируйте текст выше для использования в заметках")
                        else:
                            # Формируем JSON со всеми метриками
                            quality_score_data = analysis_result.get("quality_score", {})
                            if not isinstance(quality_score_data, dict):
                                quality_score_data = score_data

                            export_data = {
                                "summary": {
                                    "quality_score": quality_score_data.get("score", 0),
                                    "verdict": quality_score_data.get("verdict", ""),
                                    "issues_count": len(analysis_result.get("issues", [])),
                                    "issues": analysis_result.get("issues", [])
                                },
                                "metrics": {
                                    "sharpness": {
                                        "acf_score": round(float(analysis_result.get("acf_score", 0)), 3),
                                        "laplacian_global": round(float(analysis_result.get("laplacian_var", 0)), 1),
                                        "laplacian_local_median": round(float(analysis_result.get("median_laplacian", 0)), 1),
                                        "sobel_gradient_variance": round(float(analysis_result.get("sobel_var", 0)), 1),
                                        "sharpness_index": round(float(analysis_result.get("sharpness_score", 0)), 2)
                                    },
                                    "exposure": {
                                        "brightness": round(float(analysis_result.get("brightness", 0)), 1),
                                        "overexposed_pct": round(float(analysis_result.get("overexposed_pct", 0)), 1),
                                        "underexposed_pct": round(float(analysis_result.get("underexposed_pct", 0)), 1)
                                    },
                                    "composition": {
                                        "fill_rate_pct": round(float(analysis_result.get("fill_rate", 0)) * 100, 1),
                                        "is_off_center": bool(analysis_result.get("is_off_center", False)),
                                        "object_found": bool(analysis_result.get("object_found", True))
                                    }
                                },
                                "ai_recommendations": recs,
                                "file_info": {
                                    "filename": uploaded_file.name,
                                    "resolution": f"{img_array.shape[1]}x{img_array.shape[0]}",
                                    "file_size_kb": round(uploaded_file.size / 1024, 1)
                                }
                            }

                            json_output = json.dumps(export_data, ensure_ascii=False, indent=2)
                            st.code(json_output, language="json")
                            st.caption("📋 JSON скопирован — удобно для интеграции с другими системами")

            except Exception as e:
                st.error("❌ Ошибка обработки: " + str(e))
