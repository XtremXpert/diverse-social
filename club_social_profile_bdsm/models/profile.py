from odoo import fields, models, api


class ClubSocialProfileBdsm(models.Model):
    """Extends club_social_profile.profile with BDSM fields and the compatibility engine."""
    _inherit = 'club_social_profile.profile'

    bdsm_role = fields.Selection([
        ('dominant', 'Dominant'),
        ('soumis', 'Submissive'),
        ('switch', 'Switch'),
        ('maitre', 'Master / Mistress'),
        ('esclave', 'Slave'),
        ('sadique', 'Sadist'),
        ('masochiste', 'Masochist'),
        ('curieux', 'Curious (beginner)'),
        ('spectateur', 'Spectator'),
        ('autre', 'Other'),
    ], string='BDSM Role')

    experience = fields.Selection([
        ('nouveau', 'New (< 1 year)'),
        ('intermediate', 'Intermediate (1–5 years)'),
        ('experimente', 'Experienced (5+ years)'),
    ], string='Experience')

    soft_limits = fields.Text(string='Soft Limits', help='What you do with prior negotiation')
    hard_limits = fields.Text(string='Hard Limits', help='What you never do')

    fetlife_url = fields.Char("Profil FetLife", help="Lien vers le profil FetLife vérifié du membre.")
    kink_level_ids = fields.One2many(
        'club_social_profile_bdsm.kink_level', 'profile_id', string='Kink Interests',
    )

    # ── Compatibility ─────────────────────────────────────────────────────────
    _ROLE_COMPAT = {
        frozenset(['dominant', 'soumis']): 100,
        frozenset(['dominant', 'esclave']): 100,
        frozenset(['dominant', 'masochiste']): 80,
        frozenset(['maitre', 'esclave']): 100,
        frozenset(['maitre', 'soumis']): 90,
        frozenset(['sadique', 'masochiste']): 100,
        frozenset(['switch']): 70,
    }

    def _role_compat_score(self, role_a, role_b):
        if not role_a or not role_b:
            return 50
        if role_a == role_b:
            return 70 if role_a == 'switch' else 30
        pair = frozenset([role_a, role_b])
        for key, score in self._ROLE_COMPAT.items():
            if key <= pair or (len(key) == 1 and (role_a in key or role_b in key)):
                return score
        return 40

    def compute_compatibility(self, other):
        """Return a dict {score, shared_kinks, role_score, kink_score}."""
        self.ensure_one()
        my_kinks = set(self.kink_level_ids.mapped('kink_id').ids)
        their_kinks = set(other.kink_level_ids.mapped('kink_id').ids)
        shared = my_kinks & their_kinks
        denom = max(len(my_kinks), len(their_kinks), 1)
        kink_score = round(len(shared) / denom * 100) if (my_kinks or their_kinks) else 50
        role_score = self._role_compat_score(self.bdsm_role, other.bdsm_role)
        total = round(kink_score * 0.65 + role_score * 0.35)
        shared_names = self.env['club_social_profile_bdsm.kink'].browse(list(shared)).mapped('name')
        return {
            'score': total,
            'kink_score': kink_score,
            'role_score': role_score,
            'shared_kinks': shared_names,
            'shared_count': len(shared),
        }
