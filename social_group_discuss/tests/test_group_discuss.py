from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.social_group_discuss import _post_init_hook


@tagged('post_install', '-at_install')
class TestGroupDiscuss(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.a, cls.b, cls.c = (new_test_user(cls.env, login=f'{n}.groupe@example.com', groups='base.group_portal')
                               for n in 'abc')

    def members(self, group):
        return group.channel_id.channel_member_ids.partner_id

    def test_conversation_follows_the_group(self):
        group = self.env['social_group.group'].create({'name': "Randonnée", 'member_ids': [(6, 0, (self.a | self.b).ids)]})
        self.assertEqual(group.channel_id.channel_type, 'group')
        self.assertEqual(group.channel_id.name, "Randonnée")
        self.assertEqual(self.members(group), (self.a | self.b).partner_id)

        group.write({'member_ids': [(4, self.c.id), (3, self.a.id)]})
        self.assertEqual(self.members(group), (self.b | self.c).partner_id, "arrivées et départs suivis")

        group.name = "Randonnée d'automne"
        self.assertEqual(group.channel_id.name, "Randonnée d'automne")

        channel = group.channel_id
        group.unlink()
        self.assertFalse(channel.channel_member_ids, "groupe supprimé : plus personne dans la conversation")

    def test_group_without_members_gets_its_conversation_later(self):
        group = self.env['social_group.group'].create({'name': "Vide"})
        self.assertFalse(group.channel_id)
        group.member_ids = self.a
        self.assertEqual(self.members(group), self.a.partner_id)

    def test_existing_groups_at_installation(self):
        group = self.env['social_group.group'].create({'name': "Ancien", 'member_ids': [(6, 0, self.b.ids)]})
        group.channel_id = False
        _post_init_hook(self.env)
        self.assertEqual(self.members(group), self.b.partner_id)
