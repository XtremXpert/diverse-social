from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.social_safety.utils import is_sensitive_path


@tagged('social_safety', 'share_lockdown')
class TestSensitivePath(TransactionCase):
    """Pure-function tests for the path classification helper."""

    def test_member_paths_are_sensitive(self):
        for p in [
            '/my', '/my/', '/my/dashboard', '/my/profile/edit',
            '/profile/42', '/safety', '/discover', '/members',
            '/members/map', '/groups', '/groups/3', '/governance',
            '/gallery', '/stories', '/onboarding', '/messaging',
            '/calls', '/circles', '/consent', '/negotiation',
            '/vouching', '/reputation',
        ]:
            self.assertTrue(is_sensitive_path(p), f'{p} should be sensitive')

    def test_public_paths_are_not_sensitive(self):
        for p in [
            '/', '/shop', '/event', '/blog', '/membership',
            '/web/login', '/signup', '/contactus', '/website/info',
            '/manifest.webmanifest', '/sw.js',
        ]:
            self.assertFalse(is_sensitive_path(p), f'{p} must stay shareable')

    def test_edge_cases(self):
        self.assertFalse(is_sensitive_path(''), 'empty path')
        self.assertFalse(is_sensitive_path(None), 'None path')
        # No false-positive on word-boundary lookalikes
        self.assertFalse(is_sensitive_path('/myth'), '/myth ≠ /my')
        self.assertFalse(is_sensitive_path('/safetymatters'), 'prefix-but-not-section')


@tagged('social_safety', 'share_lockdown', 'post_install', '-at_install')
class TestShareLockdownRendering(HttpCase):
    """Verify the noindex meta is injected where it should be — and only there."""

    def setUp(self):
        super().setUp()
        # /members and friends require group_social_user, so we sign up a
        # member to authenticate as.
        self.user = self.env['res.users'].create({
            'name': 'Lockdown User', 'login': 'lockdown_user',
            'email': 'lockdown_user@lockdown.test',
            'password': 'Test1234!',
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('social_base.group_social_user').id),
            ],
        })
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.user)

    def test_sensitive_path_has_noindex_meta(self):
        self.authenticate('lockdown_user', 'Test1234!')
        resp = self.url_open('/members')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(
            '<meta name="robots" content="noindex, nofollow, noarchive"',
            resp.text,
            'noindex meta missing on a sensitive path',
        )

    def test_public_path_has_no_noindex_meta(self):
        # /web/login is public + must remain indexable.
        resp = self.url_open('/web/login')
        self.assertNotIn(
            '<meta name="robots" content="noindex, nofollow, noarchive"',
            resp.text,
            'public page must not carry our lockdown meta',
        )

    def test_helper_via_qweb(self):
        """The QWeb-accessible helper returns the same answer as the util."""
        Helper = self.env['social_safety.helper']
        self.assertTrue(Helper.is_sensitive_path('/my/profile/edit'))
        self.assertFalse(Helper.is_sensitive_path('/shop'))

    def test_sensitive_path_has_x_robots_tag_header(self):
        """The HTTP response on a sensitive path carries X-Robots-Tag.

        This is the layer that catches Slack/Discord unfurlers, which
        ignore the meta robots tag in HTML but honour the header.
        """
        self.authenticate('lockdown_user', 'Test1234!')
        resp = self.url_open('/members')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers.get('X-Robots-Tag'),
            'noindex, nofollow, noarchive',
        )

    def test_public_path_has_no_x_robots_tag_header(self):
        resp = self.url_open('/web/login')
        # Header must be absent (or at least not ours) on a page that's
        # supposed to be indexable.
        tag = resp.headers.get('X-Robots-Tag', '')
        self.assertNotIn('noindex', tag)
