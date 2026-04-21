from odoo.tests import common, tagged


@tagged('post_install', '-at_install', 'website_blog_restricted')
class TestBlogRestricted(common.HttpCase):
    """Tests pour la restriction d'accès aux blogs par utilisateur."""

    def setUp(self):
        super().setUp()

        # Blog public — aucune restriction
        self.blog_public = self.env['blog.blog'].create({
            'name': 'Blog Public',
        })

        # Blog restreint
        self.blog_restreint = self.env['blog.blog'].create({
            'name': 'Blog Privé',
        })

        # Article dans chaque blog
        self.post_public = self.env['blog.post'].create({
            'name': 'Article public',
            'blog_id': self.blog_public.id,
            'website_published': True,
        })
        self.post_restreint = self.env['blog.post'].create({
            'name': 'Article privé',
            'blog_id': self.blog_restreint.id,
            'website_published': True,
        })

        # Utilisateur autorisé
        self.user_autorise = self.env['res.users'].create({
            'name': 'Utilisateur Autorisé',
            'login': 'user_autorise',
            'password': 'user_autorise',
            'email': 'autorise@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

        # Utilisateur non autorisé
        self.user_non_autorise = self.env['res.users'].create({
            'name': 'Utilisateur Non Autorisé',
            'login': 'user_non_autorise',
            'password': 'user_non_autorise',
            'email': 'non_autorise@test.com',
            'groups_id': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

        # Appliquer la restriction
        self.blog_restreint.restricted_user_ids = self.user_autorise

        # Slugs pour les URLs
        self.slug = self.env['ir.http']._slug
        self.blog_public_url = '/blog/%s' % self.slug(self.blog_public)
        self.blog_restreint_url = '/blog/%s' % self.slug(self.blog_restreint)
        self.post_public_url = '/blog/%s/%s' % (self.slug(self.blog_public), self.slug(self.post_public))
        self.post_restreint_url = '/blog/%s/%s' % (self.slug(self.blog_restreint), self.slug(self.post_restreint))

    # -----------------------------------------------------------------------
    # Blog public — accessible à tous
    # -----------------------------------------------------------------------

    def test_blog_public_visiteur_anonyme(self):
        """Un blog sans restriction est accessible sans connexion."""
        resp = self.url_open(self.blog_public_url)
        self.assertEqual(resp.status_code, 200)

    def test_blog_public_utilisateur_connecte(self):
        """Un blog sans restriction est accessible à tout utilisateur connecté."""
        self.authenticate('user_non_autorise', 'user_non_autorise')
        resp = self.url_open(self.blog_public_url)
        self.assertEqual(resp.status_code, 200)

    def test_post_public_visiteur_anonyme(self):
        """Un article d'un blog public est accessible sans connexion."""
        resp = self.url_open(self.post_public_url)
        self.assertEqual(resp.status_code, 200)

    # -----------------------------------------------------------------------
    # Blog restreint — visiteur anonyme
    # -----------------------------------------------------------------------

    def test_blog_restreint_visiteur_anonyme_redirige(self):
        """Un visiteur anonyme est redirigé vers /web/login sur un blog restreint."""
        resp = self.url_open(self.blog_restreint_url, allow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/web/login', resp.headers.get('Location', ''))

    def test_post_restreint_visiteur_anonyme_redirige(self):
        """Un visiteur anonyme est redirigé vers /web/login sur un article restreint."""
        resp = self.url_open(self.post_restreint_url, allow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/web/login', resp.headers.get('Location', ''))

    # -----------------------------------------------------------------------
    # Blog restreint — utilisateur non autorisé
    # -----------------------------------------------------------------------

    def test_blog_restreint_non_autorise_redirige(self):
        """Un utilisateur non listé est redirigé vers /web/login."""
        self.authenticate('user_non_autorise', 'user_non_autorise')
        resp = self.url_open(self.blog_restreint_url, allow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/web/login', resp.headers.get('Location', ''))

    def test_post_restreint_non_autorise_redirige(self):
        """Un utilisateur non listé ne peut pas accéder aux articles du blog restreint."""
        self.authenticate('user_non_autorise', 'user_non_autorise')
        resp = self.url_open(self.post_restreint_url, allow_redirects=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/web/login', resp.headers.get('Location', ''))

    # -----------------------------------------------------------------------
    # Blog restreint — utilisateur autorisé
    # -----------------------------------------------------------------------

    def test_blog_restreint_autorise_accessible(self):
        """L'utilisateur autorisé peut accéder au blog restreint."""
        self.authenticate('user_autorise', 'user_autorise')
        resp = self.url_open(self.blog_restreint_url)
        self.assertEqual(resp.status_code, 200)

    def test_post_restreint_autorise_accessible(self):
        """L'utilisateur autorisé peut lire les articles du blog restreint."""
        self.authenticate('user_autorise', 'user_autorise')
        resp = self.url_open(self.post_restreint_url)
        self.assertEqual(resp.status_code, 200)

    # -----------------------------------------------------------------------
    # Liste des blogs — filtrage
    # -----------------------------------------------------------------------

    def test_liste_blogs_cache_restreint_pour_anonyme(self):
        """La liste /blog ne contient pas les blogs restreints pour un visiteur anonyme."""
        resp = self.url_open('/blog')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Blog Privé', resp.text)
        self.assertIn('Blog Public', resp.text)

    def test_liste_blogs_cache_restreint_pour_non_autorise(self):
        """La liste /blog ne contient pas les blogs restreints pour un utilisateur non autorisé."""
        self.authenticate('user_non_autorise', 'user_non_autorise')
        resp = self.url_open('/blog')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('Blog Privé', resp.text)

    def test_liste_blogs_affiche_restreint_pour_autorise(self):
        """La liste /blog affiche les blogs restreints pour l'utilisateur autorisé."""
        self.authenticate('user_autorise', 'user_autorise')
        resp = self.url_open('/blog')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Blog Privé', resp.text)

    # -----------------------------------------------------------------------
    # Modèle — méthode is_accessible_by
    # -----------------------------------------------------------------------

    def test_is_accessible_by_sans_restriction(self):
        """Un blog sans restriction est accessible par n'importe quel utilisateur."""
        self.assertTrue(self.blog_public.is_accessible_by(self.user_non_autorise))
        self.assertTrue(self.blog_public.is_accessible_by(self.env.ref('base.public_user')))

    def test_is_accessible_by_avec_restriction(self):
        """is_accessible_by retourne True/False selon la liste des utilisateurs."""
        self.assertTrue(self.blog_restreint.is_accessible_by(self.user_autorise))
        self.assertFalse(self.blog_restreint.is_accessible_by(self.user_non_autorise))
        self.assertFalse(self.blog_restreint.is_accessible_by(self.env.ref('base.public_user')))
