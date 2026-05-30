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
        })
        cls.env.ref('base.group_user').user_ids |= cls.internal_user
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Portal Tremblay',
            'login': 'portail_login@test.com',
            'email': 'portail@test.com',
        })
        cls.env.ref('base.group_user').user_ids -= cls.portal_user
        cls.env.ref('base.group_portal').user_ids |= cls.portal_user

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
        u_internal = self.env['res.users'].create({
            'name': 'Partagé Tremblay',
            'login': 'partage_internal@test.com',
            'email': 'partage_internal@test.com',
            'partner_id': partner.id,
        })
        internal_group.user_ids |= u_internal
        u_portal = self.env['res.users'].create({
            'name': 'Partagé Tremblay',
            'login': 'partage_portal@test.com',
            'email': 'partage_portal@test.com',
            'partner_id': partner.id,
        })
        internal_group.user_ids -= u_portal
        portal_group.user_ids |= u_portal
        partner.invalidate_recordset(['display_name'])
        self.assertNotEqual(partner.display_name, 'partage_portal@test.com')

    def test_portal_display_name_is_login_not_name(self):
        """Le login diffère du nom — vérifier que c'est bien le login affiché."""
        partner = self.portal_user.partner_id
        partner.invalidate_recordset(['display_name'])
        self.assertEqual(partner.display_name, 'portail_login@test.com')
        self.assertNotEqual(partner.display_name, 'Portal Tremblay')

    def test_inactive_portal_user_not_used(self):
        """Un utilisateur portail inactif ne déclenche pas le remplacement."""
        partner = self.env['res.partner'].create({'name': 'Portail Inactif'})
        u = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': 'Portail Inactif', 'login': 'portail_inactif@test.com',
            'email': 'portail_inactif@test.com', 'partner_id': partner.id,
            'active': False,
        })
        partner.invalidate_recordset(['display_name'])
        self.assertEqual(partner.display_name, 'Portail Inactif')

    def test_multiple_portal_users_uses_first_login(self):
        """Deux utilisateurs portail actifs → display_name = login du premier."""
        partner = self.env['res.partner'].create({'name': 'Multi Portail'})
        portal_group = self.env.ref('base.group_portal')
        internal_group = self.env.ref('base.group_user')
        for login in ('multi_p1@test.com', 'multi_p2@test.com'):
            u = self.env['res.users'].create({
                'name': 'Multi Portail', 'login': login,
                'email': login, 'partner_id': partner.id,
            })
            internal_group.user_ids -= u
            portal_group.user_ids |= u
        partner.invalidate_recordset(['display_name'])
        self.assertIn(partner.display_name, {'multi_p1@test.com', 'multi_p2@test.com'})

    def test_batch_compute_mixed_partners(self):
        """Batch avec partenaires portail et sans utilisateur — résultats corrects."""
        plain = self.env['res.partner'].create({'name': 'Plain Partner'})
        portal_partner = self.portal_user.partner_id
        (plain | portal_partner).invalidate_recordset(['display_name'])
        self.assertEqual(plain.display_name, 'Plain Partner')
        self.assertEqual(portal_partner.display_name, self.portal_user.login)

    def test_inactive_internal_and_active_portal_shows_login(self):
        """Interne inactif + portail actif → le filtre retire l'interne → login portail affiché."""
        partner = self.env['res.partner'].create({'name': 'Interne Inactif'})
        portal_group = self.env.ref('base.group_portal')
        internal_group = self.env.ref('base.group_user')
        u_internal = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
            'name': 'Interne Inactif', 'login': 'interne_inactif2@test.com',
            'email': 'interne_inactif2@test.com', 'partner_id': partner.id,
            'active': False,
        })
        u_portal = self.env['res.users'].create({
            'name': 'Interne Inactif', 'login': 'portail_actif2@test.com',
            'email': 'portail_actif2@test.com', 'partner_id': partner.id,
        })
        internal_group.user_ids -= u_portal
        portal_group.user_ids |= u_portal
        partner.invalidate_recordset(['display_name'])
        self.assertEqual(partner.display_name, 'portail_actif2@test.com')

    def test_portal_user_deactivated_reverts_to_name(self):
        """Après désactivation du portail, display_name revient au nom du partenaire."""
        partner = self.env['res.partner'].create({'name': 'Portail Désactivé'})
        portal_group = self.env.ref('base.group_portal')
        internal_group = self.env.ref('base.group_user')
        u = self.env['res.users'].create({
            'name': 'Portail Désactivé', 'login': 'portail_desactive@test.com',
            'email': 'portail_desactive@test.com', 'partner_id': partner.id,
        })
        internal_group.user_ids -= u
        portal_group.user_ids |= u
        partner.invalidate_recordset(['display_name'])
        self.assertEqual(partner.display_name, 'portail_desactive@test.com')
        # Désactivation
        u.sudo().write({'active': False})
        partner.invalidate_recordset(['display_name'])
        self.assertEqual(partner.display_name, 'Portail Désactivé')
