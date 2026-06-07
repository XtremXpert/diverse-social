from odoo.tests import TransactionCase, tagged


@tagged('social_group', 'group_discuss')
class TestGroupDiscuss(TransactionCase):
    """Chaque groupe a un canal Discuss de groupe ; les membres du groupe sont
    synchronisés avec les membres du canal (rejoindre/quitter)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        gu = cls.env.ref('base.group_user')
        gs = cls.env.ref('social_base.group_social_user')

        def mk(name, login):
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': '%s@test.test' % login,
                'group_ids': [(4, gu.id), (4, gs.id)],
            })

        cls.u1 = mk('GD User 1', 'gd_user1')
        cls.u2 = mk('GD User 2', 'gd_user2')
        cls.Group = cls.env['social_group.group']

    def _group(self, join_type='open'):
        return self.Group.with_user(self.u1).create({
            'name': 'GD Group', 'privacy': 'public', 'join_type': join_type,
            'member_ids': [(4, self.u1.id)], 'admin_ids': [(4, self.u1.id)],
        })

    def _channel_partners(self, group):
        return group.discuss_channel_id.sudo().channel_member_ids.partner_id

    def test_create_group_creates_channel(self):
        group = self._group()
        self.assertTrue(group.discuss_channel_id)
        self.assertEqual(group.discuss_channel_id.channel_type, 'group')
        self.assertIn(self.u1.partner_id, self._channel_partners(group))

    def test_join_adds_to_channel(self):
        group = self._group(join_type='open')
        group.with_user(self.u2).action_join()
        self.assertIn(self.u2, group.member_ids)
        self.assertIn(self.u2.partner_id, self._channel_partners(group))

    def test_approve_adds_to_channel(self):
        group = self._group(join_type='approval')
        group.with_user(self.u2).action_join()
        req = self.env['social_group.join_request'].search([('group_id', '=', group.id)])
        req.with_user(self.u1).action_approve()
        self.assertIn(self.u2.partner_id, self._channel_partners(group))

    def test_leave_removes_from_channel(self):
        group = self._group(join_type='open')
        group.with_user(self.u2).action_join()
        self.assertIn(self.u2.partner_id, self._channel_partners(group))
        group.with_user(self.u2).action_leave()
        self.assertNotIn(self.u2, group.member_ids)
        self.assertNotIn(self.u2.partner_id, self._channel_partners(group))

    def test_backfill_get_or_create(self):
        group = self._group()
        # Simule un ancien groupe sans canal.
        group.discuss_channel_id.sudo().unlink()
        group.sudo().discuss_channel_id = False
        channel = group._get_or_create_discuss_channel()
        self.assertTrue(channel)
        self.assertEqual(channel.channel_type, 'group')
        self.assertIn(self.u1.partner_id, channel.sudo().channel_member_ids.partner_id)

    def test_rename_group_renames_channel(self):
        group = self._group()
        group.sudo().name = 'GD Renamed'
        self.assertEqual(group.discuss_channel_id.sudo().name, 'GD Renamed')
