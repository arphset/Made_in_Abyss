import re
from typing import Optional, Dict

import streamlit as st

from database import db_repo

# Коды операций журнала и их подписи для админ-панели
ACTION_LABELS = {
    'register': '🆕 Регистрация',
    'login': '🔑 Вход',
    'login_failed': '⛔ Неудачный вход',
    'logout': '🚪 Выход',
    'upload': '📤 Загрузка фото',
    'analysis_ok': '✅ Анализ выполнен',
    'analysis_error': '❌ Ошибка анализа',
    'view_report': '👁️ Просмотр отчёта',
    'access_denied': '🚫 Отказ в доступе',
}

ROLE_LABELS = {'seller': 'Продавец', 'admin': 'Администратор'}

_LOGIN_RE = re.compile(r'^[A-Za-z0-9_.\-]{3,32}$')


def current_user() -> Optional[Dict]:
    return st.session_state.get('user')


def is_admin() -> bool:
    user = current_user()
    return bool(user and user['role'] == 'admin')


def log_action(action: str, details: str = '', analysis_id: Optional[str] = None):
    user = current_user()
    db_repo.log_action(user['id'] if user else None, action, details, analysis_id)


def logout():
    log_action('logout')
    st.session_state.clear()


def require_admin():
    """
    Проверка прав на сервере (S.01.02, шаг 3 диаграммы «Просмотр статистики»).
    Продавец получает сообщение об ошибке, выполнение страницы прекращается.
    """
    if not is_admin():
        log_action('access_denied', 'Попытка открыть админ-панель')
        st.error("🚫 Доступ запрещён (403). Раздел доступен только администраторам.")
        st.stop()


def _login_form():
    with st.form('login_form'):
        login = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти")
    if submitted:
        user = db_repo.authenticate(login.strip(), password)
        if user is None:
            db_repo.log_action(None, 'login_failed', f"Логин: {login.strip()[:64]}")
            st.error("⛔ Неверный логин или пароль")
            return
        st.session_state['user'] = user
        log_action('login')
        st.rerun()


def _register_form():
    with st.form('register_form'):
        login = st.text_input("Логин", help="3–32 символа: латиница, цифры, _ . -")
        password = st.text_input("Пароль", type="password", help="Не менее 6 символов")
        password2 = st.text_input("Повторите пароль", type="password")
        submitted = st.form_submit_button("Зарегистрироваться")
    if submitted:
        login = login.strip()
        if not _LOGIN_RE.match(login):
            st.error("⛔ Логин должен содержать 3–32 символа: латиница, цифры, _ . -")
        elif len(password) < 6:
            st.error("⛔ Пароль должен содержать не менее 6 символов")
        elif password != password2:
            st.error("⛔ Пароли не совпадают")
        else:
            try:
                # Самостоятельная регистрация — только роль «Продавец»
                user = db_repo.create_user(login, password, role='seller')
            except ValueError as e:
                st.error("⛔ " + str(e))
                return
            st.session_state['user'] = user
            log_action('register')
            st.rerun()


def login_page():
    """Страница входа (S.01.01): доступ к системе только после авторизации"""
    from theme import page_header

    page_header("📸 QualityJPG", "Войдите, чтобы проверить качество фото")
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        tab_login, tab_register = st.tabs(["🔑 Вход", "🆕 Регистрация"])
        with tab_login:
            _login_form()
        with tab_register:
            _register_form()
