from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from database import db_repo
from database.repository import SUCCESS_SCORE
from auth import ACTION_LABELS, ROLE_LABELS, current_user, log_action, require_admin
from report_view import APP_TZ, fmt_dt, parse_json_list, render_report_details, thumbnail_data_uri, VERDICT_EMOJI
from theme import page_header, stat_card
import storage

# Админ-панель (F.03.01). Права проверяются на сервере до любого запроса к БД (S.01.02)
require_admin()
user = current_user()

page_header("🛡️ Админ-панель", "Статистика системы, отчёты всех проверок и журнал действий пользователей")

ACCENT = '#4a9eff'
VIOLET = '#6c5ce7'
GOOD = '#4ade80'
BAD = '#f87171'
RESPONSE_LIMIT_S = 30.0  # R.01.01
VERDICT_ORDER = ['Отлично', 'Хорошо', 'Удовлетворительно', 'Плохо', 'Критично']
VERDICT_COLORS = ['#38bdf8', GOOD, '#facc15', '#fb923c', BAD]


def style_chart(chart: alt.Chart, height: int = 280) -> alt.Chart:
    """Оформление графиков Altair в тёмной палитре основной страницы"""
    return (
        chart.properties(height=height, background='transparent')
        .configure_axis(labelColor='rgba(200,220,255,0.8)', titleColor='rgba(200,220,255,0.8)',
                        gridColor='rgba(100,180,255,0.12)', domainColor='rgba(100,180,255,0.3)',
                        labelFontSize=12, titleFontSize=12)
        .configure_legend(labelColor='rgba(200,220,255,0.85)', titleColor='rgba(200,220,255,0.85)',
                          orient='bottom')
        .configure_view(strokeWidth=0)
    )


def show_chart(chart: alt.Chart, height: int = 280):
    st.altair_chart(style_chart(chart, height), use_container_width=True, theme=None)


# ==========================================
# ФИЛЬТР ПЕРИОДА (общий для всех вкладок)
# ==========================================
today = datetime.now(APP_TZ).date()
PRESETS = {'7 дней': 7, '30 дней': 30, '90 дней': 90, 'Всё время': None, 'Свой период': -1}

f1, f2 = st.columns([1.4, 1])
with f1:
    preset = st.radio("Период", list(PRESETS), index=1, horizontal=True, key='admin_period_preset')
with f2:
    if PRESETS[preset] == -1:
        picked = st.date_input("Даты", value=(today - timedelta(days=30), today), max_value=today,
                               format="DD.MM.YYYY", key='admin_period_dates')
        date_from, date_to = (picked if len(picked) == 2 else (picked[0], picked[0]))
    else:
        days = PRESETS[preset]
        date_from = today - timedelta(days=days - 1) if days else date(2000, 1, 1)
        date_to = today
        st.markdown(
            f'<div class="nav-user" style="text-align:left;padding-top:30px;">📅 '
            f'{"за всё время" if not days else date_from.strftime("%d.%m.%Y") + " — " + date_to.strftime("%d.%m.%Y")}</div>',
            unsafe_allow_html=True)

tab_stats, tab_reports, tab_log, tab_users = st.tabs(
    ["📊 Статистика", "🗂️ Отчёты проверок", "📜 Журнал действий", "👥 Пользователи"])

# ==========================================
# ВКЛАДКА 1: СТАТИСТИКА (задачи 6.1, 6.2)
# ==========================================
with tab_stats:
    try:
        summary = db_repo.get_period_summary(date_from, date_to)
        daily = pd.DataFrame(db_repo.get_daily_stats(date_from, date_to))
        verdicts = pd.DataFrame(db_repo.get_verdict_distribution(date_from, date_to))
        top_users = pd.DataFrame(db_repo.get_top_users(date_from, date_to))
        top_issues = pd.DataFrame(db_repo.get_top_issues(date_from, date_to))
    except Exception as e:
        st.error(f"❌ Не удалось получить статистику из БД: {e}")
        st.stop()

    total = summary['total'] or 0
    success_pct = f"{summary['success'] / total * 100:.0f}%" if total else '—'
    failed_pct = f"{summary['failed'] / total * 100:.0f}%" if total else '—'

    c = st.columns(6)
    stat_card(c[0], total, "Проверок за период")
    stat_card(c[1], success_pct, f"Успешных (≥ {SUCCESS_SCORE:g})", 'good')
    stat_card(c[2], failed_pct, f"Неуспешных (< {SUCCESS_SCORE:g})", 'bad')
    stat_card(c[3], summary['avg_score'] if summary['avg_score'] is not None else '—', "Средняя оценка")
    stat_card(c[4], summary['active_users'], "Активных пользователей")
    stat_card(c[5], summary['analysis_errors'], "Сбоев анализа", 'bad' if summary['analysis_errors'] else '')

    if not total:
        st.info("📭 За выбранный период проверок нет")
    else:
        st.markdown('<div class="section-title">📈 Проверки по дням</div>', unsafe_allow_html=True)
        # Ось по дням как категории: столбцы одинаковой ширины при любом числе дней
        daily['Дата'] = pd.to_datetime(daily['day']).dt.strftime('%d.%m')
        daily_long = daily.melt(id_vars=['Дата'], value_vars=['success', 'failed'],
                                var_name='Результат', value_name='Проверок')
        daily_long['Результат'] = daily_long['Результат'].map({'success': 'Успешные', 'failed': 'Неуспешные'})
        show_chart(
            alt.Chart(daily_long).mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=28).encode(
                x=alt.X('Дата:O', title=None, sort=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y('Проверок:Q', title='Проверок', stack=True, axis=alt.Axis(tickMinStep=1)),
                color=alt.Color('Результат:N', scale=alt.Scale(domain=['Успешные', 'Неуспешные'], range=[GOOD, BAD]),
                                title=None),
                tooltip=['Дата:O', 'Результат:N', 'Проверок:Q'],
            )
        )

        left, right = st.columns(2)
        with left:
            st.markdown('<div class="section-title">🏷️ Распределение по вердиктам</div>', unsafe_allow_html=True)
            show_chart(
                alt.Chart(verdicts).mark_arc(innerRadius=60, stroke='#0a0f1a').encode(
                    theta=alt.Theta('count:Q'),
                    color=alt.Color('verdict:N', title=None,
                                    scale=alt.Scale(domain=VERDICT_ORDER, range=VERDICT_COLORS)),
                    tooltip=[alt.Tooltip('verdict:N', title='Вердикт'), alt.Tooltip('count:Q', title='Проверок')],
                ), height=300
            )
        with right:
            st.markdown('<div class="section-title">⚠️ Частые дефекты</div>', unsafe_allow_html=True)
            if top_issues.empty:
                st.success("✅ Дефектов не выявлено")
            else:
                show_chart(
                    alt.Chart(top_issues).mark_bar(color=VIOLET, cornerRadiusEnd=4).encode(
                        x=alt.X('count:Q', title='Случаев', axis=alt.Axis(tickMinStep=1)),
                        y=alt.Y('issue:N', sort='-x', title=None, axis=alt.Axis(labelLimit=260)),
                        tooltip=[alt.Tooltip('issue:N', title='Дефект'), alt.Tooltip('count:Q', title='Случаев')],
                    ), height=300
                )

        st.markdown('<div class="section-title">🏆 Активность пользователей (топ по загрузкам)</div>',
                    unsafe_allow_html=True)
        top_users['success_pct'] = (top_users['success'] / top_users['checks'] * 100).round(0)
        top_users['last_check'] = top_users['last_check'].map(fmt_dt)
        st.dataframe(
            top_users[['login', 'checks', 'success_pct', 'avg_score', 'last_check']],
            hide_index=True, use_container_width=True,
            column_config={
                'login': 'Пользователь',
                'checks': st.column_config.ProgressColumn('Проверок', min_value=0,
                                                          max_value=int(top_users['checks'].max()), format='%d'),
                'success_pct': st.column_config.NumberColumn('Успешных', format='%d%%'),
                'avg_score': st.column_config.NumberColumn('Средняя оценка', format='%.2f'),
                'last_check': 'Последняя проверка',
            },
        )

    # Время отклика (задача 7.1, R.01.01)
    st.markdown('<div class="section-title">⏱️ Время отклика (норматив — 30 с)</div>', unsafe_allow_html=True)
    rt = db_repo.get_response_time_stats(date_from, date_to, RESPONSE_LIMIT_S)
    if not rt['measured']:
        st.info("📭 За период нет проверок с замером времени (замер ведётся с Спринта 4)")
    else:
        t = st.columns(5)
        stat_card(t[0], f"{rt['cv_avg_s']:.1f} с", "Первичный отчёт (среднее)")
        stat_card(t[1], f"{rt['total_avg_s']:.1f} с", "Полный ответ (среднее)")
        stat_card(t[2], f"{rt['total_p95_s']:.1f} с", "95-й перцентиль")
        stat_card(t[3], f"{rt['total_max_s']:.1f} с", "Максимум",
                  'bad' if rt['total_max_s'] > RESPONSE_LIMIT_S else 'good')
        stat_card(t[4], f"{rt['over_limit']} из {rt['measured']}", "Превышений норматива",
                  'bad' if rt['over_limit'] else 'good')

        times = pd.DataFrame(db_repo.get_response_times(date_from, date_to))
        times['Проверка'] = [f"{i + 1}. {name}" for i, name in enumerate(times['filename'])]
        times_long = times.melt(id_vars=['Проверка', 'total_s'], value_vars=['cv_s', 'llm_s'],
                                var_name='Этап', value_name='Секунд')
        times_long['Этап'] = times_long['Этап'].map({'cv_s': 'CV-анализ', 'llm_s': 'Рекомендации AI'})
        bars = alt.Chart(times_long).mark_bar(size=18).encode(
            x=alt.X('Проверка:N', sort=None, title=None, axis=alt.Axis(labels=False, ticks=False)),
            y=alt.Y('Секунд:Q', stack=True, title='Секунд'),
            color=alt.Color('Этап:N', title=None,
                            scale=alt.Scale(domain=['CV-анализ', 'Рекомендации AI'], range=[ACCENT, VIOLET])),
            tooltip=['Проверка:N', 'Этап:N', alt.Tooltip('Секунд:Q', format='.1f'),
                     alt.Tooltip('total_s:Q', title='Всего, с', format='.1f')],
        )
        limit_line = alt.Chart(pd.DataFrame({'y': [RESPONSE_LIMIT_S]})).mark_rule(
            color=BAD, strokeDash=[6, 4], strokeWidth=2).encode(y='y:Q')
        show_chart(bars + limit_line, height=260)

    # Сверка файлового хранилища с БД (D.01.02)
    st.markdown('<div class="section-title">💾 Файловое хранилище</div>', unsafe_allow_html=True)
    try:
        overview = storage.storage_overview(db_repo.get_all_storage_filenames())
        s = st.columns(4)
        stat_card(s[0], overview['files'], "Файлов в хранилище")
        stat_card(s[1], f"{overview['size_mb']} МБ", "Занято на диске")
        stat_card(s[2], overview['orphan_files'], "Файлов без записи в БД", 'bad' if overview['orphan_files'] else '')
        stat_card(s[3], overview['missing_files'], "Записей без файла", 'bad' if overview['missing_files'] else '')
    except Exception as e:
        st.warning(f"⚠️ Не удалось проверить хранилище: {e}")

# ==========================================
# ВКЛАДКА 2: ОТЧЁТЫ ВСЕХ ПРОВЕРОК (задача 6.3)
# ==========================================
with tab_reports:
    users = db_repo.get_users_overview()
    user_names = {u['id']: u['login'] for u in users}

    r1, r2, r3 = st.columns([1.4, 1.4, 1])
    with r1:
        selected_users = st.multiselect("Пользователи", list(user_names), format_func=user_names.get,
                                        placeholder="Все пользователи")
    with r2:
        selected_verdicts = st.multiselect("Вердикт", VERDICT_ORDER, placeholder="Все вердикты")
    with r3:
        include_anonymous = st.checkbox("Проверки без учётной записи", value=not selected_users,
                                        help="Записи, созданные до введения авторизации (Спринт 1–2)")

    reports = db_repo.get_reports(date_from, date_to, selected_users, selected_verdicts, include_anonymous)

    if not reports:
        st.info("📭 По выбранным фильтрам проверок нет")
    else:
        st.caption(f"Найдено проверок: {len(reports)}" + (" (показаны последние 500)" if len(reports) >= 500 else ""))
        table = pd.DataFrame([{
            'Превью': thumbnail_data_uri(r['storage_filename']),
            'Дата': fmt_dt(r['upload_date']),
            'Пользователь': r['login'] or '—',
            'Файл': r['filename'],
            'Оценка': r['overall_score'],
            'Вердикт': f"{VERDICT_EMOJI.get(r['verdict'], '')} {r['verdict'] or '—'}",
            'Проблем': len(parse_json_list(r['issues'])),
            'Разрешение': r['resolution'],
        } for r in reports])
        st.dataframe(
            table, hide_index=True, use_container_width=True,
            column_config={
                'Превью': st.column_config.ImageColumn('Превью', width='small'),
                'Оценка': st.column_config.ProgressColumn('Оценка', min_value=0, max_value=10, format='%.1f'),
            },
        )
        st.download_button("⬇️ Выгрузить таблицу в CSV",
                           table.drop(columns=['Превью']).to_csv(index=False).encode('utf-8-sig'),
                           file_name=f"qualityjpg_reports_{date_from}_{date_to}.csv", mime='text/csv')

        st.markdown('<div class="section-title">📄 Текстовый отчёт проверки</div>', unsafe_allow_html=True)
        options = {str(r['id']): f"{fmt_dt(r['upload_date'])} • {r['login'] or '—'} • {r['filename']} • "
                                 f"{r['overall_score']}/10" for r in reports}
        selected = st.selectbox("Выберите проверку", list(options), format_func=options.get,
                                label_visibility="collapsed", key='admin_report_select')
        record = db_repo.get_analysis_by_id(selected, requester=user)
        if record:
            if st.session_state.get('admin_viewed') != selected:
                st.session_state['admin_viewed'] = selected
                log_action('view_report', f"{record['filename']} (владелец: {record['login'] or '—'})", selected)
            render_report_details(record, show_owner=True)

# ==========================================
# ВКЛАДКА 3: ЖУРНАЛ ДЕЙСТВИЙ
# ==========================================
with tab_log:
    l1, l2 = st.columns(2)
    with l1:
        log_users = st.multiselect("Пользователи", list(user_names), format_func=user_names.get,
                                   placeholder="Все пользователи", key='log_users')
    with l2:
        log_actions = st.multiselect("Операции", list(ACTION_LABELS), format_func=ACTION_LABELS.get,
                                     placeholder="Все операции", key='log_actions')

    log = db_repo.get_activity_log(date_from, date_to, log_users, log_actions)
    if not log:
        st.info("📭 Записей в журнале за период нет")
    else:
        log_df = pd.DataFrame([{
            'Время': fmt_dt(r['created_at']),
            'Пользователь': r['login'] or '—',
            'Роль': ROLE_LABELS.get(r['role'], '—'),
            'Операция': ACTION_LABELS.get(r['action'], r['action']),
            'Подробности': r['details'] or '',
            'ID проверки': str(r['analysis_id'])[:8] if r['analysis_id'] else '',
        } for r in log])
        st.caption(f"Записей: {len(log_df)}" + (" (показаны последние 500)" if len(log_df) >= 500 else ""))
        st.dataframe(log_df, hide_index=True, use_container_width=True, height=520)

# ==========================================
# ВКЛАДКА 4: ПОЛЬЗОВАТЕЛИ
# ==========================================
with tab_users:
    users_df = pd.DataFrame([{
        'Логин': u['login'],
        'Роль': ROLE_LABELS.get(u['role'], u['role']),
        'Зарегистрирован': fmt_dt(u['created_at']),
        'Последний вход': fmt_dt(u['last_login']),
        'Проверок': u['checks'],
        'Средняя оценка': u['avg_score'],
        'Последняя проверка': fmt_dt(u['last_check']),
    } for u in users])
    st.dataframe(users_df, hide_index=True, use_container_width=True,
                 column_config={'Средняя оценка': st.column_config.NumberColumn(format='%.2f')})
