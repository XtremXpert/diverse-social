from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('social_story', 'story')
class TestSocialStory(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env.ref('base.user_demo')
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
