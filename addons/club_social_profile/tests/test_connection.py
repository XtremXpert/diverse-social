import json

from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('club_social_profile', 'connection', 'post_install', '-at_install')
class TestClubSocialConnection(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        cls.user1 = cls.env['res.users'].create({
            'name': 'Conn User 1', 'login': 'conn_test_user1', 'email': 'conn1@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.user2 = cls.env['res.users'].create({
            'name': 'Conn User 2', 'login': 'conn_test_user2', 'email': 'conn2@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
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

    def test_action_reject(self):
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
        })
        conn.action_reject()
        self.assertEqual(conn.state, 'rejected')

    def test_action_block(self):
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
        })
        conn.action_block()
        self.assertEqual(conn.state, 'blocked')

    def test_action_unblock(self):
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
            'state': 'blocked',
        })
        conn.action_unblock()
        self.assertEqual(conn.state, 'rejected')

    def test_action_unfriend_removes_both_sides(self):
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })
        reciprocal = self.Conn.create({
            'user_id': self.user2.id,
            'connected_user_id': self.user1.id,
            'connection_type': 'friend',
            'state': 'accepted',
        })
        conn_id = conn.id
        recip_id = reciprocal.id
        conn.action_unfriend()
        self.assertFalse(self.Conn.browse(conn_id).exists())
        self.assertFalse(self.Conn.browse(recip_id).exists())

    def test_is_connected_not_directional(self):
        """is_connected est directionnel : user1→user2 ≠ user2→user1."""
        self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
            'state': 'accepted',
        })
        self.assertTrue(self.Conn.is_connected(self.user1, self.user2))
        self.assertFalse(self.Conn.is_connected(self.user2, self.user1))

    def test_accept_sets_accepted_date(self):
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': self.user2.id,
            'connection_type': 'friend',
        })
        conn.action_accept()
        self.assertTrue(conn.accepted_date)

    def test_following_type_no_reciprocal(self):
        """The 'following' type does not create a reciprocal connection."""
        group_user = self.env.ref('base.group_user')
        group_social = self.env.ref('social_base.group_social_user')
        user3 = self.env['res.users'].create({
            'name': 'Follower', 'login': 'conn_follower', 'email': 'follow@test.test',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        conn = self.Conn.create({
            'user_id': self.user1.id,
            'connected_user_id': user3.id,
            'connection_type': 'following',
        })
        conn.action_accept()
        reciprocal = self.Conn.search([
            ('user_id', '=', user3.id),
            ('connected_user_id', '=', self.user1.id),
        ])
        self.assertFalse(reciprocal)


@tagged('club_social_profile', 'connection', 'post_install', '-at_install')
class TestConnectionsApiHttp(HttpCase):
    """HTTP-level checks for /social/api/connections.

    Pending requests are stored on the sender's row (connected_user_id is the
    recipient) until acceptance creates the reciprocal. The list endpoint must
    therefore look at connected_user_id when state='pending', otherwise the
    recipient cannot see what's waiting for them.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')
        cls.sender = cls.env['res.users'].create({
            'name': 'Conn Sender', 'login': 'conn_api_sender',
            'email': 'sender@conn.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })
        cls.recipient = cls.env['res.users'].create({
            'name': 'Conn Recipient', 'login': 'conn_api_recipient',
            'email': 'recipient@conn.test', 'password': 'Test1234!',
            'group_ids': [(4, group_user.id), (4, group_social.id)],
        })

    def test_recipient_sees_pending_request(self):
        self.authenticate('conn_api_sender', 'Test1234!')
        resp = self.url_open('/social/api/connections', data={
            'user_id': self.recipient.id, 'connection_type': 'friend',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'), resp.text)

        self.authenticate('conn_api_recipient', 'Test1234!')
        resp = self.url_open('/social/api/connections?state=pending')
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get('success'), resp.text)
        connections = payload['data']['connections']
        self.assertEqual(len(connections), 1,
                         f'recipient should see one pending request, got: {connections}')
        self.assertEqual(connections[0]['connected_user_id'], self.recipient.id)
        self.assertEqual(connections[0]['user_id'], self.sender.id)

    def test_sender_does_not_see_request_in_pending(self):
        """state=pending lists requests waiting for the current user; the
        sender's own outgoing request should not appear there."""
        self.authenticate('conn_api_sender', 'Test1234!')
        resp = self.url_open('/social/api/connections', data={
            'user_id': self.recipient.id, 'connection_type': 'friend',
        })
        self.assertEqual(resp.status_code, 200)

        resp = self.url_open('/social/api/connections?state=pending')
        self.assertTrue(resp.json().get('success'))
        self.assertEqual(resp.json()['data']['connections'], [])

    def test_self_connect_does_not_leak_into_db(self):
        """Self-connect must hit the constraint AND roll back the INSERT.
        Without a savepoint, the controller's `except ValidationError`
        catches the error but leaves the partial row committed."""
        self.authenticate('conn_api_sender', 'Test1234!')
        resp = self.url_open('/social/api/connections', data={
            'user_id': self.sender.id, 'connection_type': 'friend',
        })
        self.assertEqual(resp.status_code, 400)
        leaked = self.env['club_social_profile.connection'].sudo().search([
            ('user_id', '=', self.sender.id),
            ('connected_user_id', '=', self.sender.id),
        ])
        self.assertFalse(leaked, f'Self-connect leaked: {leaked}')

    def test_duplicate_connect_does_not_leak_into_db(self):
        """A duplicate request must not double the count in DB."""
        self.authenticate('conn_api_sender', 'Test1234!')
        # First call succeeds
        resp = self.url_open('/social/api/connections', data={
            'user_id': self.recipient.id, 'connection_type': 'friend',
        })
        self.assertEqual(resp.status_code, 200)
        # Second call must hit the unique-connection constraint and roll back
        resp = self.url_open('/social/api/connections', data={
            'user_id': self.recipient.id, 'connection_type': 'friend',
        })
        self.assertEqual(resp.status_code, 400)
        count = self.env['club_social_profile.connection'].sudo().search_count([
            ('user_id', '=', self.sender.id),
            ('connected_user_id', '=', self.recipient.id),
        ])
        self.assertEqual(count, 1, 'Duplicate request leaked a second row')
