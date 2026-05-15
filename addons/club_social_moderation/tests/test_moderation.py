from datetime import timedelta
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


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
            'group_ids': [(4, self.env.ref('social_base.group_social_user').id)],
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
        report.sudo().action_resolve(note='Content removed')
        self.assertEqual(report.state, 'resolved')
        self.assertTrue(report.resolved_at)
        self.assertEqual(report.resolution_note, 'Content removed')

    def test_dismiss_report(self):
        report = self._make_report(ref_id=4)
        report.sudo().action_dismiss(note='No violation found')
        self.assertEqual(report.state, 'dismissed')
        self.assertEqual(report.resolution_note, 'No violation found')

    def test_resolve_sets_resolved_by(self):
        report = self._make_report(ref_id=5)
        report.sudo().action_resolve(note='Supprimé')
        self.assertTrue(report.resolved_by)

    def test_dismiss_sets_resolved_by(self):
        report = self._make_report(ref_id=6)
        report.sudo().action_dismiss()
        self.assertTrue(report.resolved_by)

    def test_report_all_reasons(self):
        """Chaque valeur de reason est acceptée."""
        reasons = ['spam', 'harcelement', 'contenu_inapproprie', 'mineurs', 'autre']
        for i, reason in enumerate(reasons, start=10):
            r = self.Report.with_user(self.reporter).create({
                'ref_model': 'social_base.post',
                'ref_id': i,
                'reason': reason,
            })
            self.assertEqual(r.reason, reason)

    def test_report_all_ref_models(self):
        """Chaque valeur de ref_model est acceptée."""
        models = ['social_base.post', 'social_base.comment', 'club_social_profile.profile']
        for i, ref_model in enumerate(models, start=20):
            r = self.Report.with_user(self.reporter).create({
                'ref_model': ref_model,
                'ref_id': i,
                'reason': 'spam',
            })
            self.assertEqual(r.ref_model, ref_model)

    def test_duplicate_different_model_allowed(self):
        """Même ref_id mais modèle différent → deux rapports distincts autorisés."""
        self.Report.with_user(self.reporter).create({
            'ref_model': 'social_base.post',
            'ref_id': 30,
            'reason': 'spam',
        })
        r2 = self.Report.with_user(self.reporter).create({
            'ref_model': 'social_base.comment',
            'ref_id': 30,
            'reason': 'spam',
        })
        self.assertEqual(r2.state, 'pending')

    def test_report_with_description(self):
        report = self.Report.with_user(self.reporter).create({
            'ref_model': 'social_base.post',
            'ref_id': 40,
            'reason': 'autre',
            'description': 'Détails supplémentaires',
        })
        self.assertEqual(report.description, 'Détails supplémentaires')


class TestBanExtra(TransactionCase):
    """Tests supplémentaires sur les bans."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        partner = cls.env['res.partner'].create({'name': 'Extra Member'})
        user = cls.env['res.users'].create({
            'name': 'Extra Member', 'login': 'extra_member_mod', 'partner_id': partner.id,
        })
        cls.profile = cls.env['club_social_profile.profile'].create({'user_id': user.id})

    def test_action_ban_creates_ban_record(self):
        self.profile.action_ban(reason='Raison test')
        self.assertTrue(self.profile.ban_ids)

    def test_action_ban_sets_banned_by(self):
        self.profile.action_ban(reason='Test banned_by')
        active = self.profile.ban_ids.filtered('is_active')
        self.assertTrue(active.banned_by)

    def test_multiple_bans_only_active_counts(self):
        """Deux bans : le premier levé, le second actif → is_banned=True."""
        past = fields.Datetime.now() - timedelta(hours=2)
        self.env['club_social_moderation.ban'].create({
            'profile_id': self.profile.id,
            'reason': 'Premier ban',
            'banned_until': past,
        })
        self.profile.action_ban(reason='Deuxième ban actif')
        self.profile._compute_is_banned()
        self.assertTrue(self.profile.is_banned)

    def test_lift_sets_lifted_by(self):
        self.profile.action_ban(reason='À lever')
        active = self.profile.ban_ids.filtered('is_active')
        active.action_lift()
        self.assertTrue(active.lifted_by)
        self.assertTrue(active.lifted_at)

    def test_lift_ban_deactivates(self):
        self.profile.action_ban(reason='Lift test')
        active = self.profile.ban_ids.filtered('is_active')
        active.action_lift()
        active._compute_is_active()
        self.assertFalse(active.is_active)

    def test_cron_keeps_active_permanent_ban(self):
        """Le cron ne touche pas les bans permanents actifs."""
        self.profile.action_ban(reason='Permanent')
        self.env['club_social_moderation.ban'].cron_expire_bans()
        self.profile._compute_is_banned()
        self.assertTrue(self.profile.is_banned)

    def test_cron_keeps_future_ban(self):
        """Le cron ne touche pas les bans temporaires dont l'expiration est dans le futur."""
        future = fields.Datetime.now() + timedelta(days=1)
        self.profile.action_ban(reason='Futur', banned_until=future)
        self.env['club_social_moderation.ban'].cron_expire_bans()
        self.profile._compute_is_banned()
        self.assertTrue(self.profile.is_banned)

    def test_ban_reason_cleared_after_lift(self):
        self.profile.action_ban(reason='À effacer')
        active = self.profile.ban_ids.filtered('is_active')
        active.action_lift()
        self.profile._compute_is_banned()
        self.assertFalse(self.profile.ban_reason)

    def test_shadow_ban_independent_of_regular_ban(self):
        """Shadow ban et ban régulier sont indépendants."""
        self.profile.action_shadow_ban()
        self.assertTrue(self.profile.is_shadow_banned)
        self.assertFalse(self.profile.is_banned)
        self.profile.action_ban(reason='Double sanction')
        self.profile._compute_is_banned()
        self.assertTrue(self.profile.is_shadow_banned)
        self.assertTrue(self.profile.is_banned)
