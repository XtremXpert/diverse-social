from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install', 'social_help')
class TestCommunityHelp(HttpCase):

    def setUp(self):
        super().setUp()
        self.Param = self.env['ir.config_parameter'].sudo()

    def test_route_is_public(self):
        response = self.url_open('/community/help')
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('How do I post?', body)
        self.assertIn('How do I report a problematic post?', body)
        self.assertIn('Community charter', body)

    def test_default_charter_placeholder_renders_when_unset(self):
        self.Param.set_str('social_help.charter_html', '')
        response = self.url_open('/community/help')
        self.assertEqual(response.status_code, 200)
        self.assertIn('No community charter has been configured', response.text)

    def test_charter_override_is_rendered_as_html(self):
        self.Param.set_str(
            'social_help.charter_html',
            '<p class="custom-charter">Welcome neighbours.</p>',
        )
        response = self.url_open('/community/help')
        self.assertEqual(response.status_code, 200)
        self.assertIn('class="custom-charter"', response.text)
        self.assertIn('Welcome neighbours.', response.text)

    def test_community_name_appears_in_heading(self):
        self.Param.set_str('social_help.community_name', 'TestCommunity-XYZ')
        response = self.url_open('/community/help')
        self.assertIn('TestCommunity-XYZ', response.text)
