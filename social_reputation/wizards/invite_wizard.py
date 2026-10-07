from odoo import models, fields, _
from odoo.exceptions import UserError


class VouchingInviteWizard(models.TransientModel):
    _name = 'social_reputation.invite_wizard'
    _description = 'Invite a Newcomer by Email'

    email = fields.Char('Email', required=True)
    statement = fields.Text(
        'Statement',
        help='Why are you vouching for this person? Shown in the invitation email.',
    )
    send_now = fields.Boolean(
        'Send email immediately', default=True,
        help='Uncheck to create the invitation without sending the email — '
             'useful if you want to copy the URL manually.',
    )

    def action_create_invitation(self):
        self.ensure_one()
        vouching = self.env['social_reputation.vouching'].action_invite_email(
            email=self.email,
            statement=self.statement or None,
        )
        if self.send_now:
            try:
                vouching.action_send_invitation_email()
            except UserError:
                raise
            except Exception as exc:
                raise UserError(_(
                    'Invitation created but the email could not be sent: %(err)s',
                    err=str(exc),
                ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invitation'),
            'res_model': 'social_reputation.vouching',
            'res_id': vouching.id,
            'view_mode': 'form',
            'views': [(False, 'form')],  # requis par Odoo 20
            'target': 'current',
        }
