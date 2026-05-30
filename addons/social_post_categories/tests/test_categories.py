from psycopg2 import IntegrityError

from odoo import tools
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('social_post_categories')
class TestCategories(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Category = cls.env['social_post_categories.category']
        cls.Post = cls.env['social_base.post']
        cls.alerte = cls.Category.create({
            'name': 'Alerte',
            'code': 'alerte',
            'color': '#dc3545',
            'icon': 'fa-bell',
            'sequence': 10,
        })
        cls.annonce = cls.Category.create({
            'name': 'Annonce',
            'code': 'annonce',
            'color': '#0d6efd',
            'sequence': 20,
        })
        cls.author = cls.env['res.users'].create({
            'name': 'Author',
            'login': 'author@test.example',
        })

    # ── Model invariants ─────────────────────────────────────────────────────

    def test_code_must_be_unique(self):
        with self.assertRaises(IntegrityError), tools.mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.Category.create({'name': 'Alerte 2', 'code': 'alerte'})

    def test_code_shape_lowercase_alnum(self):
        with self.assertRaises(ValidationError):
            self.Category.create({'name': 'Bad', 'code': 'Bad Code!'})

    def test_post_can_have_category(self):
        post = self.Post.sudo().create({
            'content': '<p>Annonce: panne d\'eau rang 3</p>',
            'author_id': self.author.id,
            'category_id': self.alerte.id,
        })
        self.assertEqual(post.category_id, self.alerte)

    def test_post_without_category_is_allowed(self):
        post = self.Post.sudo().create({
            'content': '<p>plain post</p>',
            'author_id': self.author.id,
        })
        self.assertFalse(post.category_id)

    def test_unlink_category_preserves_post(self):
        """ondelete='set null' — losing the category beats losing the post."""
        post = self.Post.sudo().create({
            'content': '<p>tied to a category</p>',
            'author_id': self.author.id,
            'category_id': self.annonce.id,
        })
        post_id = post.id
        self.annonce.sudo().unlink()
        post = self.Post.sudo().browse(post_id)
        self.assertTrue(post.exists())
        self.assertFalse(post.category_id)

    def test_post_count_aggregates(self):
        for i in range(3):
            self.Post.sudo().create({
                'content': f'<p>post {i}</p>',
                'author_id': self.author.id,
                'category_id': self.alerte.id,
            })
        self.alerte.invalidate_recordset(['post_count'])
        self.assertEqual(self.alerte.post_count, 3)
        self.assertEqual(self.annonce.post_count, 0)
