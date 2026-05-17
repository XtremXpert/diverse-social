from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('social_privacy', 'privacy')
class TestPrivacyOfficer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = cls.env['res.users'].create({
            'name': 'Privacy Officer',
            'login': 'privacy_officer_test',
            'email': 'privacy@test.test',
        })

    def test_create_officer(self):
        officer = self.env['social_privacy.officer'].create({
            'user_id': self.test_user.id,
            'appointment_date': '2025-01-15',
        })
        self.assertEqual(officer.user_id, self.test_user)
        self.assertTrue(officer.is_active)

    def test_officer_contact_email(self):
        officer = self.env['social_privacy.officer'].create({
            'user_id': self.test_user.id,
        })
        self.assertEqual(officer.contact_email, 'privacy@test.test')


@tagged('social_privacy', 'privacy')
class TestPrivacyBreach(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.affected = cls.env['res.users'].create({
            'name': 'Affected User', 'login': 'affected_user', 'email': 'affected@test.test',
        })

    def test_breach_sequence(self):
        breach = self.env['social_privacy.breach'].create({
            'description': 'Test breach',
            'severity': 'medium',
            'affected_user_ids': [(6, 0, [self.affected.id])],
        })
        self.assertTrue(breach.name.startswith('BREACH-'))

    def test_breach_workflow(self):
        breach = self.env['social_privacy.breach'].create({
            'description': 'Unauthorized data access',
            'severity': 'high',
            'affected_user_ids': [(6, 0, [self.affected.id])],
        })
        self.assertEqual(breach.state, 'detected')

        breach.action_investigate()
        self.assertEqual(breach.state, 'investigating')

        breach.action_notify_cai()
        self.assertEqual(breach.state, 'notified_cai')
        self.assertTrue(breach.notification_date)
        self.assertTrue(breach.cai_notified_in_time)

    def test_breach_notification_date_constraint(self):
        breach = self.env['social_privacy.breach'].create({
            'description': 'Test',
            'severity': 'low',
        })
        with self.assertRaises(ValidationError):
            breach.write({'notification_date': '2020-01-01'})


@tagged('social_privacy', 'privacy')
class TestPrivacyAccessLog(TransactionCase):

    def test_create_log(self):
        user = self.env['res.users'].create({
            'name': 'Log User', 'login': 'log_user', 'email': 'log@test.test',
        })
        target = self.env['res.users'].create({
            'name': 'Target User', 'login': 'target_user', 'email': 'target@test.test',
        })
        log = self.env['social_privacy.access_log'].create({
            'user_id': user.id,
            'target_user_id': target.id,
            'model_name': 'social_base.post',
            'record_id': 1,
            'action': 'read',
        })
        self.assertEqual(log.action, 'read')
        self.assertEqual(log.model_name, 'social_base.post')


@tagged('social_privacy', 'privacy')
class TestDataExportRequest(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_user = cls.env['res.users'].create({
            'name': 'Export User',
            'login': 'export_user',
            'email': 'export@test.test',
        })

    def test_export_request_lifecycle(self):
        req = self.env['social_privacy.export_request'].with_user(self.test_user).create({
            'user_id': self.test_user.id,
        })
        self.assertEqual(req.state, 'pending')

        req.action_generate_export()
        self.assertEqual(req.state, 'ready')
        self.assertTrue(req.export_file)
        self.assertTrue(req.export_filename.endswith('.json'))
        self.assertTrue(req.expires_at)

        req.action_mark_downloaded()
        self.assertEqual(req.state, 'downloaded')

    def test_cron_expire(self):
        req = self.env['social_privacy.export_request'].with_user(self.test_user).create({
            'user_id': self.test_user.id,
        })
        req.action_generate_export()
        # Simulate expiration
        req.write({'expires_at': '2000-01-01 00:00:00'})
        count = self.env['social_privacy.export_request'].cron_expire_old_exports()
        self.assertGreaterEqual(count, 1)
        req.invalidate_recordset()
        self.assertEqual(req.state, 'expired')
