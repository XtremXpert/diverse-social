from datetime import timedelta
from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('social_safety', 'safety')
class TestBlock(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('social_base.group_social_user')

        def make_user(name, login, email):
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': email,
                'group_ids': [(4, group_user.id)],
            })

        cls.alice = make_user('Alice', 'safety_alice', 'alice@safety.test')
        cls.bob = make_user('Bob', 'safety_bob', 'bob@safety.test')
        cls.carol = make_user('Carol', 'safety_carol', 'carol@safety.test')

        Profile = cls.env['club_social_profile.profile']
        cls.alice_p = Profile.get_or_create_for_user(cls.alice)
        cls.bob_p = Profile.get_or_create_for_user(cls.bob)
        cls.carol_p = Profile.get_or_create_for_user(cls.carol)

        cls.alice_p.write({'visibility': 'members'})
        cls.bob_p.write({'visibility': 'members'})
        cls.carol_p.write({'visibility': 'members'})

        cls.Block = cls.env['social_safety.block']
        cls.Mute = cls.env['social_safety.mute']

    # ── Block ─────────────────────────────────────────────────────────────────

    def test_block_user(self):
        self.Block.with_user(self.alice).block_user(self.bob)
        self.assertTrue(self.Block.is_blocked(self.alice, self.bob))

    def test_block_is_bidirectional(self):
        self.Block.with_user(self.alice).block_user(self.bob)
        self.assertTrue(self.Block.is_blocked(self.bob, self.alice))

    def test_block_idempotent(self):
        self.Block.with_user(self.alice).block_user(self.bob)
        b2 = self.Block.with_user(self.alice).block_user(self.bob)
        self.assertEqual(self.Block.search_count([
            ('blocker_id', '=', self.alice.id), ('blocked_id', '=', self.bob.id)
        ]), 1)

    def test_cannot_block_self(self):
        with self.assertRaises(ValidationError):
            self.Block.with_user(self.alice).create({
                'blocker_id': self.alice.id,
                'blocked_id': self.alice.id,
            })

    def test_unblock(self):
        self.Block.with_user(self.alice).block_user(self.bob)
        self.Block.with_user(self.alice).unblock_user(self.bob)
        self.assertFalse(self.Block.is_blocked(self.alice, self.bob))

    def test_get_blocked_ids(self):
        self.Block.with_user(self.alice).block_user(self.bob)
        ids = self.Block.get_blocked_ids_for(self.alice)
        self.assertIn(self.bob.id, ids)
        self.assertNotIn(self.alice.id, ids)

    def test_unrelated_not_blocked(self):
        self.assertFalse(self.Block.is_blocked(self.alice, self.carol))

    # ── Profile helpers ───────────────────────────────────────────────────────

    def test_profile_has_blocked(self):
        self.Block.with_user(self.alice).block_user(self.bob)
        self.assertTrue(self.alice_p.has_blocked(self.bob))
        self.assertFalse(self.alice_p.has_blocked(self.carol))

    def test_profile_is_blocked_by(self):
        self.Block.with_user(self.bob).block_user(self.alice)
        self.assertTrue(self.alice_p.is_blocked_by(self.bob))

    def test_is_safe_to_contact_blocked(self):
        self.Block.with_user(self.alice).block_user(self.bob)
        self.assertFalse(self.alice_p.is_safe_to_contact(self.bob))

    def test_is_safe_to_contact_clean(self):
        self.assertTrue(self.alice_p.is_safe_to_contact(self.carol))

    # ── Mute ──────────────────────────────────────────────────────────────────

    def test_mute_user(self):
        self.Mute.with_user(self.alice).mute_user(self.bob)
        self.assertTrue(self.Mute.is_muted(self.alice, self.bob))

    def test_mute_is_not_bidirectional(self):
        self.Mute.with_user(self.alice).mute_user(self.bob)
        self.assertFalse(self.Mute.is_muted(self.bob, self.alice))

    def test_mute_temporary_active(self):
        future = fields.Datetime.now() + timedelta(hours=24)
        self.Mute.with_user(self.alice).mute_user(self.bob, until=future)
        self.assertTrue(self.Mute.is_muted(self.alice, self.bob))

    def test_mute_expired(self):
        past = fields.Datetime.now() - timedelta(hours=1)
        self.Mute.sudo().create({
            'muter_id': self.alice.id,
            'muted_id': self.bob.id,
            'until': past,
        })
        self.assertFalse(self.Mute.is_muted(self.alice, self.bob))

    def test_cron_expire_mutes(self):
        past = fields.Datetime.now() - timedelta(minutes=1)
        self.Mute.sudo().create({
            'muter_id': self.alice.id, 'muted_id': self.bob.id, 'until': past,
        })
        removed = self.Mute.cron_expire_mutes()
        self.assertGreaterEqual(removed, 1)

    def test_cannot_mute_self(self):
        with self.assertRaises(ValidationError):
            self.Mute.with_user(self.alice).create({
                'muter_id': self.alice.id, 'muted_id': self.alice.id,
            })

    def test_unmute(self):
        self.Mute.with_user(self.alice).mute_user(self.bob)
        self.Mute.with_user(self.alice).unmute_user(self.bob)
        self.assertFalse(self.Mute.is_muted(self.alice, self.bob))

    # ── Panic mode ────────────────────────────────────────────────────────────

    def test_panic_hides_profile(self):
        self.alice_p.with_user(self.alice).action_panic()
        self.assertTrue(self.alice_p.panic_mode)
        self.assertEqual(self.alice_p.visibility, 'connections')
        self.assertTrue(self.alice_p.panic_activated_at)

    def test_panic_lift_restores_visibility(self):
        self.alice_p.write({'visibility': 'members'})
        self.alice_p.with_user(self.alice).action_panic()
        self.alice_p.with_user(self.alice).action_panic_lift()
        self.assertFalse(self.alice_p.panic_mode)
        self.assertEqual(self.alice_p.visibility, 'members')

    def test_panic_only_own_profile(self):
        with self.assertRaises(UserError):
            self.alice_p.with_user(self.bob).action_panic()

    def test_panic_blocks_non_connections_contact(self):
        self.alice_p.with_user(self.alice).action_panic()
        # Carol is not connected to Alice
        self.assertFalse(self.alice_p.is_safe_to_contact(self.carol))

    def test_panic_allows_existing_connection(self):
        self.alice_p.with_user(self.alice).action_panic()
        self.env['club_social_profile.connection'].sudo().create({
            'user_id': self.alice.id,
            'connected_user_id': self.carol.id,
            'state': 'accepted',
        })
        self.assertTrue(self.alice_p.is_safe_to_contact(self.carol))

    # ── Discovery integration ─────────────────────────────────────────────────

    def test_discovery_excludes_blocked(self):
        self.Block.with_user(self.alice).block_user(self.bob)
        crit = self.env['social_discovery.criteria'].create({
            'profile_id': self.alice_p.id,
            'name': 'Safety test',
        })
        profiles = crit._find_profiles()
        self.assertNotIn(self.bob_p, profiles)

    def test_discovery_excludes_panic_profiles(self):
        self.carol_p.with_user(self.carol).action_panic()
        crit = self.env['social_discovery.criteria'].create({
            'profile_id': self.alice_p.id,
            'name': 'Safety test 2',
        })
        profiles = crit._find_profiles()
        self.assertNotIn(self.carol_p, profiles)
        # Cleanup
        self.carol_p.with_user(self.carol).action_panic_lift()

    # ── Mute — extra cases ────────────────────────────────────────────────────

    def test_mute_idempotent(self):
        self.Mute.with_user(self.alice).mute_user(self.bob)
        self.Mute.with_user(self.alice).mute_user(self.bob)
        count = self.Mute.search_count([
            ('muter_id', '=', self.alice.id), ('muted_id', '=', self.bob.id),
        ])
        self.assertEqual(count, 1)

    def test_mute_update_until(self):
        future1 = fields.Datetime.now() + timedelta(hours=1)
        future2 = fields.Datetime.now() + timedelta(hours=48)
        self.Mute.with_user(self.alice).mute_user(self.bob, until=future1)
        self.Mute.with_user(self.alice).mute_user(self.bob, until=future2)
        rec = self.Mute.search([
            ('muter_id', '=', self.alice.id), ('muted_id', '=', self.bob.id),
        ], limit=1)
        self.assertEqual(rec.until, future2)

    def test_cron_keeps_permanent_mutes(self):
        self.Mute.with_user(self.alice).mute_user(self.carol)
        rec = self.Mute.search([
            ('muter_id', '=', self.alice.id), ('muted_id', '=', self.carol.id),
        ], limit=1)
        self.Mute.cron_expire_mutes()
        self.assertTrue(self.Mute.browse(rec.id).exists())

    def test_cron_keeps_future_mutes(self):
        future = fields.Datetime.now() + timedelta(hours=24)
        self.Mute.sudo().create({
            'muter_id': self.alice.id, 'muted_id': self.carol.id, 'until': future,
        })
        self.Mute.cron_expire_mutes()
        self.assertTrue(self.Mute.is_muted(self.alice, self.carol))

    def test_cron_returns_count(self):
        past = fields.Datetime.now() - timedelta(minutes=1)
        self.Mute.sudo().create({
            'muter_id': self.bob.id, 'muted_id': self.carol.id, 'until': past,
        })
        count = self.Mute.cron_expire_mutes()
        self.assertGreaterEqual(count, 1)

    # ── Panic — extra cases ───────────────────────────────────────────────────

    def test_panic_saves_previous_visibility(self):
        self.alice_p.write({'visibility': 'connections'})
        self.alice_p.with_user(self.alice).action_panic()
        self.assertEqual(self.alice_p.panic_saved_visibility, 'connections')
        self.alice_p.with_user(self.alice).action_panic_lift()

    # ── Profile helpers actions ───────────────────────────────────────────────

    def test_profile_action_block_unblock(self):
        self.alice_p.with_user(self.alice).action_block_user(self.bob)
        self.assertTrue(self.Block.is_blocked(self.alice, self.bob))
        self.alice_p.with_user(self.alice).action_unblock_user(self.bob)
        self.assertFalse(self.Block.is_blocked(self.alice, self.bob))

    def test_profile_action_block_wrong_owner_raises(self):
        with self.assertRaises(UserError):
            self.alice_p.with_user(self.bob).action_block_user(self.carol)

    def test_profile_action_mute_unmute(self):
        self.alice_p.with_user(self.alice).action_mute_user(self.carol)
        self.assertTrue(self.Mute.is_muted(self.alice, self.carol))
        self.alice_p.with_user(self.alice).action_unmute_user(self.carol)
        self.assertFalse(self.Mute.is_muted(self.alice, self.carol))

    def test_profile_action_mute_wrong_owner_raises(self):
        with self.assertRaises(UserError):
            self.alice_p.with_user(self.bob).action_mute_user(self.carol)
