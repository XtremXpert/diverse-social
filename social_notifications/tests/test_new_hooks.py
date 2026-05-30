from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


def _make_social_user(env, name, login, extra_groups=None):
    group_user = env.ref('base.group_user')
    group_social = env.ref('social_base.group_social_user')
    group_ids = [(4, group_user.id), (4, group_social.id)]
    for g in (extra_groups or []):
        group_ids.append((4, g.id))
    return env['res.users'].create({
        'name': name, 'login': login, 'email': f'{login}@hooks.test',
        'group_ids': group_ids,
    })


@tagged('social_notifications', 'gallery_hooks')
class TestGalleryHooks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_mod = cls.env.ref('social_base.group_social_moderator')
        cls.moderator = _make_social_user(cls.env, 'GalMod', 'gal_mod', [group_mod])
        cls.submitter = _make_social_user(cls.env, 'GalSub', 'gal_sub')
        cls.gallery = cls.env['social_gallery.gallery'].sudo().create({
            'name': 'Test Gallery Hooks',
            'owner_id': cls.moderator.id,
            'visibility': 'members',
            'is_shared': True,
        })
        cls.Notif = cls.env['club_social_profile.notification']

    def _notifs(self, user, notif_type):
        return self.Notif.search([('user_id', '=', user.id), ('type', '=', notif_type)])

    def test_approve_photo_notifies_submitter(self):
        photo = self.env['social_gallery.photo'].sudo().create({
            'gallery_id': self.gallery.id,
            'submitted_by_id': self.submitter.id,
            'state': 'pending',
        })
        before = len(self._notifs(self.submitter, 'gallery_photo_approved'))
        photo.with_user(self.moderator).action_approve()
        self.assertEqual(len(self._notifs(self.submitter, 'gallery_photo_approved')), before + 1)

    def test_reject_photo_notifies_submitter(self):
        photo = self.env['social_gallery.photo'].sudo().create({
            'gallery_id': self.gallery.id,
            'submitted_by_id': self.submitter.id,
            'state': 'pending',
        })
        before = len(self._notifs(self.submitter, 'gallery_photo_rejected'))
        photo.with_user(self.moderator).action_reject()
        self.assertEqual(len(self._notifs(self.submitter, 'gallery_photo_rejected')), before + 1)

    def test_approve_photo_without_submitter_no_notification(self):
        photo = self.env['social_gallery.photo'].sudo().create({
            'gallery_id': self.gallery.id,
            'submitted_by_id': False,
            'state': 'pending',
        })
        before = self.Notif.search_count([('type', '=', 'gallery_photo_approved')])
        photo.with_user(self.moderator).action_approve()
        after = self.Notif.search_count([('type', '=', 'gallery_photo_approved')])
        self.assertEqual(after, before)

    def test_moderator_not_notified_for_own_photo(self):
        photo = self.env['social_gallery.photo'].sudo().create({
            'gallery_id': self.gallery.id,
            'submitted_by_id': self.moderator.id,
            'state': 'pending',
        })
        before = len(self._notifs(self.moderator, 'gallery_photo_approved'))
        photo.with_user(self.moderator).action_approve()
        # _notify() ignore user_id == actor_id
        self.assertEqual(len(self._notifs(self.moderator, 'gallery_photo_approved')), before)


@tagged('social_notifications', 'reputation_hooks')
class TestReputationHooks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.sponsor = _make_social_user(cls.env, 'Sponsor', 'rep_sponsor')
        cls.newcomer = _make_social_user(cls.env, 'Newcomer', 'rep_newcomer')
        cls.Notif = cls.env['club_social_profile.notification']
        cls.Vouching = cls.env['social_reputation.vouching']

    def _notifs(self, user, notif_type):
        return self.Notif.search([('user_id', '=', user.id), ('type', '=', notif_type)])

    def test_vouch_for_notifies_newcomer(self):
        before = len(self._notifs(self.newcomer, 'vouching_received'))
        self.Vouching.with_user(self.sponsor).vouch_for(self.newcomer, statement='Great person')
        self.assertEqual(len(self._notifs(self.newcomer, 'vouching_received')), before + 1)

    def test_withdraw_notifies_newcomer(self):
        vouching = self.Vouching.with_user(self.sponsor).vouch_for(self.newcomer)
        before = len(self._notifs(self.newcomer, 'vouching_withdrawn'))
        vouching.with_user(self.sponsor).action_withdraw(reason='Changed my mind')
        self.assertEqual(len(self._notifs(self.newcomer, 'vouching_withdrawn')), before + 1)

    def test_vouch_for_self_raises(self):
        with self.assertRaises(Exception):
            self.Vouching.with_user(self.sponsor).vouch_for(self.sponsor)


@tagged('social_notifications', 'negotiation_hooks')
class TestNegotiationHooks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.initiator = _make_social_user(cls.env, 'Initiator', 'neg_init')
        cls.partner = _make_social_user(cls.env, 'Partner', 'neg_part')
        cls.Notif = cls.env['club_social_profile.notification']

    def _notifs(self, user, notif_type):
        return self.Notif.search([('user_id', '=', user.id), ('type', '=', notif_type)])

    def _make_negotiation(self):
        return self.env['social_negotiation.negotiation'].sudo().create({
            'initiator_id': self.initiator.id,
            'partner_id': self.partner.id,
        })

    def test_action_share_notifies_partner(self):
        neg = self._make_negotiation()
        before = len(self._notifs(self.partner, 'negotiation_shared'))
        neg.with_user(self.initiator).action_share()
        self.assertEqual(len(self._notifs(self.partner, 'negotiation_shared')), before + 1)

    def test_action_sign_first_notifies_other_party(self):
        neg = self._make_negotiation()
        neg.with_user(self.initiator).action_share()
        before = len(self._notifs(self.partner, 'negotiation_signed'))
        neg.with_user(self.initiator).action_sign()
        self.assertEqual(len(self._notifs(self.partner, 'negotiation_signed')), before + 1)

    def test_action_sign_both_sends_active_notifications(self):
        neg = self._make_negotiation()
        neg.with_user(self.initiator).action_share()
        neg.with_user(self.initiator).action_sign()
        before_init = len(self._notifs(self.initiator, 'negotiation_active'))
        before_part = len(self._notifs(self.partner, 'negotiation_active'))
        neg.with_user(self.partner).action_sign()
        self.assertTrue(neg.is_fully_signed)
        self.assertEqual(len(self._notifs(self.initiator, 'negotiation_active')), before_init + 1)
        self.assertEqual(len(self._notifs(self.partner, 'negotiation_active')), before_part + 1)

    def test_action_sign_both_no_negotiation_signed_notif(self):
        """When both have signed, only negotiation_active is sent, not negotiation_signed."""
        neg = self._make_negotiation()
        neg.with_user(self.initiator).action_share()
        neg.with_user(self.initiator).action_sign()
        before = len(self._notifs(self.initiator, 'negotiation_signed'))
        neg.with_user(self.partner).action_sign()
        # L'initiateur ne doit pas recevoir negotiation_signed lors de la 2e signature
        self.assertEqual(len(self._notifs(self.initiator, 'negotiation_signed')), before)


@tagged('social_notifications', 'circles_hooks')
class TestCirclesHooks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner = _make_social_user(cls.env, 'CircleOwner', 'circ_owner')
        cls.member = _make_social_user(cls.env, 'CircleMember', 'circ_member')
        cls.profile = cls.env['club_social_profile.profile'].sudo().create({
            'user_id': cls.owner.id,
        })
        cls.circle_type = cls.env['social_circles.circle_type'].sudo().create({
            'name': 'Test Type Hooks',
        })
        cls.circle = cls.env['social_circles.circle'].sudo().create({
            'profile_id': cls.profile.id,
            'name': 'Cercle Test',
            'type_id': cls.circle_type.id,
        })
        cls.Notif = cls.env['club_social_profile.notification']

    def _notifs(self, user, notif_type):
        return self.Notif.search([('user_id', '=', user.id), ('type', '=', notif_type)])

    def test_add_member_notifies_new_member(self):
        before = len(self._notifs(self.member, 'circle_added'))
        self.circle.with_user(self.owner).add_member(self.member)
        self.assertEqual(len(self._notifs(self.member, 'circle_added')), before + 1)

    def test_add_member_already_in_circle_no_duplicate(self):
        self.circle.with_user(self.owner).add_member(self.member)
        before = len(self._notifs(self.member, 'circle_added'))
        self.circle.with_user(self.owner).add_member(self.member)
        self.assertEqual(len(self._notifs(self.member, 'circle_added')), before)

    def test_owner_added_to_own_circle_no_notification(self):
        before = len(self._notifs(self.owner, 'circle_added'))
        self.circle.with_user(self.owner).add_member(self.owner)
        # _notify() ignore user_id == actor_id
        self.assertEqual(len(self._notifs(self.owner, 'circle_added')), before)
