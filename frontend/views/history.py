import pandas as pd
import streamlit as st

from database import db_repo
from auth import current_user, log_action
from report_view import fmt_dt, parse_json_list, render_report_details, thumbnail_data_uri, VERDICT_EMOJI
from theme import page_header

# Страница «Мои проверки»: пользователь видит только собственную историю (S.01.03)
user = current_user()

page_header("🗂️ Мои проверки", "История ваших проверок и текстовые отчёты")

try:
    reports = db_repo.get_user_reports(user['id'])
except Exception as e:
    st.error(f"❌ Не удалось загрузить историю: {e}")
    st.stop()

if not reports:
    st.info("📭 У вас пока нет проверок. Загрузите фото на странице «Анализ фото».")
    st.stop()

table = pd.DataFrame([{
    'Превью': thumbnail_data_uri(r['storage_filename']),
    'Дата': fmt_dt(r['upload_date']),
    'Файл': r['filename'],
    'Оценка': r['overall_score'],
    'Вердикт': f"{VERDICT_EMOJI.get(r['verdict'], '')} {r['verdict'] or '—'}",
    'Проблем': len(parse_json_list(r['issues'])),
} for r in reports])

st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
    column_config={
        'Превью': st.column_config.ImageColumn('Превью', width='small'),
        'Оценка': st.column_config.ProgressColumn('Оценка', min_value=0, max_value=10, format='%.1f'),
    },
)

st.markdown('<div class="section-title">📄 Подробный отчёт</div>', unsafe_allow_html=True)
options = {str(r['id']): f"{fmt_dt(r['upload_date'])} • {r['filename']} • {r['overall_score']}/10" for r in reports}
selected = st.selectbox("Выберите проверку", list(options), format_func=options.get, label_visibility="collapsed")

# Повторная проверка владельца на уровне запроса к БД
record = db_repo.get_analysis_by_id(selected, requester=user)
if record is None:
    st.error("🚫 Отчёт не найден или недоступен")
else:
    if st.session_state.get('history_viewed') != selected:
        st.session_state['history_viewed'] = selected
        log_action('view_report', record['filename'], selected)
    render_report_details(record)
