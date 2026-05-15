from odoo.tests import HttpCase, TransactionCase, tagged


def _make_social_user(env, name, login):
    group_social = env.ref('social_base.group_social_user')
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@story.test',
        'password': 'Test1234!',
        'group_ids': [(4, group_social.id)],
    })


@tagged('social_story', 'story_portal')
class TestStoryPortalData(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = _make_social_user(cls.env, 'StoryAuthor', 'story_author')
        cls.other = _make_social_user(cls.env, 'StoryOther', 'story_other')
        cls.active_story = cls.env['social_story.story'].sudo().create({
            'name': 'Portal Story Active',
            'author_id': cls.author.id,
        })

    def test_my_stories_returns_own(self):
        stories = cls_env = self.env['social_story.story'].search([
            ('author_id', '=', self.author.id),
        ])
        self.assertIn(self.active_story, stories)

    def test_my_stories_excludes_others(self):
        stories = self.env['social_story.story'].with_user(self.other).search([
            ('author_id', '=', self.author.id),
        ])
        # With default ir.rule: only own active stories visible
        self.assertFalse(stories)

    def test_active_story_state(self):
        self.assertEqual(self.active_story.state, 'active')

    def test_archive_own_story(self):
        story = self.env['social_story.story'].sudo().create({
            'name': 'To Archive', 'author_id': self.author.id,
        })
        story.with_user(self.author).action_archive()
        # state is computed from expires_at; action_archive writes state='archived'
        self.assertEqual(story.state, 'archived')

    def test_cannot_archive_other_story(self):
        from odoo.exceptions import AccessError
        with self.assertRaises((AccessError, Exception)):
            self.active_story.with_user(self.other).action_archive()

    def test_filter_active_excludes_expired(self):
        import datetime
        from odoo import fields
        expired = self.env['social_story.story'].sudo().create({
            'name': 'Expired Story', 'author_id': self.author.id,
        })
        # Force state to expired
        expired.sudo().write({
            'expires_at': fields.Datetime.now() - datetime.timedelta(hours=1),
        })
        expired._compute_state()
        active_stories = self.env['social_story.story'].sudo().search([
            ('author_id', '=', self.author.id),
            ('state', '=', 'active'),
        ])
        self.assertIn(self.active_story, active_stories)
        self.assertNotIn(expired, active_stories)

    # ── ir.rule : visibilité stories expirées ─────────────────────────────────

    def test_ir_rule_user_can_see_own_expired(self):
        """Un utilisateur voit ses propres stories expirées (author_id = user.id)."""
        from odoo import fields
        import datetime
        expired = self.env['social_story.story'].sudo().create({
            'name': 'Own Expired', 'author_id': self.author.id,
        })
        expired.sudo().write({'expires_at': fields.Datetime.now() - datetime.timedelta(hours=1)})
        expired._compute_state()
        self.assertEqual(expired.state, 'expired')
        found = self.env['social_story.story'].with_user(self.author).search(
            [('id', '=', expired.id)]
        )
        self.assertTrue(found)

    def test_ir_rule_user_cannot_see_others_expired(self):
        """Un utilisateur ne voit pas les stories expirées des autres."""
        from odoo import fields
        import datetime
        expired = self.env['social_story.story'].sudo().create({
            'name': 'Other Expired', 'author_id': self.author.id,
        })
        expired.sudo().write({'expires_at': fields.Datetime.now() - datetime.timedelta(hours=1)})
        expired._compute_state()
        self.assertEqual(expired.state, 'expired')
        found = self.env['social_story.story'].with_user(self.other).search(
            [('id', '=', expired.id)]
        )
        self.assertFalse(found)


@tagged('social_story', 'story_portal', 'post_install', '-at_install')
class TestStoryPortalHttp(HttpCase):

    def test_my_stories_unauthenticated_redirects(self):
        resp = self.url_open('/my/stories', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_my_stories_authenticated_ok(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/stories')
        self.assertEqual(resp.status_code, 200)

    def test_my_stories_filter_active(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/stories?filter=active')
        self.assertEqual(resp.status_code, 200)

    def test_my_stories_filter_expired(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/my/stories?filter=expired')
        self.assertEqual(resp.status_code, 200)

    def test_story_archive_forbidden_for_other(self):
        """Un utilisateur ne peut pas archiver la story d'un autre."""
        admin = self.env.ref('base.user_admin')
        story = self.env['social_story.story'].sudo().create({
            'name': 'Other Story HTTP', 'author_id': admin.id,
        })
        other = self.env['res.users'].sudo().create({
            'name': 'HTTP Other', 'login': 'http_other_story',
            'email': 'http_other@story.test', 'password': 'Test1234!',
            'group_ids': [(4, self.env.ref('base.group_portal').id)],
        })
        self.authenticate('http_other_story', 'Test1234!')
        resp = self.url_open(
            f'/my/stories/{story.id}/archive',
            data={'csrf_token': self.csrf_token()},
            allow_redirects=False,
        )
        self.assertIn(resp.status_code, (302, 303, 403))

    def test_story_archive_by_owner(self):
        """Le propriétaire peut archiver sa propre story."""
        group_social = self.env.ref('social_base.group_social_user')
        owner = self.env['res.users'].sudo().create({
            'name': 'Story Owner HTTP', 'login': 'story_owner_http',
            'email': 'owner@story.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        story = self.env['social_story.story'].sudo().create({
            'name': 'My Own Story HTTP', 'author_id': owner.id,
        })
        self.authenticate('story_owner_http', 'Test1234!')
        resp = self.url_open(
            f'/my/stories/{story.id}/archive',
            data={'csrf_token': self.csrf_token()},
        )
        self.assertEqual(resp.status_code, 200)
        story.invalidate_recordset()
        self.assertEqual(story.state, 'archived')

    def test_api_list_stories_returns_json(self):
        """GET /social/api/stories retourne du JSON avec une liste de stories."""
        import json
        group_social = self.env.ref('social_base.group_social_user')
        api_user = self.env['res.users'].sudo().create({
            'name': 'API Story User', 'login': 'api_story_user',
            'email': 'api@story.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        self.authenticate('api_story_user', 'Test1234!')
        resp = self.url_open('/social/api/stories')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertIn('stories', data)
        self.assertIsInstance(data['stories'], list)

    def test_api_stories_unauthenticated_redirects(self):
        resp = self.url_open('/social/api/stories', allow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_api_view_story_nonexistent_404(self):
        self.authenticate('admin', 'admin')
        resp = self.url_open('/social/api/stories/999999999/view', data={})
        self.assertEqual(resp.status_code, 404)

    def test_api_view_story_increments_count(self):
        """POST /social/api/stories/<id>/view incrémente view_count."""
        import json
        group_social = self.env.ref('social_base.group_social_user')
        viewer = self.env['res.users'].sudo().create({
            'name': 'API Viewer', 'login': 'api_viewer_story',
            'email': 'viewer@story.test', 'password': 'Test1234!',
            'group_ids': [(4, group_social.id)],
        })
        admin = self.env.ref('base.user_admin')
        story = self.env['social_story.story'].sudo().create({
            'name': 'API View Story', 'author_id': admin.id,
        })
        self.authenticate('api_viewer_story', 'Test1234!')
        resp = self.url_open(f'/social/api/stories/{story.id}/view', data={})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data.get('view_count'), 1)
