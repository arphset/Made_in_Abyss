import streamlit as st
import streamlit.components.v1 as components
import os
import uuid
import cv2
import numpy as np
import sys
import re
import base64
import json
import math


# Настройка путей
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
ml_module_path = os.path.join(project_root, 'ML&CV_Module')
sys.path.insert(0, ml_module_path)

from main import analyze_image
from ollama.ollama_access import get_recommendations
from filters.score_calculator import calculate_quality_score

# Импорт репозитория базы данных
sys.path.insert(0, project_root)
from database import db_repo

st.set_page_config(
    page_title="QualityJPG",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="collapsed"
)


def safe_float(value, default=0):
    """Безопасное преобразование в float, обработка nan/None"""
    if value is None:
        return default
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default

# ==========================================
# ФУНКЦИЯ ДЛЯ ФОРМАТИРОВАНИЯ РЕКОМЕНДАЦИЙ
# ==========================================
def format_recommendations(recs):
    if not recs:
        return ""
    lines = recs.strip().split('\n')
    html_parts = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        line = line.replace('**', '').replace('*', '').replace('`', '')
        clean_line = re.sub(r'^#+\s+', '', line)
        if re.match(r'^\d+\.', clean_line):
            html_parts.append('<p style="margin:8px 0;padding-left:10px;">' + clean_line + '</p>')
        elif ':' in clean_line and any(c.isdigit() for c in clean_line):
            key, _, value = clean_line.partition(':')
            html_parts.append(
                '<p style="margin:4px 0;color:rgba(200,220,255,0.9);">'
                '<span style="color:#4a9eff;font-weight:600;">' + key + ':</span>' + value + '</p>'
            )
        elif re.match(r'^[А-Яа-яA-Za-z].*:$', clean_line):
            html_parts.append('<h4 style="color:#4a9eff;margin-top:14px;margin-bottom:6px;">' + clean_line + '</h4>')
        else:
            html_parts.append('<p style="margin:4px 0;">' + clean_line + '</p>')
    return '\n'.join(html_parts)

# ==========================================
# ЗАГРУЗКА ЛОКАЛЬНОГО ТРЕКА
# ==========================================
def get_audio_base64():
    audio_path = os.path.join(current_dir, 'assets', 'background.mp3')
    if os.path.exists(audio_path):
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        return base64.b64encode(audio_data).decode('utf-8')
    return None

audio_base64 = get_audio_base64()

# ==========================================
# IFRAME 1: CANVAS-АНИМАЦИЯ (ФОН)
# ==========================================
canvas_html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { background: transparent; overflow: hidden; }
    #bgCanvas { position: fixed; top: 0; left: 0; pointer-events: none; }
</style>
</head>
<body>
<canvas id="bgCanvas"></canvas>
<script>
(function() {
    if (window.parent !== window) {
        try {
            const iframes = window.parent.document.querySelectorAll('iframe');
            for (let iframe of iframes) {
                if (iframe.contentWindow === window) {
                    iframe.style.cssText = 'position:fixed!important;top:0!important;left:0!important;width:100vw!important;height:100vh!important;z-index:0!important;border:none!important;pointer-events:none!important;color-scheme:normal!important;';
                    if (iframe.parentElement) {
                        iframe.parentElement.style.height = '0';
                        iframe.parentElement.style.overflow = 'visible';
                    }
                    break;
                }
            }
        } catch(e) { console.log('Canvas iframe style failed:', e); }
    }

    const canvas = document.getElementById('bgCanvas');
    const ctx = canvas.getContext('2d');
    let particles = [];
    const PARTICLE_COUNT = 80;
    const CONNECTION_DIST = 150;
    const BASE_SPEED = 0.5;
    let speedMultiplier = 1;

    function getMusicState() {
        try { return sessionStorage.getItem('musicPlaying') === 'true'; } catch(e) { return false; }
    }

    if (getMusicState()) {
        speedMultiplier = 50;
        console.log('[Canvas] Music was playing, speed:', speedMultiplier);
    } else {
        speedMultiplier = 1;
        console.log('[Canvas] Music not playing, speed:', speedMultiplier);
    }

    window.addEventListener('storage', function(e) {
        if (e.key === 'musicPlaying') {
            speedMultiplier = (e.newValue === 'true') ? 50 : 1;
        }
    });

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    class Particle {
        constructor() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.baseVx = (Math.random() - 0.5) * BASE_SPEED;
            this.baseVy = (Math.random() - 0.5) * BASE_SPEED;
            this.vx = this.baseVx;
            this.vy = this.baseVy;
            this.radius = Math.random() * 2 + 1;
        }
        update() {
            this.vx = this.baseVx * speedMultiplier;
            this.vy = this.baseVy * speedMultiplier;
            this.x += this.vx;
            this.y += this.vy;
            if (this.x < 0) { this.x = 0; this.baseVx = Math.abs(this.baseVx); }
            else if (this.x > canvas.width) { this.x = canvas.width; this.baseVx = -Math.abs(this.baseVx); }
            if (this.y < 0) { this.y = 0; this.baseVy = Math.abs(this.baseVy); }
            else if (this.y > canvas.height) { this.y = canvas.height; this.baseVy = -Math.abs(this.baseVy); }
        }
        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.radius, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(100, 180, 255, 0.7)';
            ctx.fill();
        }
    }

    for (let i = 0; i < PARTICLE_COUNT; i++) {
        particles.push(new Particle());
    }

    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < CONNECTION_DIST) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    const alpha = 0.3 * (1 - dist / CONNECTION_DIST);
                    ctx.strokeStyle = 'rgba(100, 180, 255, ' + alpha + ')';
                    ctx.lineWidth = 0.8;
                    ctx.stroke();
                }
            }
        }
        particles.forEach(function(p) { p.update(); p.draw(); });
        requestAnimationFrame(animate);
    }
    animate();
})();
</script>
</body>
</html>
"""
components.html(canvas_html, height=1, scrolling=False)

# ==========================================
# IFRAME 2: КНОПКА МУЗЫКИ
# ==========================================
if audio_base64:
    music_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="UTF-8">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: transparent;
            overflow: hidden;
            width: 56px;
            height: 56px;
        }}
        #musicToggle {{
            width: 56px;
            height: 56px;
            border-radius: 50%;
            border: 2px solid rgba(100, 180, 255, 0.6);
            background: rgba(20, 30, 50, 0.85);
            backdrop-filter: blur(8px);
            cursor: pointer;
            font-size: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            box-shadow: 0 0 20px rgba(100, 180, 255, 0.3);
            color: white;
            outline: none;
        }}
        #musicToggle:hover {{
            transform: scale(1.1);
            box-shadow: 0 0 30px rgba(100, 180, 255, 0.5);
        }}
        #musicToggle.playing {{
            box-shadow: 0 0 25px rgba(100,255,150,0.5);
            border-color: rgba(100,255,150,0.7);
            background: rgba(20, 50, 30, 0.85);
        }}
    </style>
    </head>
    <body>
    <button id="musicToggle" title="Включить/выключить музыку">🎵</button>
    <audio id="bgAudio" loop preload="auto">
        <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mpeg">
    </audio>
    <script>
    (function() {{
        if (window.parent !== window) {{
            try {{
                const iframes = window.parent.document.querySelectorAll('iframe');
                for (let iframe of iframes) {{
                    if (iframe.contentWindow === window) {{
                        iframe.style.cssText = 'position:fixed!important;bottom:20px!important;left:20px!important;width:56px!important;height:56px!important;z-index:9999!important;border:none!important;pointer-events:auto!important;background:transparent!important;color-scheme:normal!important;';
                        if (iframe.parentElement) {{
                            iframe.parentElement.style.height = '0';
                            iframe.parentElement.style.overflow = 'visible';
                        }}
                        break;
                    }}
                }}
            }} catch(e) {{ console.log('Music iframe style failed:', e); }}
        }}

        const btn = document.getElementById('musicToggle');
        const audio = document.getElementById('bgAudio');
        let isPlaying = false;

        function setMusicState(playing) {{
            try {{
                sessionStorage.setItem('musicPlaying', playing ? 'true' : 'false');
            }} catch(e) {{}}
        }}

        btn.addEventListener('click', function() {{
            if (!isPlaying) {{
                audio.play().then(function() {{
                    isPlaying = true;
                    btn.textContent = '🔊';
                    btn.classList.add('playing');
                    setMusicState(true);
                }}).catch(function(e) {{
                    console.log('Play failed:', e);
                }});
            }} else {{
                audio.pause();
                isPlaying = false;
                btn.textContent = '🎵';
                btn.classList.remove('playing');
                setMusicState(false);
            }}
        }});

        audio.addEventListener('ended', function() {{
            audio.currentTime = 0;
            audio.play();
        }});
    }})();
    </script>
    </body>
    </html>
    """
    components.html(music_html, height=1, scrolling=False)
else:
    st.warning("️ Файл background.mp3 не найден в папке assets/. Музыка недоступна.")

# ==========================================
# CSS СТИЛИ
# ==========================================
custom_css = """
<style>
    .block-container, [data-testid="stAppViewContainer"], [data-testid="stHeader"], header {
        background: transparent !important;
    }
    .block-container {
        position: relative;
        z-index: 1;
    }
    .main .block-container {
        background: rgba(10, 15, 25, 0.8);
        border-radius: 16px;
        margin-top: 20px;
        padding: 30px 40px;
    }
    .app-title {
        text-align: center;
        font-size: 2.8rem;
        font-weight: 700;
        color: #ffffff;
        margin-bottom: 0.3rem;
        text-shadow: 0 0 20px rgba(100, 180, 255, 0.4);
    }
    .app-subtitle {
        text-align: center;
        font-size: 1.15rem;
        color: rgba(200, 220, 255, 0.7);
        margin-bottom: 2rem;
    }
    .stButton > button {
        background: linear-gradient(135deg, #4a9eff, #6c5ce7);
        color: white;
        border: none;
        font-size: 1.1rem;
        font-weight: 600;
        padding: 14px 28px;
        border-radius: 12px;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(74, 158, 255, 0.4);
    }
    [data-testid="stMetric"] {
        background: rgba(30, 40, 60, 0.6);
        border-radius: 12px;
        padding: 15px;
        border: 1px solid rgba(100, 180, 255, 0.2);
    }
    body { background: #0a0f1a !important; }
    .score-card {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(139, 92, 246, 0.2));
        border: 2px solid rgba(56, 189, 248, 0.4);
        border-radius: 16px;
        padding: 2rem;
        text-align: center;
        margin: 1rem 0;
    }
    .score-value { font-size: 4rem; font-weight: 700; color: #38bdf8; }
    .score-verdict { font-size: 1.5rem; color: #e2e8f0; margin-top: 0.5rem; }
    .penalty-item {
        background: rgba(239, 68, 68, 0.1);
        border-left: 3px solid #ef4444;
        padding: 8px 12px;
        margin: 8px 0;
        border-radius: 4px;
        color: #fca5a5;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# ==========================================
# ЛОГИКА ПРИЛОЖЕНИЯ
# ==========================================
UPLOAD_DIR = os.path.join(current_dir, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

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

def save_uploaded_file(file, img_array):
    ext = os.path.splitext(file.name)[1].lower()
    unique_name = str(uuid.uuid4()) + ext
    path = os.path.join(UPLOAD_DIR, unique_name)
    cv2.imwrite(path, img_array)
    return path, unique_name

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

        # Показываем результаты, если анализ был выполнен
        if st.session_state.get('analysis_done'):
            try:
                # Если результаты ещё не посчитаны — считаем
                if st.session_state.get('analysis_result') is None:
                    with st.spinner("⏳ Нейросеть анализирует изображение..."):
                        file_path, storage_name = save_uploaded_file(uploaded_file, img_array)
                        st.session_state['analysis_result'] = analyze_image(file_path)
                        st.session_state['storage_filename'] = storage_name

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

                    if recs:
                        # Сохранение результата в базу данных
                        try:
                            export_data_for_db = {
                                'filename': uploaded_file.name,
                                'storage_filename': storage_name,  # Используем локальную переменную!
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
                            st.success(f"✅ Результат сохранён в БД (ID: {str(analysis_id)[:8]}...)")

                        except Exception as db_error:
                            st.warning(f"⚠️ Не удалось сохранить в БД: {db_error}")
                            analysis_id = db_repo.save_analysis_result(export_data_for_db)
                            st.success(f"✅ Результат сохранён в БД (ID: {str(analysis_id)[:8]}...)")

                        except Exception as db_error:
                            st.warning(f"⚠️ Не удалось сохранить в БД: {db_error}")
                        formatted_recs = format_recommendations(recs)
                        st.markdown(f"""
                        <div style="background:rgba(30,40,60,0.7);border:1px solid rgba(100,180,255,0.3);border-radius:12px;padding:20px;margin-top:15px;">
                            <h3 style="color:#4a9eff;margin-top:0;">💡 Рекомендации AI</h3>
                            {formatted_recs}
                        </div>
                        """, unsafe_allow_html=True)

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