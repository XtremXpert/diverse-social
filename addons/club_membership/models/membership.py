from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ClubMembership(models.Model):
    _name = 'club_membership.membership'
    _description = 'Adhésion au club'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, id desc'
    _rec_name = 'display_name'

    partner_id = fields.Many2one(
        'res.partner', 'Membre', required=True, index=True, ondelete='cascade',
    )
    user_id = fields.Many2one(
        'res.users', 'Utilisateur', compute='_compute_user_id', store=True,
    )
    membership_type_id = fields.Many2one(
        'club_membership.type', 'Type', required=True, ondelete='restrict',
    )
    state = fields.Selection([
        ('pending', 'En attente'),
        ('active', 'Actif'),
        ('expired', 'Expiré'),
        ('suspended', 'Suspendu'),
        ('cancelled', 'Annulé'),
    ], default='pending', required=True, index=True, tracking=True)

    start_date = fields.Date('Début', required=True, default=fields.Date.today)
    end_date = fields.Date('Fin')
    fee_paid = fields.Monetary('Cotisation payée', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id,
    )
    invoice_id = fields.Many2one(
        'account.move', 'Facture', domain=[('move_type', '=', 'out_invoice')],
        ondelete='set null',
    )
    notes = fields.Text('Notes internes')

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

    # ── Transitions d'état ────────────────────────────────────────────────────

    def action_activate(self):
        for rec in self:
            if rec.state not in ('pending', 'suspended'):
                raise UserError(
                    _("Impossible d'activer une adhésion en état « %s ».", rec._get_state_label())
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
                    _("Impossible de suspendre une adhésion en état « %s ».", rec._get_state_label())
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
        """Crée une nouvelle adhésion dans la continuité de celle-ci."""
        self.ensure_one()
        start = (self.end_date or fields.Date.today()) + relativedelta(days=1)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'club_membership.membership',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_membership_type_id': self.membership_type_id.id,
                'default_start_date': str(start),
                'default_fee_paid': self.membership_type_id.fee,
            },
        }

    # ── Accès réseau social ───────────────────────────────────────────────────

    def _sync_social_access(self, grant):
        """Accorde ou révoque group_social_user selon l'état de l'adhésion."""
        group = self.env.ref('social_base.group_social_user')
        for rec in self:
            user = rec.user_id
            if not user:
                continue
            if grant:
                user.sudo().write({'group_ids': [(4, group.id)]})
            else:
                # Ne révoquer que si aucune autre adhésion active n'existe
                other_active = self.search([
                    ('partner_id', '=', rec.partner_id.id),
                    ('state', '=', 'active'),
                    ('id', '!=', rec.id),
                ], limit=1)
                if not other_active:
                    user.sudo().write({'group_ids': [(3, group.id)]})

    # ── Cron : expiration automatique ────────────────────────────────────────

    @api.model
    def cron_check_expiry(self):
        """Expire les adhésions dont la date de fin est dépassée."""
        today = fields.Date.today()
        expired = self.search([
            ('state', '=', 'active'),
            ('end_date', '<', today),
            ('end_date', '!=', False),
        ])
        for rec in expired:
            rec.write({'state': 'expired'})
            rec._sync_social_access(grant=False)

    # ── Contraintes ───────────────────────────────────────────────────────────

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for rec in self:
            if rec.end_date and rec.start_date and rec.end_date < rec.start_date:
                raise ValidationError(_("La date de fin doit être postérieure à la date de début."))

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
                        _("Le membre « %s » a déjà une adhésion active.", rec.partner_id.name)
                    )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_state_label(self):
        self.ensure_one()
        return dict(self._fields['state'].selection).get(self.state, self.state)

    @api.model
    def get_active_for_partner(self, partner_id):
        return self.search([
            ('partner_id', '=', partner_id),
            ('state', '=', 'active'),
        ], limit=1)
