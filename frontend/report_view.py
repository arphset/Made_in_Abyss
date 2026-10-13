import json
import math
import os
import re
import base64
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import storage

APP_TZ = ZoneInfo(os.environ.get('APP_TIMEZONE', 'Europe/Moscow'))

VERDICT_EMOJI = {
    'Отлично': '🏆', 'Хорошо': '✅', 'Удовлетворительно': '⚠️', 'Плохо': '❌', 'Критично': '🚫'
}


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


def fmt_dt(value) -> str:
    if not isinstance(value, datetime):
        return '—'
    return value.astimezone(APP_TZ).strftime('%d.%m.%Y %H:%M')


def parse_json_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return []
    return []


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


def render_recommendations(recs):
    st.markdown(f"""
    <div style="background:rgba(30,40,60,0.7);border:1px solid rgba(100,180,255,0.3);border-radius:12px;padding:20px;margin-top:15px;">
        <h3 style="color:#4a9eff;margin-top:0;">💡 Рекомендации AI</h3>
        {format_recommendations(recs)}
    </div>
    """, unsafe_allow_html=True)


@st.cache_data(show_spinner=False, max_entries=2000)
def thumbnail_data_uri(storage_filename: str):
    """Превью в виде data URI для st.dataframe (ImageColumn)"""
    thumb = storage.make_thumbnail(storage_filename)
    if thumb is None:
        return None
    return 'data:image/jpeg;base64,' + base64.b64encode(thumb).decode('ascii')


def render_report_details(record: dict, show_owner: bool = False):
    """
    Полный текстовый отчёт проверки из БД: фото из хранилища, оценка, метрики, дефекты, советы.
    record должен быть получен через db_repo.get_analysis_by_id(..., requester) — с проверкой прав.
    """
    col_img, col_info = st.columns([1, 1.2])

    with col_img:
        img = storage.read_image(record['storage_filename'])
        if img is not None:
            st.image(img, channels="BGR", use_container_width=True)
        else:
            st.warning("🖼️ Файл изображения не найден в хранилище")
        st.caption(f"📷 {record['filename']} • {record.get('resolution') or '—'} • "
                   f"{safe_float(record.get('file_size_kb')):.1f} КБ")

    with col_info:
        verdict = record.get('verdict') or '—'
        st.markdown(f"""
        <div class="score-card" style="padding:1.2rem;margin-top:0;">
            <div class="score-value" style="font-size:3rem;">{VERDICT_EMOJI.get(verdict, '')} {safe_float(record['overall_score']):.1f}/10</div>
            <div class="score-verdict">{verdict}</div>
        </div>
        """, unsafe_allow_html=True)
        meta = f"🕒 {fmt_dt(record.get('upload_date'))}"
        if show_owner:
            meta += f" • 👤 {record.get('login') or 'Без учётной записи'}"
        st.caption(meta + f" • ID: {str(record['id'])[:8]}…")

        penalties = parse_json_list(record.get('penalties'))
        if penalties:
            st.markdown("**📉 Что снизило оценку:**")
            for penalty in penalties:
                st.markdown(f'<div class="penalty-item">{penalty}</div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("ACF Score", f"{safe_float(record.get('acf_score')):.3f}")
    m2.metric("Яркость", f"{safe_float(record.get('brightness')):.0f}")
    m3.metric("Заполнение", f"{safe_float(record.get('fill_rate')) * 100:.1f}%")
    m4.metric("Индекс чёткости", f"{safe_float(record.get('sharpness_index')):.2f}")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Лапласиан (глоб.)", f"{safe_float(record.get('laplacian_global')):.0f}")
    r2.metric("Лапласиан (лок.)", f"{safe_float(record.get('laplacian_local_median')):.0f}")
    r3.metric("Пересвет", f"{safe_float(record.get('overexposed_pct')):.1f}%")
    r4.metric("Недосвет", f"{safe_float(record.get('underexposed_pct')):.1f}%")

    issues = parse_json_list(record.get('issues'))
    if issues:
        st.warning("⚠️ Выявлено проблем: " + str(len(issues)))
        for issue in issues:
            st.text("• " + issue)
    else:
        st.success("✅ Фото соответствует стандартам!")

    recs = record.get('ai_recommendations')
    if recs:
        render_recommendations(recs)
        with st.expander("📋 Текст отчёта для копирования"):
            st.code(recs, language="text")
