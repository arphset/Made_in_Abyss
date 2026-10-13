"""
Тесты веб-интерфейса через streamlit.testing (AppTest): вход, роли, страницы без ошибок.
S.01.01 (аутентификация), S.01.02 (админка только для администратора), F.03.02 (наследование прав).
"""
import os
import unittest
import uuid
from datetime import date, timedelta

import testenv
from database import db_repo
from streamlit.testing.v1 import AppTest

APP = os.path.join(testenv.FRONTEND_DIR, 'app.py')
ADMIN_PAGE = os.path.join(testenv.FRONTEND_DIR, 'views', 'admin.py')
ANALYZE_PAGE = os.path.join(testenv.FRONTEND_DIR, 'views', 'analyze.py')
HISTORY_PAGE =os.path.join(testenv.FRONTEND_DIR, 'views', 'history.py')
TIMEOUT = 60
PERIOD = (date.today() - timedelta(days=1), date.today() + timedelta(days=1))


def all_text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [e.value for e in at.error] + [s.value for s in at.subheader]
    parts += [c.value for c in at.caption] + [i.value for i in at.info]
    return '\n'.join(str(p) for p in parts)


def login(at: AppTest, user_login: str, password: str) -> AppTest:
    at.text_input[0].input(user_login)
    at.text_input[1].input(password)
    submit = next(b for b in at.button if b.label == 'Войти')
    submit.click()
    return at.run(timeout=TIMEOUT)


def run_app_as(user: dict) -> AppTest:
    """
    Отрисовка приложения для уже вошедшего пользователя. Дерево AppTest после st.rerun() при смене
    навигации устаревает, поэтому интерфейс после входа проверяется отдельным свежим прогоном.
    """
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state['user'] = user
    return at.run()


def page_links(at: AppTest):
    return [el.proto.label for el in at.get('page_link')]


class LoginTest(unittest.TestCase):

    def test_anonymous_sees_only_login(self):
        at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
        self.assertFalse(at.exception)
        self.assertIn('Войдите', all_text(at))
        self.assertIn('Войти', [b.label for b in at.button])
        self.assertNotIn('user', at.session_state)

    def test_wrong_password(self):
        at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
        at = login(at, testenv.ADMIN_LOGIN, 'wrong')
        self.assertIn('Неверный логин или пароль', all_text(at))
        self.assertNotIn('user', at.session_state)

    def test_registration_validation(self):
        at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
        # поля формы регистрации: логин, пароль, повтор
        at.text_input[2].input('ab')
        at.text_input[3].input('123')
        at.text_input[4].input('123')
        next(b for b in at.button if b.label == 'Зарегистрироваться').click()
        at.run()
        self.assertIn('Логин должен содержать', all_text(at))

    def test_seller_login_has_no_admin_link(self):
        name = 'ui_seller_' + uuid.uuid4().hex[:6]
        db_repo.create_user(name, 'pass123')
        at = login(AppTest.from_file(APP, default_timeout=TIMEOUT).run(), name, 'pass123')
        self.assertFalse(at.exception)
        user = at.session_state['user']
        self.assertEqual(user['role'], 'seller')

        at = run_app_as(user)
        self.assertFalse(at.exception)
        text = all_text(at)
        self.assertIn('Продавец', text)
        self.assertIn('Анализ фото', page_links(at))
        self.assertNotIn('Админ-панель', page_links(at))

    def test_admin_login_has_admin_link(self):
        at = login(AppTest.from_file(APP, default_timeout=TIMEOUT).run(),
                   testenv.ADMIN_LOGIN, testenv.ADMIN_PASSWORD)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['user']['role'], 'admin')

        at = run_app_as(at.session_state['user'])
        self.assertFalse(at.exception)
        self.assertIn('Администратор', all_text(at))
        # F.03.02: у администратора есть и функции продавца
        self.assertEqual(page_links(at), ['Анализ фото', 'Мои проверки', 'Админ-панель'])


class PagesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.seller = db_repo.create_user('ui_pages_' + uuid.uuid4().hex[:6], 'pass123')
        cls.admin = testenv.admin_user()

    def run_page(self, path, user):
        at = AppTest.from_file(path, default_timeout=TIMEOUT)
        at.session_state['user'] = user
        return at.run()

    def test_admin_page_forbidden_for_seller(self):
        """S.01.02: даже при прямом запуске страницы продавец получает 403"""
        at = self.run_page(ADMIN_PAGE, self.seller)
        self.assertFalse(at.exception)
        self.assertIn('Доступ запрещён (403)', all_text(at))
        self.assertEqual(len(at.tabs), 0, "содержимое админки не отрисовано")
        denied = db_repo.get_activity_log(*PERIOD, user_ids=[self.seller['id']], actions=['access_denied'])
        self.assertTrue(denied, "отказ в доступе записан в журнал")

    def test_admin_page_renders_for_admin(self):
        at = self.run_page(ADMIN_PAGE, self.admin)
        self.assertFalse(at.exception, at.exception)
        self.assertEqual([t.label for t in at.tabs],
                         ['📊 Статистика', '🗂️ Отчёты проверок', '📜 Журнал действий', '👥 Пользователи'])
        self.assertNotIn('Доступ запрещён', all_text(at))

    def test_admin_page_all_periods(self):
        at = self.run_page(ADMIN_PAGE, self.admin)
        for preset in ['7 дней', '90 дней', 'Всё время']:
            at.radio(key='admin_period_preset').set_value(preset).run()
            self.assertFalse(at.exception, f"{preset}: {at.exception}")

    def test_analyze_page_has_uploader(self):
        """U.01.01 / F.01.01: страница анализа с загрузкой JPG/PNG"""
        at = self.run_page(ANALYZE_PAGE, self.seller)
        self.assertFalse(at.exception)
        self.assertIn('AI-анализ качества фото', all_text(at))
        uploaders = at.get('file_uploader')
        self.assertEqual(len(uploaders), 1)
        self.assertEqual(set(uploaders[0].proto.type), {'.jpg', '.jpeg', '.png'})

    def test_history_page_empty_for_new_seller(self):
        at = self.run_page(HISTORY_PAGE, self.seller)
        self.assertFalse(at.exception)
        self.assertIn('пока нет проверок', all_text(at))


if __name__ == '__main__':
    unittest.main()
