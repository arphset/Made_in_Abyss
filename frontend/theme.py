import os
import base64

import streamlit as st
import streamlit.components.v1 as components

# Общее оформление всех страниц QualityJPG: анимированный фон, кнопка музыки, CSS.
# Вынесено из app.py, чтобы страница анализа, история и админ-панель выглядели одинаково.
current_dir = os.path.dirname(os.path.abspath(__file__))


@st.cache_resource
def get_audio_base64():
    audio_path = os.path.join(current_dir, 'assets', 'background.mp3')
    if os.path.exists(audio_path):
        with open(audio_path, 'rb') as f:
            audio_data = f.read()
        return base64.b64encode(audio_data).decode('utf-8')
    return None

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

# ==========================================
# IFRAME 2: КНОПКА МУЗЫКИ
# ==========================================
def _music_html(audio_base64):
    return f"""
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

    /* ===== Спринт 3: навигация, вход, админ-панель ===== */
    .nav-user {
        text-align: right;
        color: rgba(200, 220, 255, 0.85);
        padding-top: 8px;
        font-size: 0.95rem;
    }
    .role-badge {
        display: inline-block;
        padding: 2px 10px;
        margin-left: 6px;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
        border: 1px solid rgba(100, 180, 255, 0.4);
        background: rgba(74, 158, 255, 0.15);
        color: #4a9eff;
    }
    .role-badge.admin {
        border-color: rgba(108, 92, 231, 0.6);
        background: rgba(108, 92, 231, 0.2);
        color: #a29bfe;
    }
    [data-testid="stPageLink"] a {
        background: rgba(30, 40, 60, 0.6);
        border: 1px solid rgba(100, 180, 255, 0.2);
        border-radius: 12px;
        padding: 8px 14px;
        justify-content: center;
        transition: all 0.3s ease;
    }
    [data-testid="stPageLink"] a:hover {
        border-color: rgba(100, 180, 255, 0.6);
        box-shadow: 0 0 15px rgba(100, 180, 255, 0.25);
    }
    [data-testid="stPageLink-NavLink"][aria-current="page"],
    [data-testid="stPageLink"] a[aria-current="page"] {
        background: linear-gradient(135deg, rgba(74, 158, 255, 0.35), rgba(108, 92, 231, 0.35));
        border-color: rgba(100, 180, 255, 0.6);
    }
    .st-key-logout_btn button {
        padding: 8px 14px;
        font-size: 0.95rem;
        white-space: nowrap;
        background: rgba(30, 40, 60, 0.6);
        border: 1px solid rgba(239, 68, 68, 0.4);
    }
    .st-key-logout_btn button:hover {
        border-color: rgba(239, 68, 68, 0.8);
        box-shadow: 0 0 15px rgba(239, 68, 68, 0.25);
    }
    .section-title {
        color: #4a9eff;
        font-size: 1.25rem;
        font-weight: 600;
        margin: 1.2rem 0 0.6rem 0;
    }
    .glass-card {
        background: rgba(30, 40, 60, 0.7);
        border: 1px solid rgba(100, 180, 255, 0.3);
        border-radius: 12px;
        padding: 20px;
        margin: 10px 0;
    }
    .stat-card {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.2), rgba(139, 92, 246, 0.2));
        border: 1px solid rgba(56, 189, 248, 0.35);
        border-radius: 14px;
        padding: 16px;
        text-align: center;
        height: 100%;
    }
    .stat-card .stat-value { font-size: 2rem; font-weight: 700; color: #38bdf8; }
    .stat-card .stat-label { font-size: 0.9rem; color: rgba(200, 220, 255, 0.75); margin-top: 4px; }
    .stat-card.good .stat-value { color: #4ade80; }
    .stat-card.bad .stat-value { color: #f87171; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(30, 40, 60, 0.6);
        border-radius: 10px 10px 0 0;
        padding: 8px 16px;
    }
    [data-testid="stDataFrame"], [data-testid="stExpander"] {
        border: 1px solid rgba(100, 180, 255, 0.2);
        border-radius: 12px;
        background: rgba(20, 30, 50, 0.6);
    }
    [data-testid="stForm"] {
        background: rgba(30, 40, 60, 0.6);
        border: 1px solid rgba(100, 180, 255, 0.25);
        border-radius: 16px;
    }
    .stFormSubmitButton > button {
        background: linear-gradient(135deg, #4a9eff, #6c5ce7);
        color: white;
        border: none;
        font-weight: 600;
        border-radius: 12px;
        width: 100%;
    }
</style>
"""


def apply_theme():
    """Отрисовать общий фон, кнопку музыки и стили. Вызывается один раз за прогон скрипта."""
    components.html(canvas_html, height=1, scrolling=False)
    audio_base64 = get_audio_base64()
    if audio_base64:
        components.html(_music_html(audio_base64), height=1, scrolling=False)
    st.markdown(custom_css, unsafe_allow_html=True)


def page_header(title: str, subtitle: str):
    st.markdown(f'<div class="app-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="app-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def stat_card(column, value, label: str, kind: str = ''):
    column.markdown(
        f'<div class="stat-card {kind}"><div class="stat-value">{value}</div>'
        f'<div class="stat-label">{label}</div></div>',
        unsafe_allow_html=True
    )
