from odoo.tests import common, tagged


@tagged('club_base')
class TestClubBasePartnerDisplayName(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.internal_user = cls.env['res.users'].create({
            'name': 'Interne Dupont',
            'login': 'interne@test.com',
            'email': 'interne@test.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        portal_group = cls.env.ref('base.group_portal')
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Portal Tremblay',
            'login': 'portail_login@test.com',
            'email': 'portail@test.com',
            'groups_id': [(6, 0, [portal_group.id])],
        })

    def test_internal_user_display_name_is_name(self):
        partner = self.internal_user.partner_id
        partner.invalidate_recordset(['display_name'])
        self.assertEqual(partner.display_name, self.internal_user.name)

    def test_portal_user_display_name_is_login(self):
        partner = self.portal_user.partner_id
        partner.invalidate_recordset(['display_name'])
        self.assertEqual(partner.display_name, self.portal_user.login)

    def test_portal_display_name_not_email(self):
        partner = self.portal_user.partner_id
        partner.invalidate_recordset(['display_name'])
        self.assertNotEqual(partner.display_name, self.portal_user.email)

    def test_partner_with_no_user_unaffected(self):
        partner = self.env['res.partner'].create({'name': 'Sans utilisateur'})
        self.assertEqual(partner.display_name, 'Sans utilisateur')

    def test_partner_with_internal_and_portal_user_uses_name(self):
        """Un partner avec un user interne ET un user portail → nom (pas le login portail)."""
        portal_group = self.env.ref('base.group_portal')
        internal_group = self.env.ref('base.group_user')
        partner = self.env['res.partner'].create({'name': 'Partagé Tremblay'})
        self.env['res.users'].create({
            'name': 'Partagé Tremblay',
            'login': 'partage_internal@test.com',
            'email': 'partage_internal@test.com',
            'partner_id': partner.id,
            'groups_id': [(6, 0, [internal_group.id])],
        })
        self.env['res.users'].create({
            'name': 'Partagé Tremblay',
            'login': 'partage_portal@test.com',
            'email': 'partage_portal@test.com',
            'partner_id': partner.id,
            'groups_id': [(6, 0, [portal_group.id])],
        })
        partner.invalidate_recordset(['display_name'])
        self.assertNotEqual(partner.display_name, 'partage_portal@test.com')
