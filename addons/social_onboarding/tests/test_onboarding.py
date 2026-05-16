import datetime

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('social_onboarding', 'onboarding')
class TestSocialOnboarding(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        group_social = cls.env.ref('social_base.group_social_user')

        cls.user = cls.env['res.users'].create({
            'name': 'Onboarding User',
            'login': 'onb_user',
            'email': 'onb@test.test',
            'group_ids': [(4, group_social.id)],
        })
        cls.type_regular = cls.env.ref('club_membership.membership_type_regular')

    # ── Création du wizard ────────────────────────────────────────────────────

    def test_action_open_creates_wizard(self):
        """action_open crée un enregistrement wizard et retourne un acte d'ouverture."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'social_onboarding.wizard')
        self.assertIsNotNone(action['res_id'])

    def test_action_open_creates_profile(self):
        """action_open crée le profil si inexistant."""
        before = self.env['club_social_profile.profile'].search_count(
            [('user_id', '=', self.user.id)]
        )
        self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        after = self.env['club_social_profile.profile'].search_count(
            [('user_id', '=', self.user.id)]
        )
        self.assertEqual(after, before + 1)

    def test_action_open_reuses_existing_profile(self):
        """action_open ne crée pas de doublon si le profil existe déjà."""
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.user)
        self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        count = self.env['club_social_profile.profile'].search_count(
            [('user_id', '=', self.user.id)]
        )
        self.assertEqual(count, 1)

    def test_wizard_starts_at_welcome_step(self):
        """L'assistant démarre à l'étape 'welcome' pour un profil non complété."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.step, 'welcome')

    # ── Navigation ────────────────────────────────────────────────────────────

    def test_action_next_advances_step(self):
        """action_next passe à l'étape suivante."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.step, 'welcome')
        wizard.action_next()
        self.assertEqual(wizard.step, 'about')

    def test_action_next_all_steps(self):
        """action_next parcourt toutes les étapes dans l'ordre."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        expected = ['welcome', 'about', 'preferences', 'done']
        for i, step in enumerate(expected):
            self.assertEqual(wizard.step, step)
            if i < len(expected) - 1:
                wizard.action_next()

    def test_action_previous_goes_back(self):
        """action_previous revient à l'étape précédente."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.action_next()  # welcome → about
        wizard.action_next()  # about → preferences
        self.assertEqual(wizard.step, 'preferences')
        wizard.action_previous()
        self.assertEqual(wizard.step, 'about')

    def test_action_previous_does_not_go_before_welcome(self):
        """action_previous ne va pas en dessous de l'étape 'welcome'."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.step, 'welcome')
        wizard.action_previous()
        self.assertEqual(wizard.step, 'welcome')

    def test_action_next_returns_act_window(self):
        """action_next retourne un act_window vers le même wizard."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        result = wizard.action_next()
        self.assertEqual(result['type'], 'ir.actions.act_window')
        self.assertEqual(result['res_id'], wizard.id)

    # ── Sauvegarde et profil ──────────────────────────────────────────────────

    def test_next_saves_photo_to_profile(self):
        """action_next sauvegarde l'image vers le profil."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        # Simuler l'upload d'une image (1x1 pixel PNG en base64)
        fake_image = b'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='
        wizard.write({'profile_image': fake_image})
        wizard.action_next()
        self.assertIsNotNone(wizard.profile_id.profile_image)

    def test_finish_saves_all_fields(self):
        """action_finish sauvegarde tous les champs du profil."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.write({
            'pronouns': 'iel/iel',
            'bio': 'Biographie test',
            'birth_year': 1990,
            'city': 'Montréal',
            'visibility': 'connections',
            'availability': 'disponible',
            'digest_email_enabled': False,
        })
        # Avancer jusqu'à l'étape preferences pour pouvoir terminer
        wizard.step = 'preferences'
        wizard.action_finish()
        profile = wizard.profile_id
        self.assertEqual(profile.pronouns, 'iel/iel')
        self.assertEqual(profile.bio, 'Biographie test')
        self.assertEqual(profile.birth_year, 1990)
        self.assertEqual(profile.city, 'Montréal')
        self.assertEqual(profile.visibility, 'connections')
        self.assertEqual(profile.availability, 'disponible')
        self.assertFalse(profile.digest_email_enabled)

    def test_finish_marks_onboarding_done(self):
        """action_finish passe onboarding_done à True."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertFalse(wizard.profile_id.onboarding_done)
        wizard.step = 'preferences'
        wizard.action_finish()
        self.assertTrue(wizard.profile_id.onboarding_done)

    def test_skip_does_not_mark_done(self):
        """action_skip laisse onboarding_done à False."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.action_skip()
        self.assertFalse(wizard.profile_id.onboarding_done)

    # ── Validation ────────────────────────────────────────────────────────────

    def test_underage_birth_year_blocked(self):
        """Une année de naissance donnant moins de 18 ans est rejetée à l'étape 'about'."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        current_year = datetime.date.today().year
        wizard.write({
            'step': 'about',
            'birth_year': current_year - 15,
        })
        with self.assertRaises(ValidationError):
            wizard.action_next()

    def test_valid_adult_birth_year_passes(self):
        """Une année de naissance d'un adulte (18+) passe la validation."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        current_year = datetime.date.today().year
        wizard.write({
            'step': 'about',
            'birth_year': current_year - 25,
        })
        wizard.action_next()  # Ne doit pas lever d'exception
        self.assertEqual(wizard.step, 'preferences')

    def test_zero_birth_year_skips_validation(self):
        """Un birth_year à 0 (non saisi) ne déclenche pas la validation d'âge."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.write({'step': 'about', 'birth_year': 0})
        wizard.action_next()
        self.assertEqual(wizard.step, 'preferences')

    # ── Hook d'adhésion ───────────────────────────────────────────────────────

    def test_membership_activate_creates_profile(self):
        """L'activation d'une adhésion crée automatiquement le profil du membre."""
        user2 = self.env['res.users'].create({
            'name': 'Hook Test User',
            'login': 'hook_test_onb',
            'email': 'hook@onb.test',
        })
        membership = self.env['club_membership.membership'].sudo().create({
            'partner_id': user2.partner_id.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'pending',
        })
        membership.action_activate()
        profile = self.env['club_social_profile.profile'].search(
            [('user_id', '=', user2.id)]
        )
        self.assertEqual(len(profile), 1)
        self.assertFalse(profile.onboarding_done)

    def test_membership_activate_no_profile_if_no_user(self):
        """L'activation sans user associé ne crée pas de profil orphelin."""
        partner = self.env['res.partner'].create({'name': 'Partenaire sans compte'})
        membership = self.env['club_membership.membership'].sudo().create({
            'partner_id': partner.id,
            'membership_type_id': self.type_regular.id,
            'start_date': datetime.date.today(),
            'state': 'pending',
        })
        membership.action_activate()
        count = self.env['club_social_profile.profile'].search_count([
            ('partner_id', '=', partner.id),
        ])
        self.assertEqual(count, 0)

    # ── Méthode profile_ext ───────────────────────────────────────────────────

    def test_profile_action_open_onboarding(self):
        """La méthode action_open_onboarding sur le profil ouvre l'assistant."""
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.user)
        action = profile.with_user(self.user).action_open_onboarding()
        self.assertEqual(action['type'], 'ir.actions.act_window')
        self.assertEqual(action['res_model'], 'social_onboarding.wizard')

    def test_action_open_loads_profile_data(self):
        """action_open pré-remplit le wizard avec les données existantes du profil."""
        profile = self.env['club_social_profile.profile'].sudo().get_or_create_for_user(self.user)
        profile.sudo().write({'bio': 'Bio existante', 'city': 'Québec', 'birth_year': 1985})
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        self.assertEqual(wizard.bio, 'Bio existante')
        self.assertEqual(wizard.city, 'Québec')
        self.assertEqual(wizard.birth_year, 1985)

    def test_skip_saves_to_profile(self):
        """action_skip sauvegarde les champs remplis vers le profil."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.write({'bio': 'Bio via skip', 'city': 'Laval'})
        wizard.action_skip()
        profile = wizard.profile_id
        self.assertEqual(profile.bio, 'Bio via skip')
        self.assertEqual(profile.city, 'Laval')

    def test_action_next_at_done_stays_done(self):
        """action_next à l'étape 'done' ne dépasse pas 'done'."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.step = 'done'
        wizard.action_next()
        self.assertEqual(wizard.step, 'done')

    def test_finish_returns_client_action(self):
        """action_finish retourne une action client (notification)."""
        action = self.env['social_onboarding.wizard'].with_user(self.user).action_open()
        wizard = self.env['social_onboarding.wizard'].browse(action['res_id'])
        wizard.step = 'preferences'
        result = wizard.action_finish()
        self.assertEqual(result['type'], 'ir.actions.client')
        self.assertEqual(result['tag'], 'display_notification')
