from odoo.tests import HttpCase, tagged
from odoo.http import Request


@tagged('post_install', '-at_install')
class TestQuickExit(HttpCase):
    """Quand le module est installé, le bouton et sa doc sont présents."""

    def test_quick_exit_button_on_portal(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'social_quick_exit', resp.content)

    def test_safety_page_documents_quick_exit(self):
        self.authenticate('admin', 'admin')
        _csrf = Request.csrf_token(self)
        resp = self.url_open('/safety')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Quick exit', resp.content)
        self.assertIn('Esc'.encode(), resp.content)
