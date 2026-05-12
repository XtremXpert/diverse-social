from datetime import timedelta
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestBan(TransactionCase):

    def setUp(self):
        super().setUp()
        self.moderator = self.env.ref('base.user_admin')
        partner = self.env['res.partner'].create({'name': 'Test Member'})
        user = self.env['res.users'].create({
            'name': 'Test Member',
            'login': 'test_member_mod',
            'partner_id': partner.id,
        })
        self.profile = self.env['club_social_profile.profile'].create({
            'user_id': user.id,
            'display_name': 'TestMember',
        })

    def test_permanent_ban(self):
        self.profile.action_ban(reason='Test permanent ban')
        self.assertTrue(self.profile.is_banned)
        self.assertEqual(self.profile.ban_reason, 'Test permanent ban')

    def test_temporary_ban_active(self):
        future = fields.Datetime.now() + timedelta(hours=24)
        self.profile.action_ban(reason='Temp ban', banned_until=future)
        self.assertTrue(self.profile.is_banned)

    def test_temporary_ban_expired(self):
        past = fields.Datetime.now() - timedelta(hours=1)
        ban = self.env['club_social_moderation.ban'].create({
            'profile_id': self.profile.id,
            'reason': 'Expired ban',
            'banned_until': past,
        })
        ban._compute_is_active()
        self.profile._compute_is_banned()
        self.assertFalse(self.profile.is_banned)

    def test_lift_ban(self):
        self.profile.action_ban(reason='Will be lifted')
        self.assertTrue(self.profile.is_banned)
        active_ban = self.profile.ban_ids.filtered('is_active')
        active_ban.action_lift()
        self.profile._compute_is_banned()
        self.assertFalse(self.profile.is_banned)

    def test_shadow_ban(self):
        self.assertFalse(self.profile.is_shadow_banned)
        self.profile.action_shadow_ban()
        self.assertTrue(self.profile.is_shadow_banned)
        self.profile.action_lift_shadow_ban()
        self.assertFalse(self.profile.is_shadow_banned)

    def test_cron_expire_bans(self):
        past = fields.Datetime.now() - timedelta(minutes=1)
        self.env['club_social_moderation.ban'].create({
            'profile_id': self.profile.id,
            'reason': 'Expired',
            'banned_until': past,
            'is_active': True,
        })
        self.env['club_social_moderation.ban'].cron_expire_bans()
        self.profile._compute_is_banned()
        self.assertFalse(self.profile.is_banned)


class TestReport(TransactionCase):

    def setUp(self):
        super().setUp()
        partner = self.env['res.partner'].create({'name': 'Reporter'})
        self.reporter = self.env['res.users'].create({
            'name': 'Reporter',
            'login': 'reporter_mod_test',
            'partner_id': partner.id,
        })
        self.Report = self.env['club_social_moderation.report']

    def _make_report(self, ref_id=1):
        return self.Report.with_user(self.reporter).create({
            'ref_model': 'social_base.post',
            'ref_id': ref_id,
            'reason': 'spam',
        })

    def test_create_report(self):
        report = self._make_report(ref_id=1)
        self.assertEqual(report.state, 'pending')
        self.assertEqual(report.reporter_id, self.reporter)

    def test_duplicate_report_blocked(self):
        self._make_report(ref_id=2)
        with self.assertRaises(Exception):
            self._make_report(ref_id=2)

    def test_resolve_report(self):
        report = self._make_report(ref_id=3)
        report.action_resolve(note='Content removed')
        self.assertEqual(report.state, 'resolved')
        self.assertTrue(report.resolved_at)
        self.assertEqual(report.resolution_note, 'Content removed')

    def test_dismiss_report(self):
        report = self._make_report(ref_id=4)
        report.action_dismiss(note='No violation found')
        self.assertEqual(report.state, 'dismissed')
        self.assertEqual(report.resolution_note, 'No violation found')
