import datetime

from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged('club_membership', 'membership')
class TestClubMembership(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.group_social = cls.env.ref('social_base.group_social_user')

        cls.partner_alice = cls.env['res.partner'].create({
            'name': 'Alice Membre', 'email': 'alice@member.test',
        })
        cls.partner_bob = cls.env['res.partner'].create({
            'name': 'Bob Membre', 'email': 'bob@member.test',
        })
        cls.user_alice = cls.env['res.users'].create({
            'name': 'Alice Membre', 'login': 'mbr_alice',
            'email': 'alice@member.test', 'partner_id': cls.partner_alice.id,
        })
        cls.user_bob = cls.env['res.users'].create({
            'name': 'Bob Membre', 'login': 'mbr_bob',
            'email': 'bob@member.test', 'partner_id': cls.partner_bob.id,
        })

        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')
        cls.type_lifetime = cls.env.ref('club_membership.membership_type_lifetime')
        cls.type_trial = cls.env.ref('club_membership.membership_type_trial')

        cls.Membership = cls.env['club_membership.membership']

    def _make_membership(self, partner, mtype=None, state='pending', start=None):
        return self.Membership.sudo().create({
            'partner_id': partner.id,
            'membership_type_id': (mtype or self.type_regular).id,
            'state': state,
            'start_date': start or datetime.date.today(),
        })

    # ── Création & computed fields ────────────────────────────────────────────

    def test_user_id_computed_from_partner(self):
        m = self._make_membership(self.partner_alice)
        self.assertEqual(m.user_id, self.user_alice)

    def test_display_name_contains_partner(self):
        m = self._make_membership(self.partner_alice)
        self.assertIn('Alice Membre', m.display_name)

    # ── Transitions d'état ────────────────────────────────────────────────────

    def test_activate_from_pending(self):
        m = self._make_membership(self.partner_alice)
        m.action_activate()
        self.assertEqual(m.state, 'active')

    def test_activate_from_suspended(self):
        m = self._make_membership(self.partner_alice, state='active')
        m.action_suspend()
        m.action_activate()
        self.assertEqual(m.state, 'active')

    def test_activate_invalid_state_raises(self):
        m = self._make_membership(self.partner_alice, state='active')
        m.action_cancel()
        with self.assertRaises(UserError):
            m.action_activate()

    def test_suspend_active_membership(self):
        m = self._make_membership(self.partner_alice)
        m.action_activate()
        m.action_suspend()
        self.assertEqual(m.state, 'suspended')

    def test_suspend_non_active_raises(self):
        m = self._make_membership(self.partner_alice)
        with self.assertRaises(UserError):
            m.action_suspend()

    def test_cancel_any_state(self):
        m = self._make_membership(self.partner_alice)
        m.action_cancel()
        self.assertEqual(m.state, 'cancelled')

    def test_cancel_idempotent(self):
        m = self._make_membership(self.partner_alice)
        m.action_cancel()
        m.action_cancel()
        self.assertEqual(m.state, 'cancelled')

    # ── Accès réseau social ───────────────────────────────────────────────────

    def test_activate_grants_social_access(self):
        m = self._make_membership(self.partner_bob)
        self.assertNotIn(self.group_social, self.user_bob.groups_id)
        m.action_activate()
        self.assertIn(self.group_social, self.user_bob.sudo().groups_id)

    def test_suspend_revokes_social_access(self):
        m = self._make_membership(self.partner_bob)
        m.action_activate()
        self.assertIn(self.group_social, self.user_bob.sudo().groups_id)
        m.action_suspend()
        self.assertNotIn(self.group_social, self.user_bob.sudo().groups_id)

    def test_cancel_revokes_social_access(self):
        m = self._make_membership(self.partner_bob)
        m.action_activate()
        m.action_cancel()
        self.assertNotIn(self.group_social, self.user_bob.sudo().groups_id)

    def test_two_active_memberships_keep_access_on_cancel_one(self):
        m1 = self._make_membership(self.partner_alice)
        m1.action_activate()
        # Manually create a second active (bypass unique constraint for test)
        m2 = self.Membership.sudo().create({
            'partner_id': self.partner_alice.id,
            'membership_type_id': self.type_trial.id,
            'state': 'active',
            'start_date': datetime.date.today(),
        })
        m1.action_cancel()
        # Alice still has m2 active → should keep social access
        self.assertIn(self.group_social, self.user_alice.sudo().groups_id)

    # ── Durée automatique ─────────────────────────────────────────────────────

    def test_end_date_computed_on_activate(self):
        m = self._make_membership(self.partner_alice)
        self.assertFalse(m.end_date)
        m.action_activate()
        self.assertTrue(m.end_date)
        expected = m.start_date + datetime.timedelta(days=365)
        delta = abs((m.end_date - expected).days)
        self.assertLessEqual(delta, 1)

    def test_lifetime_no_end_date(self):
        m = self._make_membership(self.partner_alice, mtype=self.type_lifetime)
        m.action_activate()
        self.assertFalse(m.end_date)

    def test_explicit_end_date_not_overwritten(self):
        end = datetime.date.today() + datetime.timedelta(days=180)
        m = self.Membership.sudo().create({
            'partner_id': self.partner_alice.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'end_date': end,
        })
        m.action_activate()
        self.assertEqual(m.end_date, end)

    # ── Cron d'expiration ─────────────────────────────────────────────────────

    def test_cron_expires_overdue_memberships(self):
        past_end = datetime.date.today() - datetime.timedelta(days=1)
        m = self.Membership.sudo().create({
            'partner_id': self.partner_alice.id,
            'membership_type_id': self.type_regular.id,
            'state': 'active',
            'start_date': past_end - datetime.timedelta(days=365),
            'end_date': past_end,
        })
        # Manually grant access to test revocation
        self.user_alice.sudo().write({'group_ids': [(4, self.group_social.id)]})
        self.Membership.cron_check_expiry()
        self.assertEqual(m.state, 'expired')
        self.assertNotIn(self.group_social, self.user_alice.sudo().groups_id)

    def test_cron_ignores_future_end_date(self):
        m = self._make_membership(self.partner_bob)
        m.action_activate()
        self.assertEqual(m.state, 'active')
        self.Membership.cron_check_expiry()
        self.assertEqual(m.state, 'active')

    # ── Contraintes ───────────────────────────────────────────────────────────

    def test_end_date_before_start_raises(self):
        with self.assertRaises(ValidationError):
            self.Membership.sudo().create({
                'partner_id': self.partner_alice.id,
                'membership_type_id': self.type_regular.id,
                'start_date': datetime.date.today(),
                'end_date': datetime.date.today() - datetime.timedelta(days=1),
            })

    def test_unique_active_constraint(self):
        m1 = self._make_membership(self.partner_alice)
        m1.action_activate()
        m2 = self._make_membership(self.partner_alice)
        with self.assertRaises(ValidationError):
            m2.action_activate()

    # ── res.partner computed fields ───────────────────────────────────────────

    def test_partner_member_state_none(self):
        self.assertEqual(self.partner_bob.member_state, 'none')

    def test_partner_member_state_active(self):
        m = self._make_membership(self.partner_bob)
        m.action_activate()
        self.assertEqual(self.partner_bob.member_state, 'active')

    def test_partner_current_membership(self):
        m = self._make_membership(self.partner_bob)
        m.action_activate()
        self.assertEqual(self.partner_bob.current_membership_id, m)

    # ── Type d'adhésion ───────────────────────────────────────────────────────

    def test_membership_type_data_loaded(self):
        self.assertTrue(self.type_regular.exists())
        self.assertTrue(self.type_lifetime.exists())
        self.assertTrue(self.type_trial.exists())

    def test_lifetime_duration_zero(self):
        self.assertEqual(self.type_lifetime.duration_months, 0)
