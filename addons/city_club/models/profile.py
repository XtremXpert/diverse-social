import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_PARAM_ALLOWED_POSTAL_CODES = 'city_club.allowed_postal_codes'
_PARAM_ALLOWED_POSTAL_PREFIX = 'city_club.allowed_postal_prefix'
_PARAM_CITY_NAME = 'city_club.city_name'


def _normalize_postal(code):
    """Normalize a Canadian postal code: strip, uppercase, collapse spaces."""
    if not code:
        return ''
    return re.sub(r'\s+', ' ', code.strip().upper())


class ClubSocialProfile(models.Model):
    _inherit = 'club_social_profile.profile'

    residency_postal_code = fields.Char(
        string='Postal code',
        size=10,
        help='Used to confirm the member resides in the community.',
    )
    residency_state = fields.Selection([
        ('none', 'Not submitted'),
        ('pending', 'Pending review'),
        ('verified', 'Verified resident'),
        ('rejected', 'Rejected'),
    ], default='none', required=True, index=True)
    residency_submitted_at = fields.Datetime(readonly=True)
    residency_verified_at = fields.Datetime(readonly=True)
    residency_verified_by_id = fields.Many2one(
        'res.users', string='Verified by', readonly=True, ondelete='set null',
    )
    residency_notes = fields.Text(
        string='Residency notes',
        help='Free-form notes from the member or the moderator (proof of '
             'residence, justifications, special cases).',
    )

    # ── Submission ────────────────────────────────────────────────────────────

    def action_submit_residency(self, postal_code=None, notes=None):
        """Member submits a postal code for residency verification.

        Idempotent: calling on a pending or verified profile is a no-op
        (except for `notes` updates).
        """
        self.ensure_one()
        if postal_code is not None:
            self.residency_postal_code = _normalize_postal(postal_code)
        if notes is not None:
            self.residency_notes = notes
        if not self.residency_postal_code:
            raise UserError(_("A postal code is required."))
        if not self._is_allowed_postal_code(self.residency_postal_code):
            raise UserError(_(
                "Postal code %(code)s is not in the area served by %(city)s.",
                code=self.residency_postal_code,
                city=self._get_city_name() or _("this community"),
            ))
        if self.residency_state in ('verified', 'pending'):
            return
        self.write({
            'residency_state': 'pending',
            'residency_submitted_at': fields.Datetime.now(),
        })
        self._notify_moderators_residency_pending()

    def _notify_moderators_residency_pending(self):
        """In-app ping to every active moderator that a residency awaits review."""
        self.ensure_one()
        moderator_group = self.env.ref('social_base.group_social_moderator')
        moderators = self.env['res.users'].sudo().search([
            ('group_ids', 'in', moderator_group.id),
            ('active', '=', True),
        ])
        if not moderators:
            return
        Notification = self.env['club_social_profile.notification'].sudo()
        body = _(
            "%(name)s submitted residency for review (postal %(code)s)",
            name=self.user_id.name or self.login,
            code=self.residency_postal_code,
        )
        url = (
            f'/odoo/action-city_club.action_residency_pending/{self.id}'
        )
        for moderator in moderators:
            Notification._notify(
                user_id=moderator.id,
                actor_id=self.user_id.id,
                notif_type='residency_pending',
                body=body,
                url=url,
                ref_model='club_social_profile.profile',
                ref_id=self.id,
            )

    # ── Moderator actions ─────────────────────────────────────────────────────

    def action_verify_residency(self):
        """Approve residency and grant social-network access via membership.

        Activates a ``club_membership.membership`` of the configured default
        resident type, which in turn grants ``social_base.group_social_user``
        through the standard ``_sync_social_access()`` workflow.
        """
        # sudo() : moderators don't have create/write rights on club_membership.
        # Granting the social_user group is the explicit point of this action,
        # so privilege escalation here is the intended behavior.
        Membership = self.env['club_membership.membership'].sudo()
        Type = self.env['club_membership.type'].sudo()
        resident_type = Type.search(
            [('is_resident_default', '=', True), ('active', '=', True)],
            limit=1,
        )
        if not resident_type:
            raise UserError(_(
                "No default resident membership type is configured. "
                "Set `is_resident_default` on a club_membership.type record."
            ))
        now = fields.Datetime.now()
        for profile in self:
            if not profile.user_id:
                raise UserError(_("Profile %s has no user.") % profile.display_name)
            if profile.residency_state == 'verified':
                continue
            existing = Membership.search([
                ('partner_id', '=', profile.partner_id.id),
                ('state', '=', 'active'),
            ], limit=1)
            if not existing:
                membership = Membership.create({
                    'partner_id': profile.partner_id.id,
                    'membership_type_id': resident_type.id,
                    'start_date': fields.Date.today(),
                })
                membership.action_activate()
            profile.write({
                'residency_state': 'verified',
                'residency_verified_at': now,
                'residency_verified_by_id': self.env.user.id,
            })

    def action_reject_residency(self):
        for profile in self:
            profile.write({
                'residency_state': 'rejected',
                'residency_verified_at': fields.Datetime.now(),
                'residency_verified_by_id': self.env.user.id,
            })

    def action_reset_residency(self):
        """Allow a member to re-submit after rejection."""
        for profile in self:
            profile.write({
                'residency_state': 'none',
                'residency_submitted_at': False,
                'residency_verified_at': False,
                'residency_verified_by_id': False,
            })

    # ── Validation ────────────────────────────────────────────────────────────

    @api.constrains('residency_postal_code')
    def _check_postal_code_format(self):
        for profile in self:
            code = profile.residency_postal_code
            if not code:
                continue
            if not re.fullmatch(r'[A-Z]\d[A-Z] ?\d[A-Z]\d', _normalize_postal(code)):
                raise ValidationError(_(
                    "Postal code %s is not a valid Canadian format (A1A 1A1)."
                ) % code)

    # ── Helpers (city_club configuration) ─────────────────────────────────────

    @api.model
    def _is_allowed_postal_code(self, code):
        """Return True if ``code`` matches the configured allow-list.

        Two configuration knobs (both via ``ir.config_parameter``):

        - ``city_club.allowed_postal_codes`` — comma-separated full codes
          (matched exactly after normalization)
        - ``city_club.allowed_postal_prefix`` — comma-separated prefixes
          (matched against the leading characters; e.g. ``G0S`` matches
          ``G0S 2S0`` and ``G0S 1A1``)

        If neither is configured, returns True (no filtering — moderator
        decides manually).
        """
        code = _normalize_postal(code)
        if not code:
            return False
        Param = self.env['ir.config_parameter'].sudo()
        allow_full = (Param.get_param(_PARAM_ALLOWED_POSTAL_CODES) or '').strip()
        allow_prefix = (Param.get_param(_PARAM_ALLOWED_POSTAL_PREFIX) or '').strip()
        if not allow_full and not allow_prefix:
            return True
        if allow_full:
            allowed = {_normalize_postal(c) for c in allow_full.split(',') if c.strip()}
            if code in allowed:
                return True
        if allow_prefix:
            prefixes = [p.strip().upper() for p in allow_prefix.split(',') if p.strip()]
            if any(code.startswith(p) for p in prefixes):
                return True
        return False

    @api.model
    def _get_city_name(self):
        return self.env['ir.config_parameter'].sudo().get_param(
            _PARAM_CITY_NAME, default='',
        )
