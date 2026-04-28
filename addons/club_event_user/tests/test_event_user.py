from odoo.tests import common, tagged


@tagged('club_event_user')
class TestEventRegistrationUser(common.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env['res.users'].create({
            'name': 'Event User', 'login': 'evtuser@test.com', 'email': 'evtuser@test.com',
        })
        cls.event = cls.env['event.event'].create({
            'name': 'Test Event',
            'date_begin': '2030-01-01 10:00:00',
            'date_end': '2030-01-01 18:00:00',
        })

    def test_user_id_field_exists(self):
        self.assertIn('user_id', self.env['event.registration']._fields)

    def test_allowed_fields_includes_user_id(self):
        reg = self.env['event.registration'].new({'event_id': self.event.id})
        allowed = reg._get_website_registration_allowed_fields()
        self.assertIn('user_id', allowed)

    def test_onchange_user_fills_partner(self):
        reg = self.env['event.registration'].new({
            'event_id': self.event.id,
            'user_id': self.user.id,
        })
        reg._onchange_user_id()
        self.assertEqual(reg.partner_id, self.user.partner_id)

    def test_onchange_user_fills_name_with_login(self):
        reg = self.env['event.registration'].new({
            'event_id': self.event.id,
            'user_id': self.user.id,
        })
        reg._onchange_user_id()
        self.assertEqual(reg.name, self.user.login)

    def test_onchange_user_fills_email(self):
        reg = self.env['event.registration'].new({
            'event_id': self.event.id,
            'user_id': self.user.id,
        })
        reg._onchange_user_id()
        self.assertEqual(reg.email, self.user.email)

    def test_onchange_no_user_does_nothing(self):
        reg = self.env['event.registration'].new({'event_id': self.event.id})
        reg.name = 'Avant'
        reg._onchange_user_id()
        self.assertEqual(reg.name, 'Avant')

    def test_registration_create_with_user(self):
        reg = self.env['event.registration'].create({
            'event_id': self.event.id,
            'user_id': self.user.id,
            'name': self.user.login,
            'email': self.user.email,
            'partner_id': self.user.partner_id.id,
        })
        self.assertEqual(reg.user_id, self.user)
        self.assertEqual(reg.partner_id, self.user.partner_id)

    def test_registration_without_user(self):
        reg = self.env['event.registration'].create({
            'event_id': self.event.id,
            'name': 'Visiteur anonyme',
            'email': 'anon@test.com',
        })
        self.assertFalse(reg.user_id)

    def test_multiple_registrations_same_user_different_events(self):
        event2 = self.env['event.event'].create({
            'name': 'Event 2',
            'date_begin': '2030-06-01 10:00:00',
            'date_end': '2030-06-01 18:00:00',
        })
        reg1 = self.env['event.registration'].create({
            'event_id': self.event.id,
            'user_id': self.user.id,
            'name': self.user.login,
            'email': self.user.email,
            'partner_id': self.user.partner_id.id,
        })
        reg2 = self.env['event.registration'].create({
            'event_id': event2.id,
            'user_id': self.user.id,
            'name': self.user.login,
            'email': self.user.email,
            'partner_id': self.user.partner_id.id,
        })
        self.assertEqual(reg1.user_id, reg2.user_id)
        self.assertNotEqual(reg1.event_id, reg2.event_id)
