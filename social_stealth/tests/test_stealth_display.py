from odoo.tests import HttpCase, TransactionCase, tagged


class StealthCommon:

    @classmethod
    def _make_member(cls, env, name, login, stealth=None):
        user = env['res.users'].create({
            'name': name,
            'login': login,
            'email': login,
            'password': 'Stealth1234!',
            'group_ids': [
                (4, env.ref('base.group_portal').id),
                (4, env.ref('social_base.group_social_user').id),
            ],
        })
        profile = env['club_social_profile.profile'].sudo() \
            .get_or_create_for_user(user)
        if stealth:
            profile.sudo().write({'stealth_name': stealth})
        profile.sudo().write({'visibility': 'members'})
        return user


@tagged('social_stealth', 'post_install', '-at_install')
class TestStealthDisplayName(TransactionCase, StealthCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bob = cls._make_member(
            cls.env, 'Bob Vrainom', 'bob_stealth@test.local',
            stealth='Renard Masqué')
        cls.alice = cls._make_member(
            cls.env, 'Alice Membre', 'alice_stealth@test.local')
        # Un modérateur est un utilisateur INTERNE (group_user est impliqué
        # par group_social_moderator — exclusif avec group_portal).
        cls.moderator = cls.env['res.users'].create({
            'name': 'Momo Modo',
            'login': 'modo_stealth@test.local',
            'email': 'modo_stealth@test.local',
            'group_ids': [
                (4, cls.env.ref('base.group_user').id),
                (4, cls.env.ref('social_base.group_social_moderator').id),
            ],
        })

    def _name(self, viewer, partner, **ctx):
        # .sudo() APRÈS with_user : dans la vraie vie, un membre portail lit
        # les partners d'autrui via des recordsets élevés par les contrôleurs
        # (il n'a pas d'ACL read directe). La logique stealth cle sur
        # env.user, qui survit au sudo — c'est précisément le contrat testé.
        partner = partner.with_user(viewer).sudo()
        if ctx:
            partner = partner.with_context(**ctx)
        return partner.display_name

    def test_member_sees_alias(self):
        self.assertEqual(
            self._name(self.alice, self.bob.partner_id), 'Renard Masqué')

    def test_member_without_alias_untouched(self):
        self.assertEqual(
            self._name(self.bob, self.alice.partner_id), 'Alice Membre')

    def test_self_sees_real_name(self):
        self.assertEqual(
            self._name(self.bob, self.bob.partner_id), 'Bob Vrainom')

    # Pour les spectateurs privilégiés, social_stealth S'EFFACE : la
    # plateforme décide (club_base, s'il est installé, affiche le LOGIN des
    # partners purement portail pour l'identification backoffice). Le
    # contrat de ce module est seulement : jamais le pseudonyme.
    def test_internal_sees_real_identity(self):
        admin = self.env.ref('base.user_admin')
        name = self._name(admin, self.bob.partner_id)
        self.assertIn(name, ('Bob Vrainom', 'bob_stealth@test.local'))
        self.assertNotEqual(name, 'Renard Masqué')

    def test_moderator_sees_real_identity(self):
        name = self._name(self.moderator, self.bob.partner_id)
        self.assertIn(name, ('Bob Vrainom', 'bob_stealth@test.local'))
        self.assertNotEqual(name, 'Renard Masqué')

    def test_public_sees_alias(self):
        public = self.env.ref('base.public_user')
        self.assertEqual(
            self._name(public, self.bob.partner_id), 'Renard Masqué')

    def test_context_forces_real_identity(self):
        name = self._name(self.alice, self.bob.partner_id,
                          stealth_display=False)
        self.assertIn(name, ('Bob Vrainom', 'bob_stealth@test.local'))
        self.assertNotEqual(name, 'Renard Masqué')

    def test_context_forces_alias_for_internal(self):
        admin = self.env.ref('base.user_admin')
        self.assertEqual(
            self._name(admin, self.bob.partner_id, stealth_display=True),
            'Renard Masqué')

    def test_partner_without_profile_untouched(self):
        org = self.env['res.partner'].create({'name': 'Organisme Local'})
        self.assertEqual(
            self._name(self.alice, org), 'Organisme Local')

    def test_batch_mixed_recordset(self):
        """Un batch mêlant aliasés / non-aliasés / sans profil."""
        org = self.env['res.partner'].create({'name': 'Ferme du Rang'})
        batch = (self.bob.partner_id | self.alice.partner_id | org) \
            .with_user(self.alice)
        names = {p.id: p.display_name for p in batch}
        self.assertEqual(names[self.bob.partner_id.id], 'Renard Masqué')
        self.assertEqual(names[self.alice.partner_id.id], 'Alice Membre')
        self.assertEqual(names[org.id], 'Ferme du Rang')

    def test_user_display_name_stealth(self):
        """res.users est intercepté aussi (compute propre, non délégué)."""
        self.assertEqual(
            self.bob.with_user(self.alice).sudo().display_name,
            'Renard Masqué')
        admin = self.env.ref('base.user_admin')
        self.assertEqual(
            self.bob.with_user(admin).display_name, 'Bob Vrainom')


@tagged('social_stealth', 'post_install', '-at_install')
class TestStealthContract(HttpCase, StealthCommon):
    """Test de CONTRAT : le vrai nom et le courriel d'un membre pseudonymisé
    ne doivent apparaître sur aucune page portail rendue à un autre membre.

    Balaie les routes des modules installés dans l'environnement de test
    (une route absente → skip silencieux). Toute nouvelle fuite de
    ``partner.name`` / ``user.name`` casse ce test au lieu d'attendre un
    audit manuel.
    """

    ROUTES = [
        '/discover',
        '/members',
        '/groups',
        '/governance',
        '/social/feed',
        '/directory',
        '/search?q=Renard',
    ]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bob = cls._make_member(
            cls.env, 'Bob Vrainom', 'bob_contract@test.local',
            stealth='Renard Masqué')
        cls.alice = cls._make_member(
            cls.env, 'Alice Membre', 'alice_contract@test.local')

    def test_no_real_name_leak_on_portal_pages(self):
        self.authenticate('alice_contract@test.local', 'Stealth1234!')
        swept = 0
        for route in self.ROUTES:
            resp = self.url_open(route)
            if resp.status_code != 200:
                continue
            swept += 1
            self.assertNotIn(
                b'Bob Vrainom', resp.content,
                'FUITE du vrai nom sur %s' % route)
            self.assertNotIn(
                b'bob_contract@', resp.content,
                'FUITE du courriel sur %s' % route)
        self.assertGreater(swept, 0, 'aucune route balayée — deps de test ?')

    def test_alias_shown_on_discover(self):
        self.authenticate('alice_contract@test.local', 'Stealth1234!')
        resp = self.url_open('/discover')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Renard Masqué'.encode(), resp.content)
