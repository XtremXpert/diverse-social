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

    def test_cron_keeps_archived_stories(self):
        """Le cron ne supprime pas les stories archivées (seulement les expirées >7j)."""
        story = self.Story.sudo().create({'name': 'Archived Kept', 'author_id': self.user.id})
        story.action_archive()
        story_id = story.id
        self.Story.cron_cleanup_expired_stories()
        self.assertTrue(self.Story.sudo().browse(story_id).exists())

    def test_mark_as_viewed_multiple_users(self):
        """Deux utilisateurs distincts incrémentent view_count à 2."""
        other_user = self.env['res.users'].create({
            'name': 'Other Viewer', 'login': 'story_other_viewer',
            'email': 'otherview@test.test',
            'group_ids': [(4, self.env.ref('social_base.group_social_user').id)],
        })
        story = self._make_story('Multi Viewer Story')
        story.mark_as_viewed(self.user)
        story.mark_as_viewed(other_user)
        self.assertEqual(story.view_count, 2)
        self.assertIn(self.user, story.viewer_ids)
        self.assertIn(other_user, story.viewer_ids)

    def test_media_type_photo_from_image_attachment(self):
        """Un attachement image/jpeg → media_type reste 'photo'."""
        story = self._make_story('Image Story')
        self.env['ir.attachment'].sudo().create({
            'name': 'pic.jpg',
            'res_model': 'social_story.story',
            'res_id': story.id,
            'mimetype': 'image/jpeg',
            'datas': b'',
        })
        story._compute_media_type()
        self.assertEqual(story.media_type, 'photo')

    def test_reaction_no_target_model_false(self):
        """Une réaction sans post, comment ou story → target_model False."""
        reaction = self.env['social_base.reaction'].create({
            'user_id': self.user.id,
            'type': 'like',
        })
        self.assertFalse(reaction.target_model)

    def test_story_to_dict_viewed_field(self):
        """_story_to_dict retourne viewed=True après mark_as_viewed."""
        story = self._make_story('Dict Viewed Story')
        story.mark_as_viewed(self.user)
        Feed = self.env['social_story.story'].sudo()
        self.assertIn(self.user, story.viewer_ids)

    def test_multiple_reactions_from_different_users(self):
        other_user = self.env['res.users'].create({
            'name': 'Reactor 2', 'login': 'story_reactor2',
            'email': 'react2@test.test',
            'group_ids': [(4, self.env.ref('social_base.group_social_user').id)],
        })
        story = self._make_story('Multi Reaction Story')
        self.env['social_base.reaction'].create({
            'story_id': story.id, 'user_id': self.user.id, 'type': 'love',
        })
        self.env['social_base.reaction'].create({
            'story_id': story.id, 'user_id': other_user.id, 'type': 'like',
        })
        self.assertEqual(len(story.reaction_ids), 2)
