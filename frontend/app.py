import os
import sys

import streamlit as st

# Настройка путей
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
ml_module_path = os.path.join(project_root, 'ML&CV_Module')
sys.path.insert(0, ml_module_path)
sys.path.insert(0, current_dir)

# Импорт репозитория базы данных
sys.path.insert(0, project_root)
from database import db_repo

from theme import apply_theme
from auth import ROLE_LABELS, current_user, is_admin, login_page, logout

st.set_page_config(
    page_title="QualityJPG",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="collapsed"
)


@st.cache_resource
def init_database():
    """Миграции схемы (users, activity_log, user_id) и учётная запись администратора — один раз на процесс"""
    db_repo.ensure_schema()
    db_repo.ensure_admin(os.environ.get('ADMIN_LOGIN', ''), os.environ.get('ADMIN_PASSWORD', ''))
    return True


apply_theme()

try:
    init_database()
except Exception as e:
    st.error(f"❌ База данных недоступна: {e}")
    st.stop()

# ==========================================
# АУТЕНТИФИКАЦИЯ (S.01.01)
# ==========================================
user = current_user()
if user is None:
    st.navigation([st.Page(login_page, title="Вход", icon="🔑")], position="hidden").run()
    st.stop()

# ==========================================
# РАЗГРАНИЧЕНИЕ ПРАВ (S.01.02, F.03.02)
# Продавец: анализ + своя история. Администратор: всё то же + админ-панель.
# Страница админки не регистрируется для продавца вовсе, а сама дополнительно проверяет роль.
# ==========================================
analyze_page = st.Page(os.path.join(current_dir, "views", "analyze.py"), title="Анализ фото", icon="📸",
                       url_path="analyze", default=True)
history_page = st.Page(os.path.join(current_dir, "views", "history.py"), title="Мои проверки", icon="🗂️",
                       url_path="history")
pages = [analyze_page, history_page]
if is_admin():
    admin_page = st.Page(os.path.join(current_dir, "views", "admin.py"), title="Админ-панель", icon="🛡️",
                         url_path="admin")
    pages.append(admin_page)

nav = st.navigation(pages, position="hidden")

# Верхняя панель навигации в стиле основной страницы
nav_cols = st.columns([1, 1, 1, 2.2, 0.8]) if is_admin() else st.columns([1, 1, 3.2, 0.8])
for col, page in zip(nav_cols, pages):
    col.page_link(page, use_container_width=True)
with nav_cols[-2]:
    badge_class = 'role-badge admin' if user['role'] == 'admin' else 'role-badge'
    st.markdown(
        f'<div class="nav-user">👤 {user["login"]}'
        f'<span class="{badge_class}">{ROLE_LABELS.get(user["role"], user["role"])}</span></div>',
        unsafe_allow_html=True)
with nav_cols[-1]:
    if st.button("🚪 Выйти", key="logout_btn", use_container_width=True):
        logout()
        st.rerun()

nav.run()
