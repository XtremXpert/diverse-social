from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ClubMembership(models.Model):
    _name = 'club_membership.membership'
    _description = 'Club Membership'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'
    _rec_name = 'display_name'

    partner_id = fields.Many2one(
        'res.partner', 'Member', required=True, index=True, ondelete='cascade',
    )
    user_id = fields.Many2one(
        'res.users', 'User', compute='_compute_user_id', store=True,
    )
    membership_type_id = fields.Many2one(
        'club_membership.type', 'Type', required=True, ondelete='restrict',
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, index=True, tracking=True)

    start_date = fields.Date('Start', required=True, default=fields.Date.today)
    end_date = fields.Date('End')
    fee_paid = fields.Monetary('Fee paid', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )
    invoice_id = fields.Many2one(
        'account.move', 'Invoice', domain=[('move_type', '=', 'out_invoice')],
        ondelete='set null',
    )
    notes = fields.Text('Internal notes')

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('partner_id', 'membership_type_id', 'start_date')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"{rec.partner_id.name or ''} — "
                f"{rec.membership_type_id.name or ''} "
                f"({rec.start_date or ''})"
            )

    @api.depends('partner_id')
    def _compute_user_id(self):
        for rec in self:
            user = self.env['res.users'].search(
                [('partner_id', '=', rec.partner_id.id), ('active', 'in', [True, False])],
                limit=1,
            )
            rec.user_id = user

    # ── State transitions ────────────────────────────────────────────────────

    def action_activate(self):
        for rec in self:
            if rec.state not in ('pending', 'suspended'):
                raise UserError(
                    _("Cannot activate a membership in state \"%s\".", rec._get_state_label())
                )
            if not rec.end_date and rec.membership_type_id.duration_months:
                rec.end_date = rec.start_date + relativedelta(
                    months=rec.membership_type_id.duration_months
                )
            rec.write({'state': 'active'})
            rec._sync_social_access(grant=True)

    def action_suspend(self):
        for rec in self:
            if rec.state != 'active':
                raise UserError(
                    _("Cannot suspend a membership in state \"%s\".", rec._get_state_label())
                )
            rec.write({'state': 'suspended'})
            rec._sync_social_access(grant=False)

    def action_cancel(self):
        for rec in self:
            if rec.state == 'cancelled':
                continue
            rec.write({'state': 'cancelled'})
            rec._sync_social_access(grant=False)

    def action_renew(self):
        """Create a new membership picking up from this one."""
        self.ensure_one()
        start = (self.end_date or fields.Date.today()) + relativedelta(days=1)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'club_membership.membership',
            'view_mode': 'form',
            'views': [(False, 'form')],  # requis par Odoo 20
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_membership_type_id': self.membership_type_id.id,
                'default_start_date': str(start),
                'default_fee_paid': self.membership_type_id.fee,
            },
        }

    # ── Social network access ────────────────────────────────────────────────

    # Groups that mark a user as deliberately "internal" (admin or
    # moderator). Members in these groups must stay internal — never
    # downgrade them to portal on activation.
    _BACKEND_ROLE_XML_IDS = (
        'base.group_system',
        'base.group_erp_manager',
        'social_base.group_social_moderator',
        'social_base.group_social_admin',
    )

    def _convert_to_portal_if_eligible(self, user):
        """Downgrade `user` from internal to portal when nothing else
        requires backend access.

        The default `res.users.create()` adds `base.group_user` (internal,
        backend-enabled). For social-network members that costs an
        Enterprise license seat and exposes /odoo unnecessarily. Once a
        membership becomes active, swap that for `base.group_portal`
        unless the user holds a role that *needs* the backend.

        Idempotent: skips when the user is already portal or never was
        internal.
        """
        if not user:
            return
        for xml_id in self._BACKEND_ROLE_XML_IDS:
            if user.has_group(xml_id):
                return
        internal = self.env.ref('base.group_user', raise_if_not_found=False)
        portal = self.env.ref('base.group_portal', raise_if_not_found=False)
        if not (internal and portal):
            return
        if portal in user.group_ids:
            return  # déjà portal, rien à faire
        if internal not in user.group_ids:
            return  # ni internal ni portal (public ?) — on ne touche pas
        # Odoo 20 refuse internal + portal : retirer aussi chaque groupe qui
        # implique internal (groupes par défaut d'un utilisateur créé).
        internal_groups = user.group_ids.filtered(lambda g: internal in g.all_implied_ids)
        user.sudo().write({
            'group_ids': [(3, g.id) for g in internal_groups] + [(4, portal.id)],
        })

    def _sync_social_access(self, grant):
        """Grant or revoke group_social_user based on the membership state.

        On grant, also downgrade the user from internal to portal when
        eligible (see `_convert_to_portal_if_eligible`).
        """
        group = self.env.ref('social_base.group_social_user')
        for rec in self:
            user = rec.user_id
            if not user:
                continue
            if grant:
                user.sudo().write({'group_ids': [(4, group.id)]})
                rec._convert_to_portal_if_eligible(user)
            else:
                # Only revoke if no other active membership exists
                other_active = self.search([
                    ('partner_id', '=', rec.partner_id.id),
                    ('state', '=', 'active'),
                    ('id', '!=', rec.id),
                ], limit=1)
                if not other_active:
                    user.sudo().write({'group_ids': [(3, group.id)]})

    # ── Cron: automatic expiration ──────────────────────────────────────────

    @api.model
    def cron_check_expiry(self):
        """Expire memberships whose end_date is past."""
        today = fields.Date.today()
        expired = self.search([
            ('state', '=', 'active'),
            ('end_date', '<', today),
            ('end_date', '!=', False),
        ])
        for rec in expired:
            rec.write({'state': 'expired'})
            rec._sync_social_access(grant=False)

    # ── Constraints ──────────────────────────────────────────────────────────

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.end_date and rec.start_date and rec.end_date < rec.start_date:
                raise ValidationError(_("End date must be after start date."))

    @api.constrains('partner_id', 'state')
    def _check_unique_active(self):
        if self.env.context.get('no_check_unique_active'):
            return
        for rec in self:
            if rec.state == 'active':
                duplicate = self.search([
                    ('partner_id', '=', rec.partner_id.id),
                    ('state', '=', 'active'),
                    ('id', '!=', rec.id),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        _("Member \"%s\" already has an active membership.", rec.partner_id.name)
                    )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_state_label(self):
        self.ensure_one()
        # _description_selection : libellé traduit selon la langue courante
        # (le fr_CA.po fournit « Actif », « En attente », etc.).
        return dict(self._fields['state']._description_selection(self.env)).get(self.state, self.state)

    @api.model
    def get_active_for_partner(self, partner_id):
        return self.search([
            ('partner_id', '=', partner_id),
            ('state', '=', 'active'),
        ], limit=1)
