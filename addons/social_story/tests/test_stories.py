from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('social_story', 'story')
class TestSocialStory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Story Test User',
            'login': 'story_test_user',
            'email': 'story@test.test',
            'group_ids': [(4, cls.env.ref('social_base.group_social_user').id)],
        })
        cls.Story = cls.env['social_story.story']

    def _make_story(self, name='My Story'):
        return self.Story.with_user(self.user).create({'name': name})

    def test_create_story_active(self):
        story = self._make_story()
        self.assertEqual(story.state, 'active')
        self.assertEqual(story.author_id, self.user)

    def test_expires_at_24h(self):
        story = self._make_story()
        delta = story.expires_at - story.create_date
        self.assertAlmostEqual(delta.total_seconds(), 86400, delta=60)

    def test_expired_state(self):
        story = self._make_story()
        story.write({'expires_at': fields.Datetime.now() - timedelta(hours=1)})
        story._compute_state()
        self.assertEqual(story.state, 'expired')

    def test_mark_as_viewed(self):
        story = self._make_story()
        story.mark_as_viewed(self.user)
        self.assertIn(self.user, story.viewer_ids)
        self.assertEqual(story.view_count, 1)

    def test_mark_as_viewed_idempotent(self):
        story = self._make_story()
        story.mark_as_viewed(self.user)
        story.mark_as_viewed(self.user)
        self.assertEqual(story.view_count, 1)

    def test_story_reaction(self):
        story = self._make_story()
        self.env['social_base.reaction'].create({
            'story_id': story.id,
            'user_id': self.user.id,
            'type': 'love',
        })
        self.assertEqual(len(story.reaction_ids), 1)
        self.assertEqual(story.reaction_ids.target_model, 'social_story.story')

    def test_action_archive(self):
        story = self._make_story()
        story.action_archive()
        self.assertEqual(story.state, 'archived')

    # ── Media type ────────────────────────────────────────────────────────────

    def test_media_type_defaults_photo(self):
        story = self._make_story('Photo Story')
        self.assertEqual(story.media_type, 'photo')

    def test_media_type_video_from_attachment(self):
        story = self._make_story('Video Story')
        self.env['ir.attachment'].sudo().create({
            'name': 'clip.mp4',
            'res_model': 'social_story.story',
            'res_id': story.id,
            'mimetype': 'video/mp4',
            'datas': b'',
        })
        story._compute_media_type()
        self.assertEqual(story.media_type, 'video')

    # ── Cron ──────────────────────────────────────────────────────────────────

    def test_cron_deletes_stories_expired_over_7_days(self):
        story = self.Story.sudo().create({'name': 'Old Expired', 'author_id': self.user.id})
        story.sudo().write({
            'expires_at': fields.Datetime.now() - timedelta(days=8),
        })
        story._compute_state()
        self.assertEqual(story.state, 'expired')
        story_id = story.id
        self.Story.cron_cleanup_expired_stories()
        self.assertFalse(self.Story.sudo().browse(story_id).exists())

    def test_cron_keeps_stories_expired_under_7_days(self):
        story = self.Story.sudo().create({'name': 'Recent Expired', 'author_id': self.user.id})
        story.sudo().write({
            'expires_at': fields.Datetime.now() - timedelta(hours=2),
        })
        story._compute_state()
        self.assertEqual(story.state, 'expired')
        self.Story.cron_cleanup_expired_stories()
        self.assertTrue(self.Story.sudo().browse(story.id).exists())

    def test_cron_keeps_active_stories(self):
        story = self._make_story('Active Story Cron')
        self.assertEqual(story.state, 'active')
        self.Story.cron_cleanup_expired_stories()
        self.assertTrue(self.Story.sudo().browse(story.id).exists())

    def test_cron_returns_count(self):
        stories = [
            self.Story.sudo().create({'name': f'Cron Del {i}', 'author_id': self.user.id})
            for i in range(3)
        ]
        for s in stories:
            s.sudo().write({'expires_at': fields.Datetime.now() - timedelta(days=8)})
            s._compute_state()
        count = self.Story.cron_cleanup_expired_stories()
        self.assertGreaterEqual(count, 3)
