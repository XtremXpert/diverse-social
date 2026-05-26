import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

# Délai par défaut avant qu'une invitation non utilisée expire.
INVITE_EXPIRY_DAYS = 7


class SocialVouching(models.Model):
    _name = 'social_reputation.vouching'
    _description = 'Community Vouching'
    _order = 'create_date desc'
    _inherit = ['mail.thread']

    sponsor_id = fields.Many2one(
        'res.users', string='Sponsor', required=True,
        default=lambda self: self.env.user,
        ondelete='restrict', index=True,
    )
    # newcomer_id optionnel : à la création d'une invitation, l'user n'existe pas
    # encore. Il est renseigné quand le destinataire complète l'inscription via
    # le lien tokenisé.
    newcomer_id = fields.Many2one(
        'res.users', string='Newcomer',
        ondelete='restrict', index=True,
    )
    statement = fields.Text(
        'Statement',
        help='Why are you vouching for this person? Visible to the newcomer and moderators.',
    )
    state = fields.Selection([
        ('invited', 'Invited (email sent)'),
        ('pending_payment', 'Pending Membership Payment'),
        ('active', 'Active'),
        ('withdrawn', 'Withdrawn'),
        ('expired', 'Invitation Expired'),
    ], default='active', required=True, tracking=True)

    # Champs pour le flow d'invitation par email
    invite_email = fields.Char(
        'Invitation Email',
        help='Email of the person being invited. Set when sponsor creates an '
             'invitation; cleared once the newcomer completes signup.',
        index=True,
    )
    invite_token = fields.Char(
        'Invitation Token', readonly=True, copy=False,
        help='Random token used in the invitation URL.',
    )
    invited_at = fields.Datetime('Invitation Sent', readonly=True)
    expires_at = fields.Datetime('Invitation Expires')

    create_date = fields.Datetime('Vouched On', readonly=True)
    withdrawn_at = fields.Datetime('Withdrawn On', readonly=True)
    withdrawn_reason = fields.Text('Withdrawal Reason')

    # On ne peut pas mettre une contrainte SQL UNIQUE(sponsor, newcomer) seule :
    # quand newcomer_id est NULL (pendant l'invitation), un sponsor peut avoir
    # plusieurs invitations vers des emails différents. On garde la contrainte
    # historique mais Postgres autorise plusieurs NULL — donc OK.
    _unique_vouching = models.Constraint(
        'UNIQUE(sponsor_id, newcomer_id)',
        'You have already vouched for this person.',
    )

    @api.constrains('sponsor_id', 'newcomer_id')
    def _check_not_self(self):
        for rec in self:
            if rec.newcomer_id and rec.sponsor_id == rec.newcomer_id:
                raise ValidationError(_('You cannot vouch for yourself.'))

    @api.constrains('sponsor_id', 'newcomer_id')
    def _check_no_circular(self):
        """Prevent A vouching B if B has already vouched A."""
        for rec in self:
            if not rec.newcomer_id:
                continue  # invitation sans newcomer encore : pas de cycle possible
            reverse = self.search([
                ('sponsor_id', '=', rec.newcomer_id.id),
                ('newcomer_id', '=', rec.sponsor_id.id),
                ('state', '=', 'active'),
            ], limit=1)
            if reverse:
                raise ValidationError(_(
                    '%(newcomer)s has already vouched for you. '
                    'Circular vouching is not allowed.',
                    newcomer=rec.newcomer_id.name,
                ))

    def action_withdraw(self, reason=None):
        self.ensure_one()
        if self.env.user != self.sponsor_id and \
                not self.env.user.has_group('social_base.group_social_moderator'):
            raise UserError(_('Only the sponsor or a moderator can withdraw a vouching.'))
        if self.state == 'withdrawn':
            raise UserError(_('This vouching is already withdrawn.'))
        if not reason and not self.withdrawn_reason:
            raise UserError(_('A reason is required to withdraw a vouching.'))
        rec = self.sudo() if self.env.user.has_group('social_base.group_social_moderator') else self
        newcomer = rec.newcomer_id  # captured avant write au cas où
        rec.write({
            'state': 'withdrawn',
            'withdrawn_at': fields.Datetime.now(),
            'withdrawn_reason': reason or self.withdrawn_reason,
        })
        # Chain of trust : si le newcomer n'a plus aucun vouching actif,
        # révoque son accès au réseau.
        if newcomer:
            self.sudo()._enforce_chain_of_trust(newcomer)

    @api.model
    def vouch_for(self, newcomer_user, statement=None):
        """Create an active vouching. Raises if already exists (active or withdrawn)."""
        existing = self.search([
            ('sponsor_id', '=', self.env.user.id),
            ('newcomer_id', '=', newcomer_user.id),
        ], limit=1)
        if existing and existing.state == 'active':
            raise UserError(_('You have already vouched for %(name)s.', name=newcomer_user.name))
        if existing and existing.state == 'withdrawn':
            raise UserError(_(
                'You previously withdrew your vouching for %(name)s. '
                'Contact a moderator to reinstate it.',
                name=newcomer_user.name,
            ))
        return self.create({
            'sponsor_id': self.env.user.id,
            'newcomer_id': newcomer_user.id,
            'statement': statement,
        })

    # ── Invitation flow ─────────────────────────────────────────────────────

    @api.model
    def action_invite_email(self, email, statement=None, sponsor=None):
        """Create a vouching invitation tied to an email address.

        Returns the new vouching record. Token + expiry are generated; the
        actual email send happens in a later step (mail.template).
        """
        email = (email or '').strip().lower()
        if not email or '@' not in email:
            raise UserError(_('A valid email address is required.'))
        sponsor = sponsor or self.env.user
        existing_user = self.env['res.users'].sudo().search(
            [('login', '=', email)], limit=1,
        )
        if existing_user:
            raise UserError(_(
                'A user with email %(email)s already exists. Use the regular '
                'vouching flow instead of an invitation.',
                email=email,
            ))
        # Refuser une invitation en doublon (même sponsor + email, non expirée)
        dup = self.search([
            ('sponsor_id', '=', sponsor.id),
            ('invite_email', '=', email),
            ('state', 'in', ['invited', 'pending_payment']),
        ], limit=1)
        if dup:
            raise UserError(_(
                'You already have a pending invitation for %(email)s '
                '(expires %(date)s).',
                email=email, date=dup.expires_at,
            ))
        token = secrets.token_urlsafe(32)
        return self.create({
            'sponsor_id': sponsor.id,
            'invite_email': email,
            'invite_token': token,
            'invited_at': fields.Datetime.now(),
            'expires_at': fields.Datetime.now() + timedelta(days=INVITE_EXPIRY_DAYS),
            'statement': statement,
            'state': 'invited',
        })

    @api.model
    def accept_invitation(self, token, new_user):
        """Called after a newcomer completes signup via the invitation link.

        Links the vouching to the freshly-created user and moves state to
        pending_payment (membership must be activated to gain social access).
        """
        if not token:
            raise UserError(_('Missing invitation token.'))
        vouching = self.sudo().search([
            ('invite_token', '=', token),
            ('state', 'in', ['invited', 'pending_payment']),
        ], limit=1)
        if not vouching:
            raise UserError(_('Invitation token unknown, used, or expired.'))
        if vouching.expires_at and vouching.expires_at < fields.Datetime.now():
            vouching.write({'state': 'expired'})
            raise UserError(_('This invitation has expired.'))
        vouching.write({
            'newcomer_id': new_user.id,
            'state': 'pending_payment',
            'invite_email': False,  # cleared once linked
            'invite_token': False,  # un-usable after acceptance
        })
        return vouching

    def action_activate_after_payment(self):
        """Called when the newcomer's first membership goes active.

        Moves a pending_payment vouching to active. No-op for other states.
        """
        for rec in self:
            if rec.state == 'pending_payment':
                rec.sudo().write({'state': 'active'})

    # ── Chain of trust ──────────────────────────────────────────────────────

    @api.model
    def has_active_vouching(self, user):
        """True if `user` has at least one active vouching (i.e. at least one
        sponsor still backing them). Admin / non-social-user are exempt:
        they don't need a vouching to keep their (non-social) access."""
        if not user or not user.has_group('social_base.group_social_user'):
            return True  # exempt: not a social user
        return bool(self.sudo().search([
            ('newcomer_id', '=', user.id),
            ('state', '=', 'active'),
        ], limit=1))

    @api.model
    def _enforce_chain_of_trust(self, user):
        """If `user` no longer has any active vouching, revoke their
        social_user group. Membership stays intact — they can re-enter once
        a new vouching is in place.
        """
        if not user:
            return
        # Exempt: admins (group_system) and any user without group_social_user.
        if user.has_group('base.group_system'):
            return
        if not user.has_group('social_base.group_social_user'):
            return
        if self.has_active_vouching(user):
            return
        group = self.env.ref('social_base.group_social_user', raise_if_not_found=False)
        if group:
            user.sudo().write({'group_ids': [(3, group.id)]})

    @api.model
    def _cron_expire_invitations(self):
        """Move stale invitations to 'expired' state. Run daily."""
        stale = self.sudo().search([
            ('state', 'in', ['invited']),
            ('expires_at', '<', fields.Datetime.now()),
        ])
        if stale:
            stale.write({'state': 'expired'})
