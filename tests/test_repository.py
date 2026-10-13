"""Тесты слоя данных на изолированной БД: пользователи, права, статистика, журнал (D.01.01, S.01.*, F.03.01)"""
import unittest
import uuid
from datetime import date, timedelta

import testenv
from database import db_repo
from database.repository import SUCCESS_SCORE

TODAY = date.today()
PERIOD = (TODAY - timedelta(days=1), TODAY + timedelta(days=1))


def make_analysis(user_id, score, verdict, issues=(), total_ms=None):
    return db_repo.save_analysis_result({
        'filename': f'{uuid.uuid4().hex[:6]}.jpg',
        'storage_filename': f'{uuid.uuid4()}.jpg',
        'user_id': user_id,
        'overall_score': score,
        'verdict': verdict,
        'summary': {'issues': list(issues)},
        'penalties': [],
        'ai_recommendations': 'Метрики фото:\n...',
        'timings': {'cv_ms': 800, 'llm_ms': (total_ms or 0) - 800, 'total_ms': total_ms} if total_ms else {},
        'file_info': {'resolution': '100x100', 'file_size_kb': 10},
    })


class UsersTest(unittest.TestCase):

    def test_register_and_authenticate(self):
        login = 'u_' + uuid.uuid4().hex[:8]
        user = db_repo.create_user(login, 'pass123')
        self.assertEqual(user['role'], 'seller')
        self.assertEqual(db_repo.authenticate(login, 'pass123')['id'], user['id'])
        self.assertIsNone(db_repo.authenticate(login, 'wrong'))
        self.assertIsNone(db_repo.authenticate('no_such_user', 'pass123'))

    def test_login_is_unique(self):
        login = 'u_' + uuid.uuid4().hex[:8]
        db_repo.create_user(login, 'pass123')
        with self.assertRaises(ValueError):
            db_repo.create_user(login, 'other')

    def test_seeded_admin(self):
        admin = testenv.admin_user()
        self.assertIsNotNone(admin)
        self.assertEqual(admin['role'], 'admin')
        db_repo.ensure_admin(testenv.ADMIN_LOGIN, 'другой пароль')  # повторный сид не меняет пароль
        self.assertIsNotNone(testenv.admin_user())


class AccessControlTest(unittest.TestCase):
    """S.01.02 / S.01.03: продавец видит только свои проверки, администратор — все"""

    @classmethod
    def setUpClass(cls):
        cls.alice = db_repo.create_user('alice_' + uuid.uuid4().hex[:6], 'pass123')
        cls.bob = db_repo.create_user('bob_' + uuid.uuid4().hex[:6], 'pass123')
        cls.admin = testenv.admin_user()
        cls.alice_report = make_analysis(cls.alice['id'], 8.0, 'Хорошо')

    def test_owner_sees_report(self):
        self.assertIsNotNone(db_repo.get_analysis_by_id(self.alice_report, requester=self.alice))

    def test_other_seller_denied(self):
        self.assertIsNone(db_repo.get_analysis_by_id(self.alice_report, requester=self.bob))

    def test_admin_sees_everything(self):
        record = db_repo.get_analysis_by_id(self.alice_report, requester=self.admin)
        self.assertEqual(record['login'], self.alice['login'])

    def test_history_is_private(self):
        self.assertIn(self.alice_report, [str(r['id']) for r in db_repo.get_user_reports(self.alice['id'])])
        self.assertNotIn(self.alice_report, [str(r['id']) for r in db_repo.get_user_reports(self.bob['id'])])


class StatisticsTest(unittest.TestCase):
    """6.1: агрегированные запросы на контролируемом наборе данных"""

    @classmethod
    def setUpClass(cls):
        cls.user = db_repo.create_user('stats_' + uuid.uuid4().hex[:6], 'pass123')
        cls.before = db_repo.get_period_summary(*PERIOD)
        make_analysis(cls.user['id'], 9.5, 'Отлично', total_ms=12000)
        make_analysis(cls.user['id'], 7.0, 'Хорошо', ['Недосвет (провал в тенях)'], total_ms=8000)
        make_analysis(cls.user['id'], 3.0, 'Критично',
                      ['Малое заполнение кадра (5.0%, рекомендуется >30%)', 'Недосвет (провал в тенях)'],
                      total_ms=31000)
        cls.after = db_repo.get_period_summary(*PERIOD)

    def test_summary_counts(self):
        self.assertEqual(self.after['total'] - self.before['total'], 3)
        self.assertEqual(self.after['success'] - self.before['success'], 2, f"успешные: ≥ {SUCCESS_SCORE}")
        self.assertEqual(self.after['failed'] - self.before['failed'], 1)

    def test_daily_and_verdicts(self):
        days = db_repo.get_daily_stats(*PERIOD)
        self.assertEqual(sum(d['total'] for d in days), self.after['total'])
        verdicts = {v['verdict']: v['count'] for v in db_repo.get_verdict_distribution(*PERIOD)}
        self.assertGreaterEqual(verdicts.get('Отлично', 0), 1)

    def test_top_users(self):
        top = {u['login']: u for u in db_repo.get_top_users(*PERIOD)}
        self.assertEqual(top[self.user['login']]['checks'], 3)

    def test_top_issues_grouped_without_details(self):
        issues = {i['issue']: i['count'] for i in db_repo.get_top_issues(*PERIOD, limit=50)}
        self.assertGreaterEqual(issues.get('Недосвет', 0), 2)
        self.assertIn('Малое заполнение кадра', issues, "проценты в скобках отбрасываются")

    def test_response_time_stats(self):
        rt = db_repo.get_response_time_stats(*PERIOD)
        self.assertGreaterEqual(rt['measured'], 3)
        self.assertGreaterEqual(rt['over_limit'], 1)
        self.assertGreaterEqual(rt['total_max_s'], 31.0)
        self.assertGreaterEqual(len(db_repo.get_response_times(*PERIOD)), 3)

    def test_reports_filters(self):
        mine = db_repo.get_reports(*PERIOD, user_ids=[self.user['id']], include_anonymous=False)
        self.assertEqual(len(mine), 3)
        bad = db_repo.get_reports(*PERIOD, user_ids=[self.user['id']], verdicts=['Критично'],
                                  include_anonymous=False)
        self.assertEqual(len(bad), 1)
        past = db_repo.get_reports(TODAY - timedelta(days=30), TODAY - timedelta(days=20))
        self.assertEqual(past, [])


class ActivityLogTest(unittest.TestCase):

    def test_log_and_filter(self):
        user = db_repo.create_user('log_' + uuid.uuid4().hex[:6], 'pass123')
        db_repo.log_action(user['id'], 'login')
        db_repo.log_action(user['id'], 'upload', 'photo.jpg')
        db_repo.log_action(None, 'login_failed', 'Логин: hacker')
        rows = db_repo.get_activity_log(*PERIOD, user_ids=[user['id']])
        self.assertEqual({r['action'] for r in rows}, {'login', 'upload'})
        failed = db_repo.get_activity_log(*PERIOD, actions=['login_failed'])
        self.assertTrue(any(r['details'] == 'Логин: hacker' for r in failed))

    def test_log_never_raises(self):
        db_repo.log_action(999999, 'login')  # несуществующий пользователь — ошибка FK гасится


class MigrationsTest(unittest.TestCase):
    def test_migrations_are_idempotent(self):
        db_repo.ensure_schema()
        db_repo.ensure_schema()


if __name__ == '__main__':
    unittest.main()
