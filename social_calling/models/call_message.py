from odoo import models, fields


class SocialCallingMessage(models.Model):
    """Message de chat d'un appel, capturé depuis le chat Jitsi pour le rendre
    persistant dans l'historique. Chaque participant n'enregistre que ses propres
    messages sortants (event Jitsi `outgoingMessage`) -> pas de doublon, auteur
    fiable côté serveur."""
    _name = 'social_calling.message'
    _description = 'Social Calling Chat Message'
    _order = 'create_date asc, id asc'

    session_id = fields.Many2one(
        'social_calling.session', string='Call', required=True,
        ondelete='cascade', index=True,
    )
    author_id = fields.Many2one('res.users', string='Author', ondelete='set null')
    author_name = fields.Char(string='Author Name')
    body = fields.Text(string='Message', required=True)
    is_private = fields.Boolean(string='Private', default=False)
    # Un message peut être un fichier partagé (body = nom du fichier).
    attachment_id = fields.Many2one('ir.attachment', string='File', ondelete='cascade')
    # Aperçu de lien (OpenGraph), façon Messenger.
    preview_url = fields.Char(string='Preview URL')
    preview_title = fields.Char(string='Preview Title')
    preview_description = fields.Text(string='Preview Description')
    preview_image = fields.Char(string='Preview Image')
