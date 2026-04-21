from odoo.tests import common, tagged


@tagged('post_install', '-at_install', 'website_blog_restricted')
class TestBlogRestricted(common.HttpCase):
    """Tests pour la restriction d'accès aux blogs par niveau de visibilité."""

    def setUp(self):
        super().setUp()

        self.blog_public = self.env['blog.blog'].create({
            'name': 'Blog Public',
            'visibility': 'public',
        })
        self.blog_members = self.env['blog.blog'].create({
            'name': 'Blog Membres',
            'visibility': 'members',
        })

        self.post_public = self.env['blog.post'].create({
            'name': 'Article public',
            'blog_id': self.blog_public.id,
            'website_published': True,
        })
        self.post_members = self.env['blog.post'].create({
            'name': 'Article membres',
            'blog_id': self.blog_members.id,
            'website_published': True,
        })

        # Utilisateur interne (membre du club = non-portal)
        self.user_member = self.env['res.users'].create({
            'name': 'Membre',
            'login': 'user_member',
            'password': 'user_member',
            'email': 'membre@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        # Utilisateur portal (non-membre)
        self.user_portal = self.env['res.users'].create({
            'name': 'Portal',
            'login': 'user_portal',
            'password': 'user_portal',
            'email': 'portal@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

        slug = self.env['ir.http']._slug
        self.url_public = '/blog/%s' % slug(self.blog_public)
        self.url_members = '/blog/%s' % slug(self.blog_members)
        self.url_post_public = '/blog/%s/%s' % (slug(self.blog_public), slug(self.post_public))
        self.url_post_members = '/blog/%s/%s' % (slug(self.blog_members), slug(self.post_members))

    # ── Blog public ────────────────────────────────────────────────────────

    def test_blog_public_anonyme(self):
        resp = self.url_open(self.url_public)
        self.assertEqual(resp.status_code, 200)

    def test_blog_public_portal(self):
        self.authenticate('user_portal', 'user_portal')
        resp = self.url_open(self.url_public)
        self.assertEqual(resp.status_code, 200)

    def test_post_public_anonyme(self):
        resp = self.url_open(self.url_post_public)
        self.assertEqual(resp.status_code, 200)

    # ── Blog membres — visiteur anonyme ───────────────────────────────────

    def test_blog_members_anonyme_redirige(self):
        resp = self.url_open(self.url_members, allow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/web/login', resp.headers.get('Location', ''))

    def test_post_members_anonyme_redirige(self):
        resp = self.url_open(self.url_post_members, allow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/web/login', resp.headers.get('Location', ''))

    # ── Blog membres — utilisateur portal (non-membre) ────────────────────

    def test_blog_members_portal_redirige(self):
        self.authenticate('user_portal', 'user_portal')
        resp = self.url_open(self.url_members, allow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/web/login', resp.headers.get('Location', ''))

    # ── Blog membres — utilisateur interne ───────────────────────────────

    def test_blog_members_interne_accessible(self):
        self.authenticate('user_member', 'user_member')
        resp = self.url_open(self.url_members)
        self.assertEqual(resp.status_code, 200)

    def test_post_members_interne_accessible(self):
        self.authenticate('user_member', 'user_member')
        resp = self.url_open(self.url_post_members)
        self.assertEqual(resp.status_code, 200)

    # ── Liste /blog — filtrage ────────────────────────────────────────────

    def test_liste_blogs_anonyme_cache_members(self):
        resp = self.url_open('/blog')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Blog Membres', resp.text)
        self.assertIn('Blog Public', resp.text)

    def test_liste_blogs_interne_affiche_members(self):
        self.authenticate('user_member', 'user_member')
        resp = self.url_open('/blog')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Blog Membres', resp.text)

    # ── Modèle — is_accessible_by ─────────────────────────────────────────

    def test_is_accessible_by_public(self):
        self.assertTrue(self.blog_public.is_accessible_by(self.user_portal))
        self.assertTrue(self.blog_public.is_accessible_by(self.env.ref('base.public_user')))

    def test_is_accessible_by_members_interne(self):
        self.assertTrue(self.blog_members.is_accessible_by(self.user_member))

    def test_is_accessible_by_members_portal(self):
        self.assertFalse(self.blog_members.is_accessible_by(self.user_portal))

    def test_is_accessible_by_members_public_user(self):
        self.assertFalse(self.blog_members.is_accessible_by(self.env.ref('base.public_user')))


class TestBlogVisibilityMixin(common.TransactionCase):
    """Tests unitaires du mixin sur blog.blog (sans HTTP)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.rel_type = cls.env['res.partner.relation.type'].create({
            'name': 'Partenaire de', 'name_inverse': 'Partenaire de', 'is_symmetric': True,
        })
        cls.user_owner = cls.env['res.users'].create({
            'name': 'Owner', 'login': 'owner_blog', 'email': 'owner_blog@test.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.user_other = cls.env['res.users'].create({
            'name': 'Other', 'login': 'other_blog', 'email': 'other_blog@test.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.partner_owner = cls.user_owner.partner_id
        cls.partner_other = cls.user_other.partner_id

    def _blog(self, visibility, **kwargs):
        vals = {'name': 'Blog test', 'visibility': visibility}
        vals.update(kwargs)
        return self.env['blog.blog'].create(vals)

    def test_public_accessible_to_all(self):
        blog = self._blog('public')
        self.assertTrue(blog._is_accessible_by(self.partner_other))

    def test_members_accessible_to_internal(self):
        blog = self._blog('members')
        self.assertTrue(blog._is_accessible_by(self.partner_other))

    def test_relations_with_matching_relation(self):
        blog = self._blog(
            'relations',
            owner_partner_id=self.partner_owner.id,
            allowed_relation_type_ids=[(6, 0, [self.rel_type.id])],
        )
        self.env['res.partner.relation'].create({
            'left_partner_id': self.partner_owner.id,
            'right_partner_id': self.partner_other.id,
            'type_id': self.rel_type.id,
        })
        self.assertTrue(blog._is_accessible_by(self.partner_other))

    def test_relations_without_relation(self):
        blog = self._blog(
            'relations',
            owner_partner_id=self.partner_owner.id,
            allowed_relation_type_ids=[(6, 0, [self.rel_type.id])],
        )
        self.assertFalse(blog._is_accessible_by(self.partner_other))

    def test_relations_owner_always_visible(self):
        blog = self._blog(
            'relations',
            owner_partner_id=self.partner_owner.id,
            allowed_relation_type_ids=[(6, 0, [self.rel_type.id])],
        )
        self.assertTrue(blog._is_accessible_by(self.partner_owner))

    def test_connections_no_owner_fallback_to_members(self):
        """Sans owner_partner_id, connections se replie sur 'membres'."""
        blog = self._blog('connections')
        self.assertTrue(blog._is_accessible_by(self.partner_other))  # interne → membre
