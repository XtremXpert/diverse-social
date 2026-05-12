from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('club_social_profile', 'connection')
class TestClubSocialConnection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user1 = cls.env.ref('base.user_demo')
        cls.user2 = cls.env['res.users'].create({
            'name': 'Conn User 2', 'login': 'conn_user2', 'email': 'conn2@test.test',
        })
        cls.Conn = cls.env['club_social_profile.connection']

    def test_send_friend_request(self):
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
            'connection_type': 'friend',
        })
        self.assertEqual(conn.state, 'pending')

    def test_self_connection_rejected(self):
        with self.assertRaises(ValidationError):
            self.Conn.create({
                'user_id': self.user1.id,
                'connected_user_id': self.user1.id,
                'connection_type': 'friend',
            })

    def test_duplicate_rejected(self):
        self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
        })
        with self.assertRaises(ValidationError):
            self.Conn.create({
                'user_id': self.user1.id,
                'connected_user_id': self.user2.id,
            })

    def test_accept_creates_reciprocal(self):
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
            'connection_type': 'friend',
        })
        conn.action_accept()
        self.assertEqual(conn.state, 'accepted')
        reciprocal = self.Conn.search([
            ('user_id', '=', self.user2.id),
            ('connected_user_id', '=', self.user1.id),
        ])
        self.assertTrue(reciprocal)

    def test_is_connected(self):
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
        })
        self.assertFalse(self.Conn.is_connected(self.user1, self.user2))
        conn.write({'state': 'accepted'})
        self.assertTrue(self.Conn.is_connected(self.user1, self.user2))
