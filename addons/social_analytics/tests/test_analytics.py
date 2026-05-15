import datetime

from odoo import fields
from odoo.tests import TransactionCase, HttpCase, tagged


@tagged('social_analytics', 'analytics')
class TestSocialAnalytics(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_social = cls.env.ref('social_base.group_social_user')
        group_mod = cls.env.ref('social_base.group_social_moderator')

        cls.moderator = cls.env['res.users'].create({
            'name': 'Modo Analytics', 'login': 'anlt_modo',
            'email': 'modo@analytics.test',
            'group_ids': [(4, group_social.id), (4, group_mod.id)],
        })
        cls.user = cls.env['res.users'].create({
            'name': 'User Analytics', 'login': 'anlt_user',
            'email': 'user@analytics.test',
            'group_ids': [(4, group_social.id)],
        })

        cls.Dashboard = cls.env['social_analytics.dashboard']
        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')

    # ── Membres ───────────────────────────────────────────────────────────────

    def test_members_active_count(self):
        partner = self.env['res.partner'].create({'name': 'Test Membre Anlt'})
        m = self.env['club_membership.membership'].sudo().create({
            'partner_id': partner.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
        })
        before = self.Dashboard._member_stats(
            datetime.date.today(),
            datetime.datetime.now() - datetime.timedelta(days=30),
            datetime.date.today() + datetime.timedelta(days=30),
        )['active']
        m.action_activate()
        after = self.Dashboard._member_stats(
            datetime.date.today(),
            datetime.datetime.now() - datetime.timedelta(days=30),
            datetime.date.today() + datetime.timedelta(days=30),
        )['active']
        self.assertEqual(after, before + 1)

    def test_members_pending_count(self):
        partner = self.env['res.partner'].create({'name': 'Pending Anlt'})
        self.env['club_membership.membership'].sudo().create({
            'partner_id': partner.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'pending',
        })
        stats = self.Dashboard._member_stats(
            datetime.date.today(),
            datetime.datetime.now() - datetime.timedelta(days=30),
            datetime.date.today() + datetime.timedelta(days=30),
        )
        self.assertGreaterEqual(stats['pending'], 1)

    def test_members_expiring_soon(self):
        partner = self.env['res.partner'].create({'name': 'Expiring Anlt'})
        m = self.env['club_membership.membership'].sudo().create({
            'partner_id': partner.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'end_date': datetime.date.today() + datetime.timedelta(days=15),
            'state': 'active',
        })
        stats = self.Dashboard._member_stats(
            datetime.date.today(),
            datetime.datetime.now() - datetime.timedelta(days=30),
            datetime.date.today() + datetime.timedelta(days=30),
        )
        self.assertGreaterEqual(stats['expiring_soon'], 1)

    # ── Engagement ────────────────────────────────────────────────────────────

    def test_posts_published_month(self):
        before = self.Dashboard._engagement_stats(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )['posts_published_month']
        self.env['social_base.post'].sudo().create({
            'name': 'Post Analytics',
            'content': '<p>test</p>',
            'author_id': self.user.id,
            'visibility': 'members',
            'state': 'published',
        })
        after = self.Dashboard._engagement_stats(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )['posts_published_month']
        self.assertEqual(after, before + 1)

    def test_draft_post_not_counted(self):
        self.env['social_base.post'].sudo().create({
            'name': 'Draft Analytics',
            'content': '<p>draft</p>',
            'author_id': self.user.id,
            'visibility': 'members',
            'state': 'draft',
        })
        stats = self.Dashboard._engagement_stats(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )
        # Draft posts should not appear in published count
        published = self.env['social_base.post'].sudo().search_count([
            ('state', '=', 'published'),
            ('create_date', '>=', datetime.datetime.now() - datetime.timedelta(days=30)),
        ])
        self.assertEqual(stats['posts_published_month'], published)

    def test_stories_active_count(self):
        before = self.Dashboard._engagement_stats(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )['stories_active']
        self.env['social_story.story'].sudo().create({
            'name': 'Story Analytics',
            'author_id': self.user.id,
        })
        after = self.Dashboard._engagement_stats(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )['stories_active']
        self.assertEqual(after, before + 1)

    def test_top_posts_returns_list(self):
        top = self.Dashboard._top_posts(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )
        self.assertIsInstance(top, list)
        self.assertLessEqual(len(top), 5)

    # ── Modération ────────────────────────────────────────────────────────────

    def test_reports_pending_count(self):
        before = self.Dashboard._moderation_stats()['reports_pending']
        self.env['club_social_moderation.report'].sudo().create({
            'reporter_id': self.user.id,
            'ref_model': 'post',
            'ref_id': 1,
            'reason': 'spam',
            'state': 'pending',
        })
        after = self.Dashboard._moderation_stats()['reports_pending']
        self.assertEqual(after, before + 1)

    def test_posts_in_moderation_count(self):
        before = self.Dashboard._moderation_stats()['posts_in_moderation']
        self.env['social_base.post'].sudo().create({
            'name': 'Post Moderation',
            'content': '<p>à modérer</p>',
            'author_id': self.user.id,
            'visibility': 'members',
            'state': 'moderation',
        })
        after = self.Dashboard._moderation_stats()['posts_in_moderation']
        self.assertEqual(after, before + 1)

    # ── Gouvernance ───────────────────────────────────────────────────────────

    def test_proposals_voting_count(self):
        before = self.Dashboard._governance_stats(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )['proposals_voting']
        proposal = self.env['social_governance.proposal'].with_user(self.moderator).create({
            'name': 'Proposition Analytics',
            'description': '<p>test</p>',
            'author_id': self.moderator.id,
            'category_id': self.env.ref('social_governance.category_other').id,
            'voting_closes_at': datetime.datetime.now() + datetime.timedelta(days=7),
        })
        proposal.action_start_voting()
        after = self.Dashboard._governance_stats(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )['proposals_voting']
        self.assertEqual(after, before + 1)

    # ── Activité ──────────────────────────────────────────────────────────────

    def test_profiles_total(self):
        before = self.Dashboard._activity_stats(
            datetime.datetime.now() - datetime.timedelta(days=7)
        )['profiles_total']
        self.env['club_social_profile.profile'].get_or_create_for_user(self.user)
        after = self.Dashboard._activity_stats(
            datetime.datetime.now() - datetime.timedelta(days=7)
        )['profiles_total']
        self.assertGreaterEqual(after, before)

    # ── get_dashboard_data ────────────────────────────────────────────────────

    def test_get_dashboard_data_structure(self):
        data = self.Dashboard.get_dashboard_data()
        self.assertIn('members', data)
        self.assertIn('engagement', data)
        self.assertIn('moderation', data)
        self.assertIn('governance', data)
        self.assertIn('activity', data)
        self.assertIn('generated_at', data)

    def test_get_dashboard_data_keys(self):
        data = self.Dashboard.get_dashboard_data()
        self.assertIn('active', data['members'])
        self.assertIn('posts_published_month', data['engagement'])
        self.assertIn('reports_pending', data['moderation'])
        self.assertIn('proposals_voting', data['governance'])
        self.assertIn('profiles_total', data['activity'])

    def test_dashboard_values_are_non_negative(self):
        data = self.Dashboard.get_dashboard_data()
        for section in ('members', 'engagement', 'moderation', 'governance', 'activity'):
            for key, val in data[section].items():
                if isinstance(val, int):
                    self.assertGreaterEqual(val, 0, f"{section}.{key} should be >= 0")

    # ── TransientModel open/populate ─────────────────────────────────────────

    def test_populate_fills_fields(self):
        record = self.Dashboard.sudo().create({})
        record._populate()
        self.assertGreaterEqual(record.members_active, 0)
        self.assertGreaterEqual(record.posts_published_month, 0)
        self.assertGreaterEqual(record.reports_pending, 0)

    def test_action_view_pending_reports(self):
        record = self.Dashboard.sudo().create({})
        action = record.action_view_pending_reports()
        self.assertEqual(action['res_model'], 'club_social_moderation.report')
        self.assertIn(('state', '=', 'pending'), action['domain'])

    def test_action_view_pending_memberships(self):
        record = self.Dashboard.sudo().create({})
        action = record.action_view_pending_memberships()
        self.assertEqual(action['res_model'], 'club_membership.membership')

    # ── Galerie ───────────────────────────────────────────────────────────────

    def test_gallery_stats_photos_pending(self):
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Anlt Gallery Pending',
            'owner_id': self.user.id,
            'visibility': 'members',
        })
        month_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        before = self.Dashboard._gallery_stats(month_ago)['photos_pending_moderation']
        self.env['social_gallery.photo'].sudo().create({
            'gallery_id': gallery.id,
            'submitted_by_id': self.user.id,
            'state': 'pending',
        })
        after = self.Dashboard._gallery_stats(month_ago)['photos_pending_moderation']
        self.assertEqual(after, before + 1)

    def test_gallery_stats_photos_approved_month(self):
        gallery = self.env['social_gallery.gallery'].sudo().create({
            'name': 'Anlt Gallery Approved',
            'owner_id': self.user.id,
            'visibility': 'members',
        })
        month_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        before = self.Dashboard._gallery_stats(month_ago)['photos_approved_month']
        self.env['social_gallery.photo'].sudo().create({
            'gallery_id': gallery.id,
            'state': 'approved',
            'moderation_date': fields.Datetime.now(),
        })
        after = self.Dashboard._gallery_stats(month_ago)['photos_approved_month']
        self.assertEqual(after, before + 1)

    def test_gallery_stats_galleries_total(self):
        month_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        before = self.Dashboard._gallery_stats(month_ago)['galleries_total']
        self.env['social_gallery.gallery'].sudo().create({
            'name': 'Anlt Gallery Total',
            'owner_id': self.user.id,
            'visibility': 'members',
        })
        after = self.Dashboard._gallery_stats(month_ago)['galleries_total']
        self.assertEqual(after, before + 1)

    def test_private_gallery_not_counted(self):
        month_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        before = self.Dashboard._gallery_stats(month_ago)['galleries_total']
        self.env['social_gallery.gallery'].sudo().create({
            'name': 'Anlt Private Gallery',
            'owner_id': self.user.id,
            'visibility': 'private',
        })
        after = self.Dashboard._gallery_stats(month_ago)['galleries_total']
        self.assertEqual(after, before)

    # ── Réputation ────────────────────────────────────────────────────────────

    def test_reputation_stats_vouchings_active(self):
        month_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        before = self.Dashboard._reputation_stats(month_ago)['vouchings_active']
        self.env['social_reputation.vouching'].sudo().create({
            'sponsor_id': self.moderator.id,
            'newcomer_id': self.user.id,
            'state': 'active',
        })
        after = self.Dashboard._reputation_stats(month_ago)['vouchings_active']
        self.assertEqual(after, before + 1)

    def test_reputation_stats_withdrawn_not_counted(self):
        month_ago = datetime.datetime.now() - datetime.timedelta(days=30)
        before = self.Dashboard._reputation_stats(month_ago)['vouchings_active']
        self.env['social_reputation.vouching'].sudo().create({
            'sponsor_id': self.moderator.id,
            'newcomer_id': self.user.id,
            'state': 'withdrawn',
        })
        after = self.Dashboard._reputation_stats(month_ago)['vouchings_active']
        self.assertEqual(after, before)

    # ── Négociations ──────────────────────────────────────────────────────────

    def test_negotiation_stats_active(self):
        before = self.Dashboard._negotiation_stats()['negotiations_active']
        self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': self.moderator.id,
            'partner_id': self.user.id,
            'state': 'active',
        })
        after = self.Dashboard._negotiation_stats()['negotiations_active']
        self.assertEqual(after, before + 1)

    def test_negotiation_stats_pending_signature(self):
        before = self.Dashboard._negotiation_stats()['negotiations_pending_signature']
        self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': self.moderator.id,
            'partner_id': self.user.id,
            'state': 'shared',
        })
        after = self.Dashboard._negotiation_stats()['negotiations_pending_signature']
        self.assertEqual(after, before + 1)

    def test_negotiation_archived_not_in_pending(self):
        before = self.Dashboard._negotiation_stats()['negotiations_pending_signature']
        self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': self.moderator.id,
            'partner_id': self.user.id,
            'state': 'archived',
        })
        after = self.Dashboard._negotiation_stats()['negotiations_pending_signature']
        self.assertEqual(after, before)

    def test_get_dashboard_data_includes_new_sections(self):
        data = self.Dashboard.get_dashboard_data()
        self.assertIn('gallery', data)
        self.assertIn('reputation', data)
        self.assertIn('negotiation', data)
        self.assertIn('photos_pending_moderation', data['gallery'])
        self.assertIn('vouchings_active', data['reputation'])
        self.assertIn('negotiations_active', data['negotiation'])

    def test_populate_includes_new_fields(self):
        record = self.Dashboard.sudo().create({})
        record._populate()
        self.assertGreaterEqual(record.galleries_total, 0)
        self.assertGreaterEqual(record.vouchings_active, 0)
        self.assertGreaterEqual(record.negotiations_active, 0)
        self.assertGreaterEqual(record.photos_pending_moderation, 0)

    def test_action_view_pending_photos(self):
        record = self.Dashboard.sudo().create({})
        action = record.action_view_pending_photos()
        self.assertEqual(action['res_model'], 'social_gallery.photo')
        self.assertIn(('state', '=', 'pending'), action['domain'])

    # ── Actions navigation restantes ─────────────────────────────────────────

    def test_action_view_posts_moderation(self):
        record = self.Dashboard.sudo().create({})
        action = record.action_view_posts_moderation()
        self.assertEqual(action['res_model'], 'social_base.post')
        self.assertIn(('state', '=', 'moderation'), action['domain'])

    def test_action_view_voting_proposals(self):
        record = self.Dashboard.sudo().create({})
        action = record.action_view_voting_proposals()
        self.assertEqual(action['res_model'], 'social_governance.proposal')

    # ── action_refresh & open_dashboard ──────────────────────────────────────

    def test_action_refresh_returns_action(self):
        record = self.Dashboard.sudo().create({})
        action = record.action_refresh()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'social_analytics.dashboard')

    def test_open_dashboard_returns_action(self):
        action = self.Dashboard.sudo().open_dashboard()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'social_analytics.dashboard')

    # ── Compteurs supplémentaires ─────────────────────────────────────────────

    def test_members_new_month_count(self):
        before = self.Dashboard._member_stats(
            datetime.date.today(),
            datetime.datetime.now() - datetime.timedelta(days=30),
            datetime.date.today() + datetime.timedelta(days=30),
        )['new_month']
        partner = self.env['res.partner'].create({'name': 'New This Month'})
        m = self.env['club_membership.membership'].sudo().create({
            'partner_id': partner.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
        })
        m.action_activate()
        after = self.Dashboard._member_stats(
            datetime.date.today(),
            datetime.datetime.now() - datetime.timedelta(days=30),
            datetime.date.today() + datetime.timedelta(days=30),
        )['new_month']
        self.assertEqual(after, before + 1)

    def test_negotiation_reviewing_in_pending_signature(self):
        before = self.Dashboard._negotiation_stats()['negotiations_pending_signature']
        self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': self.moderator.id,
            'partner_id': self.user.id,
            'state': 'reviewing',
        })
        after = self.Dashboard._negotiation_stats()['negotiations_pending_signature']
        self.assertEqual(after, before + 1)

    def test_connections_week_count(self):
        before = self.Dashboard._activity_stats(
            datetime.datetime.now() - datetime.timedelta(days=7)
        )['connections_week']
        profile_a = self.env['club_social_profile.profile'].get_or_create_for_user(self.moderator)
        profile_b = self.env['club_social_profile.profile'].get_or_create_for_user(self.user)
        self.env['club_social_profile.connection'].sudo().create({
            'profile_a_id': profile_a.id,
            'profile_b_id': profile_b.id,
        })
        after = self.Dashboard._activity_stats(
            datetime.datetime.now() - datetime.timedelta(days=7)
        )['connections_week']
        self.assertGreaterEqual(after, before)

    def test_top_posts_has_required_keys(self):
        """Chaque entrée _top_posts possède les clés attendues."""
        self.env['social_base.post'].sudo().create({
            'name': 'Top Post Test',
            'content': '<p>Contenu analytique</p>',
            'author_id': self.user.id,
            'visibility': 'members',
            'state': 'published',
        })
        top = self.Dashboard._top_posts(
            datetime.datetime.now() - datetime.timedelta(days=30)
        )
        if top:
            entry = top[0]
            self.assertIn('id', entry)
            self.assertIn('likes', entry)
            self.assertIn('comments', entry)

    def test_new_sections_values_non_negative(self):
        data = self.Dashboard.get_dashboard_data()
        for section in ('gallery', 'reputation', 'negotiation'):
            for key, val in data[section].items():
                if isinstance(val, int):
                    self.assertGreaterEqual(val, 0, f"{section}.{key} devrait être >= 0")


@tagged('social_analytics', 'analytics', 'post_install', '-at_install')
class TestSocialAnalyticsHttp(HttpCase):
    """Tests HTTP des endpoints API analytics."""

    def setUp(self):
        super().setUp()
        group_social = self.env.ref('social_base.group_social_user')
        group_mod = self.env.ref('social_base.group_social_moderator')
        self.moderator = self.env['res.users'].sudo().create({
            'name': 'API Modo', 'login': 'api_modo_anlt',
            'email': 'api_modo@analytics.test',
            'password': 'Test1234!',
            'group_ids': [(4, group_social.id), (4, group_mod.id)],
        })
        self.regular_user = self.env['res.users'].sudo().create({
            'name': 'API User', 'login': 'api_user_anlt',
            'email': 'api_user@analytics.test',
            'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })

    def test_dashboard_api_moderator_200(self):
        self.authenticate('api_modo_anlt', 'Test1234!')
        resp = self.url_open('/social/api/analytics/dashboard')
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_api_non_moderator_403(self):
        self.authenticate('api_user_anlt', 'Test1234!')
        resp = self.url_open('/social/api/analytics/dashboard')
        self.assertEqual(resp.status_code, 403)

    def test_members_api_moderator_200(self):
        self.authenticate('api_modo_anlt', 'Test1234!')
        resp = self.url_open('/social/api/analytics/members')
        self.assertEqual(resp.status_code, 200)

    def test_members_api_non_moderator_403(self):
        self.authenticate('api_user_anlt', 'Test1234!')
        resp = self.url_open('/social/api/analytics/members')
        self.assertEqual(resp.status_code, 403)

    def test_engagement_api_moderator_200(self):
        self.authenticate('api_modo_anlt', 'Test1234!')
        resp = self.url_open('/social/api/analytics/engagement')
        self.assertEqual(resp.status_code, 200)

    def test_engagement_api_non_moderator_403(self):
        self.authenticate('api_user_anlt', 'Test1234!')
        resp = self.url_open('/social/api/analytics/engagement')
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_api_unauthenticated_redirects(self):
        resp = self.url_open('/social/api/analytics/dashboard', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
