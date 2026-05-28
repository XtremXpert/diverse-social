from datetime import timedelta

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo import fields


def _make_user(env, login, *, login_date=None):
    user = env['res.users'].create({
        'name': login.capitalize(),
        'login': login,
        'email': f'{login}@digest.test',
        'password': 'Test1234!',
        'group_ids': [(4, env.ref('base.group_user').id),
                      (4, env.ref('social_base.group_social_user').id)],
    })
    profile = env['club_social_profile.profile'].sudo().get_or_create_for_user(user)
    profile.sudo().write({'onboarding_done': True, 'digest_email_enabled': True})
    if login_date:
        # login_date is a related (non-stored) field; we need a real row in
        # res_users_log with the right create_date so the digest's SQL query
        # sees it. ORM create() ignores `create_date` writes, so we insert
        # directly. flush_all() so the row is visible in the next SQL read.
        env.cr.execute(
            "INSERT INTO res_users_log (create_uid, create_date) VALUES (%s, %s)",
            (user.id, login_date),
        )
        env.cr.flush()
    return user, profile


def _make_unread(env, recipient, actor, notif_type='post_like'):
    return env['club_social_profile.notification'].sudo().create({
        'user_id': recipient.id,
        'actor_id': actor.id,
        'type': notif_type,
        'body': 'something happened',
        'is_read': False,
    })


@tagged('social_notifications', 'digest', 'post_install', '-at_install')
class TestDigestEligibility(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Service = self.env['social_notifications.digest_service']
        # Default: 3 days inactivity required
        now = fields.Datetime.now()
        self.long_ago = now - timedelta(days=10)
        self.recent = now - timedelta(hours=2)

    def test_active_user_excluded(self):
        alice, _ = _make_user(self.env, 'eligib_alice', login_date=self.recent)
        bob, _ = _make_user(self.env, 'eligib_bob', login_date=self.long_ago)
        _make_unread(self.env, alice, bob)
        ids = self.Service._eligible_user_ids()
        self.assertNotIn(alice.id, ids, 'recently active user must not be eligible')

    def test_inactive_user_with_unread_eligible(self):
        alice, _ = _make_user(self.env, 'eligib_alice', login_date=self.long_ago)
        bob, _ = _make_user(self.env, 'eligib_bob')
        _make_unread(self.env, alice, bob)
        ids = self.Service._eligible_user_ids()
        self.assertIn(alice.id, ids)

    def test_user_without_unread_excluded(self):
        alice, _ = _make_user(self.env, 'eligib_alice', login_date=self.long_ago)
        ids = self.Service._eligible_user_ids()
        self.assertNotIn(alice.id, ids, 'no unread notifs → no digest')

    def test_optout_excluded(self):
        alice, alice_p = _make_user(self.env, 'eligib_alice', login_date=self.long_ago)
        bob, _ = _make_user(self.env, 'eligib_bob')
        _make_unread(self.env, alice, bob)
        alice_p.digest_email_enabled = False
        ids = self.Service._eligible_user_ids()
        self.assertNotIn(alice.id, ids)

    def test_recent_digest_excluded(self):
        alice, _ = _make_user(self.env, 'eligib_alice', login_date=self.long_ago)
        bob, _ = _make_user(self.env, 'eligib_bob')
        _make_unread(self.env, alice, bob)
        alice.sudo().last_notification_digest_sent = fields.Datetime.now() - timedelta(days=2)
        ids = self.Service._eligible_user_ids()
        self.assertNotIn(alice.id, ids, 'digest sent within throttle window must skip')


@tagged('social_notifications', 'digest', 'post_install', '-at_install')
class TestDigestSummary(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Service = self.env['social_notifications.digest_service']
        self.alice, _ = _make_user(self.env, 'sum_alice')
        self.b1, _ = _make_user(self.env, 'sum_b1')
        self.b2, _ = _make_user(self.env, 'sum_b2')
        self.b3, _ = _make_user(self.env, 'sum_b3')
        self.b4, _ = _make_user(self.env, 'sum_b4')

    def test_groups_by_type(self):
        _make_unread(self.env, self.alice, self.b1, 'post_like')
        _make_unread(self.env, self.alice, self.b2, 'post_like')
        _make_unread(self.env, self.alice, self.b3, 'post_comment')
        summary = self.Service._summary_for_user(self.alice)
        by_type = {g['type']: g for g in summary}
        self.assertEqual(by_type['post_like']['count'], 2)
        self.assertEqual(by_type['post_comment']['count'], 1)

    def test_sample_names_capped_with_extras(self):
        # 4 distinct actors on the same notif type
        for actor in (self.b1, self.b2, self.b3, self.b4):
            _make_unread(self.env, self.alice, actor, 'post_like')
        summary = self.Service._summary_for_user(self.alice, name_cap=3)
        g = next(g for g in summary if g['type'] == 'post_like')
        self.assertEqual(len(g['sample_names']), 3)
        self.assertEqual(g['extra_count'], 1)

    def test_stealth_name_preferred(self):
        bob_profile = self.env['club_social_profile.profile'].sudo().search(
            [('user_id', '=', self.b1.id)], limit=1,
        )
        bob_profile.stealth_name = 'NightOwl'
        _make_unread(self.env, self.alice, self.b1, 'new_message')
        summary = self.Service._summary_for_user(self.alice)
        g = next(g for g in summary if g['type'] == 'new_message')
        self.assertIn('NightOwl', g['sample_names'])
        self.assertNotIn(self.b1.name, g['sample_names'])

    def test_empty_when_no_unread(self):
        self.assertEqual(self.Service._summary_for_user(self.alice), [])


@tagged('social_notifications', 'digest', 'post_install', '-at_install')
class TestDigestToken(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Service = self.env['social_notifications.digest_service']

    def test_token_is_deterministic(self):
        t1 = self.Service._unsubscribe_token(42)
        t2 = self.Service._unsubscribe_token(42)
        self.assertEqual(t1, t2)

    def test_token_differs_per_user(self):
        self.assertNotEqual(
            self.Service._unsubscribe_token(1),
            self.Service._unsubscribe_token(2),
        )

    def test_verify_accepts_own_token(self):
        token = self.Service._unsubscribe_token(7)
        self.assertTrue(self.Service._verify_unsubscribe_token(7, token))

    def test_verify_rejects_tampered(self):
        token = self.Service._unsubscribe_token(7)
        self.assertFalse(self.Service._verify_unsubscribe_token(7, token + 'x'))
        self.assertFalse(self.Service._verify_unsubscribe_token(7, ''))
        self.assertFalse(self.Service._verify_unsubscribe_token(7, None))

    def test_verify_rejects_other_user(self):
        token = self.Service._unsubscribe_token(7)
        self.assertFalse(self.Service._verify_unsubscribe_token(8, token))


@tagged('social_notifications', 'digest', 'post_install', '-at_install')
class TestDigestSendFlow(HttpCase):

    def setUp(self):
        super().setUp()
        self.Service = self.env['social_notifications.digest_service']
        self.alice, self.alice_p = _make_user(
            self.env, 'send_alice', login_date=fields.Datetime.now() - timedelta(days=10),
        )
        self.bob, _ = _make_user(self.env, 'send_bob')
        _make_unread(self.env, self.alice, self.bob)

    def test_send_stamps_last_digest_sent(self):
        before = self.alice.last_notification_digest_sent
        summary = self.Service._summary_for_user(self.alice)
        self.Service._send_digest(self.alice, summary)
        self.alice.invalidate_recordset()
        self.assertNotEqual(before, self.alice.last_notification_digest_sent)
        self.assertTrue(self.alice.last_notification_digest_sent)

    def test_unsubscribe_endpoint_disables_digest(self):
        token = self.Service._unsubscribe_token(self.alice.id)
        resp = self.url_open(f'/notifications/digest/unsubscribe/{self.alice.id}/{token}')
        self.assertEqual(resp.status_code, 200)
        self.alice_p.invalidate_recordset()
        self.assertFalse(self.alice_p.digest_email_enabled)
        self.assertIn('Reminders disabled', resp.text)

    def test_unsubscribe_endpoint_rejects_bad_token(self):
        resp = self.url_open(f'/notifications/digest/unsubscribe/{self.alice.id}/bogus')
        self.assertEqual(resp.status_code, 200)
        # Page rendered but state unchanged
        self.assertIn('isn\'t valid', resp.text)
        self.alice_p.invalidate_recordset()
        self.assertTrue(self.alice_p.digest_email_enabled)

    def test_cron_sends_and_skips_after_throttle(self):
        n1 = self.Service.cron_send_reactivation_digests()
        self.assertEqual(n1, 1)
        # Same run again immediately — throttle window prevents resend.
        n2 = self.Service.cron_send_reactivation_digests()
        self.assertEqual(n2 or 0, 0)
