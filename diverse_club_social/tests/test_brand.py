from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.diverse_club_social import hooks


@tagged('post_install', '-at_install', 'diverse_club_social')
class TestBrand(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({
            'name': 'Destinataire logo', 'email': 'logo@diverse.test',
        })
        cls.record = cls.env['res.partner'].create({'name': 'Fil de test'})

    def _sent_body(self, subtype_xmlid):
        message = self.record.with_context(mail_notify_force_send=False).message_post(
            body='Test', partner_ids=self.partner.ids,
            message_type='comment', subtype_xmlid=subtype_xmlid,
            mail_auto_delete=False,
        )
        mail = self.env['mail.mail'].sudo().search([('mail_message_id', '=', message.id)])
        self.assertTrue(mail, "La notification doit produire un courriel")
        return str(mail.body_html)

    def test_apply_logo_sets_brand_images(self):
        hooks._apply_logo(self.env)
        company_logo = hooks._read_image_b64(*hooks._COMPANY_LOGO_REL_PATH)
        website_logo = hooks._read_image_b64(*hooks._WEBSITE_LOGO_REL_PATH)
        self.assertNotEqual(bytes(company_logo), bytes(website_logo))
        self.assertFalse(hooks._differs(self.company.logo, company_logo))
        self.assertFalse(hooks._differs(hooks._diverse_websites(self.env).logo, website_logo))

    def test_setup_leaves_other_websites_alone(self):
        main = hooks._diverse_websites(self.env)
        self.assertEqual(main, self.env.ref('base.default_website'))
        other = self.env['website'].create({'name': 'Skyline', 'domain': 'https://ww2.diverse.test'})
        menus = self.env['website.menu'].search([('website_id', '=', other.id)])
        self.assertTrue(menus, "Le site de test doit avoir ses propres menus")
        state = {m.id: (m.group_ids.ids, m.with_context(lang='fr_CA').name) for m in menus}
        langs = other.language_ids.ids
        logo = bytes(other.logo or b'')
        hooks._apply_diverse_setup(self.env)
        self.assertEqual(other.name, 'Skyline')
        self.assertEqual(bytes(other.logo or b''), logo)
        self.assertEqual(other.language_ids.ids, langs)
        self.assertEqual(
            {m.id: (m.group_ids.ids, m.with_context(lang='fr_CA').name) for m in menus}, state)
        self.assertEqual(main.name, 'Diverse-Cité')

    def test_apply_logo_is_idempotent(self):
        hooks._apply_logo(self.env)
        Company = type(self.env['res.company'])
        Website = type(self.env['website'])
        with patch.object(Company, 'write', autospec=True) as company_write, \
                patch.object(Website, 'write', autospec=True) as website_write:
            hooks._apply_logo(self.env)
        company_write.assert_not_called()
        website_write.assert_not_called()

    def test_notification_has_company_logo(self):
        hooks._apply_logo(self.env)
        self.assertFalse(self.company.uses_default_logo)
        logo_src = '/logo.png?company=%s' % self.company.id
        self.assertIn(logo_src, self._sent_body('mail.mt_note'))
        # Les messages de discussion n'ont pas d'en-tête Odoo : le logo y est quand même.
        self.assertIn(logo_src, self._sent_body('mail.mt_comment'))
