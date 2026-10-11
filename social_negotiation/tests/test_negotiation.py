from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError, UserError


@tagged('social_negotiation', 'negotiation')
class TestNegotiation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_user = cls.env.ref('base.group_user')
        group_social = cls.env.ref('social_base.group_social_user')

        def make_user(name, login):
            return cls.env['res.users'].create({
                'name': name, 'login': login, 'email': f'{login}@neg.test',
                'group_ids': [(4, group_user.id), (4, group_social.id)],
            })

        cls.alice = make_user('Alice', 'neg_alice')
        cls.bob = make_user('Bob', 'neg_bob')
        cls.carol = make_user('Carol', 'neg_carol')

        cls.Neg = cls.env['social_negotiation.negotiation']
        cls.Item = cls.env['social_negotiation.item']

    def _make_neg(self, initiator=None, partner=None):
        initiator = initiator or self.alice
        partner = partner or self.bob
        return self.Neg.with_user(initiator).create({
            'initiator_id': initiator.id,
            'partner_id': partner.id,
        })

    def _with_items(self, neg):
        self.Item.with_user(self.alice).create([
            {'negotiation_id': neg.id, 'category': 'desire', 'text': 'Item A'},
            {'negotiation_id': neg.id, 'category': 'hard_limit', 'text': 'Item B'},
        ])
        return neg

    # ── Creation ─────────────────────────────────────────────────────────────

    def test_create_negotiation(self):
        neg = self._make_neg()
        self.assertEqual(neg.state, 'draft')
        self.assertEqual(neg.version, 1)

    def test_cannot_create_self_negotiation(self):
        with self.assertRaises(ValidationError):
            self.Neg.with_user(self.alice).create({
                'initiator_id': self.alice.id,
                'partner_id': self.alice.id,
            })

    # ── Workflow ──────────────────────────────────────────────────────────────

    def test_share(self):
        neg = self._make_neg()
        neg.with_user(self.alice).action_share()
        self.assertEqual(neg.state, 'shared')

    def test_share_only_from_draft(self):
        neg = self._make_neg()
        neg.action_share()
        with self.assertRaises(UserError):
            neg.action_share()

    def test_outsider_cannot_share(self):
        neg = self._make_neg()
        with self.assertRaises(UserError):
            neg.with_user(self.carol).action_share()

    def test_start_review(self):
        neg = self._make_neg()
        neg.action_share()
        neg.with_user(self.bob).action_start_review()
        self.assertEqual(neg.state, 'reviewing')

    def test_start_review_only_from_shared(self):
        neg = self._make_neg()
        with self.assertRaises(UserError):
            neg.with_user(self.bob).action_start_review()

    # ── Signing ───────────────────────────────────────────────────────────────

    def test_both_sign_activates(self):
        neg = self._make_neg()
        neg.action_share()
        neg.with_user(self.bob).action_start_review()
        neg.with_user(self.alice).action_sign()
        self.assertIsNotNone(neg.initiator_signed_at)
        self.assertFalse(neg.is_fully_signed)
        neg.with_user(self.bob).action_sign()
        self.assertTrue(neg.is_fully_signed)
        self.assertEqual(neg.state, 'active')

    def test_cannot_sign_twice(self):
        neg = self._make_neg()
        neg.action_share()
        neg.with_user(self.alice).action_sign()
        with self.assertRaises(UserError):
            neg.with_user(self.alice).action_sign()

    def test_outsider_cannot_sign(self):
        neg = self._make_neg()
        neg.action_share()
        with self.assertRaises(UserError):
            neg.with_user(self.carol).action_sign()

    def test_cannot_sign_from_draft(self):
        neg = self._make_neg()
        with self.assertRaises(UserError):
            neg.with_user(self.alice).action_sign()

    # ── Archive ───────────────────────────────────────────────────────────────

    def test_archive(self):
        neg = self._make_neg()
        neg.action_share()
        neg.with_user(self.bob).action_sign()
        neg.with_user(self.alice).action_sign()
        neg.with_user(self.alice).action_archive()
        self.assertEqual(neg.state, 'archived')
        self.assertIsNotNone(neg.archived_at)

    # ── New version ───────────────────────────────────────────────────────────

    def test_new_version(self):
        neg = self._make_neg()
        self._with_items(neg)
        neg.action_share()
        neg.with_user(self.alice).action_sign()
        neg.with_user(self.bob).action_sign()

        result = neg.with_user(self.alice).action_new_version()
        new_id = result['res_id']
        new_neg = self.Neg.browse(new_id)

        self.assertEqual(new_neg.version, 2)
        self.assertEqual(new_neg.state, 'draft')
        self.assertFalse(new_neg.initiator_signed_at)
        self.assertEqual(len(new_neg.item_ids), 2)
        neg.invalidate_recordset()
        self.assertEqual(neg.state, 'archived')

    # ── Items ─────────────────────────────────────────────────────────────────

    def test_item_count(self):
        neg = self._make_neg()
        self._with_items(neg)
        self.assertEqual(neg.item_count, 2)

    def test_is_compatible(self):
        neg = self._make_neg()
        item = self.Item.create({
            'negotiation_id': neg.id,
            'category': 'desire',
            'text': 'Test',
            'initiator_response': 'oui',
            'partner_response': 'soft',
        })
        self.assertTrue(item.is_compatible)

    def test_not_compatible(self):
        neg = self._make_neg()
        item = self.Item.create({
            'negotiation_id': neg.id,
            'category': 'hard_limit',
            'text': 'Hard stop',
            'initiator_response': 'oui',
            'partner_response': 'non',
        })
        self.assertFalse(item.is_compatible)

    # ── Agreement score ───────────────────────────────────────────────────────

    def test_agreement_score_all_compatible(self):
        neg = self._make_neg()
        self.Item.create([
            {'negotiation_id': neg.id, 'category': 'desire', 'text': 'A',
             'initiator_response': 'oui', 'partner_response': 'oui'},
            {'negotiation_id': neg.id, 'category': 'desire', 'text': 'B',
             'initiator_response': 'soft', 'partner_response': 'oui'},
        ])
        self.assertEqual(neg.agreement_score, 100)

    def test_agreement_score_partial(self):
        neg = self._make_neg()
        self.Item.create([
            {'negotiation_id': neg.id, 'category': 'desire', 'text': 'A',
             'initiator_response': 'oui', 'partner_response': 'oui'},
            {'negotiation_id': neg.id, 'category': 'hard_limit', 'text': 'B',
             'initiator_response': 'oui', 'partner_response': 'non'},
        ])
        self.assertEqual(neg.agreement_score, 50)

    def test_agreement_score_no_responses(self):
        neg = self._make_neg()
        self.Item.create({
            'negotiation_id': neg.id, 'category': 'desire', 'text': 'A',
        })
        self.assertEqual(neg.agreement_score, 0)

    # ── Privacy ───────────────────────────────────────────────────────────────

    def test_outsider_cannot_see_negotiation(self):
        neg = self._make_neg()
        result = self.Neg.with_user(self.carol).search([('id', '=', neg.id)])
        self.assertFalse(result)

    # ── safe_word ─────────────────────────────────────────────────────────────

    def test_safe_word_stored(self):
        neg = self.Neg.with_user(self.alice).create({
            'initiator_id': self.alice.id,
            'partner_id': self.bob.id,
            'safe_word': 'Ananas',
        })
        self.assertEqual(neg.safe_word, 'Ananas')

    def test_safe_word_optional(self):
        neg = self._make_neg()
        self.assertFalse(neg.safe_word)

    # ── Réponse NA ────────────────────────────────────────────────────────────

    def test_na_response_not_compatible(self):
        """Une réponse 'na' n'est pas comptée comme compatible."""
        neg = self._make_neg()
        item = self.Item.create({
            'negotiation_id': neg.id, 'category': 'desire', 'text': 'NA test',
            'initiator_response': 'oui', 'partner_response': 'na',
        })
        self.assertFalse(item.is_compatible)

    def test_agreement_score_na_not_counted(self):
        """Les items avec 'na' sont comptés comme non-compatibles dans le score."""
        neg = self._make_neg()
        self.Item.create({
            'negotiation_id': neg.id, 'category': 'desire', 'text': 'NA',
            'initiator_response': 'oui', 'partner_response': 'na',
        })
        self.assertEqual(neg.agreement_score, 0)

    def test_agreement_score_all_na(self):
        """Deux items avec réponses incompatibles (na) → 0%."""
        neg = self._make_neg()
        self.Item.create([
            {'negotiation_id': neg.id, 'category': 'desire', 'text': 'A',
             'initiator_response': 'na', 'partner_response': 'oui'},
            {'negotiation_id': neg.id, 'category': 'desire', 'text': 'B',
             'initiator_response': 'oui', 'partner_response': 'na'},
        ])
        self.assertEqual(neg.agreement_score, 0)

    # ── Signature depuis shared ───────────────────────────────────────────────

    def test_sign_from_shared_state(self):
        """On peut signer directement depuis l'état 'shared'."""
        neg = self._make_neg()
        neg.action_share()
        neg.with_user(self.alice).action_sign()
        self.assertTrue(neg.initiator_signed_at)

    def test_both_sign_from_shared_activates(self):
        neg = self._make_neg()
        neg.action_share()
        neg.with_user(self.alice).action_sign()
        neg.with_user(self.bob).action_sign()
        self.assertEqual(neg.state, 'active')

    # ── Modérateur bypass ─────────────────────────────────────────────────────

    def test_moderator_can_archive_any(self):
        """Un modérateur peut archiver une négociation dont il n'est pas participant."""
        group_mod = self.env.ref('social_base.group_social_moderator')
        moderator = self.env['res.users'].create({
            'name': 'Neg Mod', 'login': 'neg_modo', 'email': 'neg_modo@neg.test',
            'group_ids': [
                (4, self.env.ref('base.group_user').id),
                (4, self.env.ref('social_base.group_social_user').id),
                (4, group_mod.id),
            ],
        })
        neg = self._make_neg()
        neg.with_user(moderator).action_archive()
        self.assertEqual(neg.state, 'archived')

    def test_outsider_cannot_archive(self):
        """Un utilisateur non-participant ne peut pas archiver."""
        neg = self._make_neg()
        with self.assertRaises(UserError):
            neg.with_user(self.carol).action_archive()

    # ── Catégories d'item ─────────────────────────────────────────────────────

    def test_all_item_categories_accepted(self):
        """Chaque valeur de category est acceptée."""
        neg = self._make_neg()
        categories = ['hard_limit', 'soft_limit', 'desire', 'safeguard', 'other']
        for cat in categories:
            item = self.Item.create({
                'negotiation_id': neg.id,
                'category': cat,
                'text': f'Item {cat}',
            })
            self.assertEqual(item.category, cat)

    def test_partner_can_archive(self):
        """Le partenaire peut aussi archiver."""
        neg = self._make_neg()
        neg.action_share()
        neg.with_user(self.bob).action_archive()
        self.assertEqual(neg.state, 'archived')

    def test_item_note_stored(self):
        neg = self._make_neg()
        item = self.Item.create({
            'negotiation_id': neg.id,
            'category': 'desire',
            'text': 'Avec note',
            'note': 'Note partagée',
        })
        self.assertEqual(item.note, 'Note partagée')
