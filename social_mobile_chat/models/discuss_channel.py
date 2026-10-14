import datetime

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext, plaintext2html

PAGE_SIZE = 50
MAX_BODY = 4000


def iso(value):
    return value.replace(tzinfo=datetime.UTC).isoformat() if value else None


class DiscussChannel(models.Model):
    """Messagerie de l'application mobile.

    Les conversations de l'application sont les chats à deux et les conversations de relation
    (``social_relation``). Toutes les lectures se font en sudo, mais toujours après avoir vérifié
    que l'utilisateur courant est membre du canal ; les envois passent par ``message_post`` avec
    l'utilisateur courant, donc par le contrôle de blocage de ``social_messaging_discuss``."""
    _inherit = 'discuss.channel'

    @api.model
    def _mobile_channels(self, user):
        """Canaux de messagerie mobile dont ``user`` est membre, du plus récent au plus ancien."""
        relation_channels = self.env['social_relation.relation'].sudo().search([
            ('channel_id', '!=', False), ('state', '=', 'active'),
            ('member_ids', 'any', [('user_id', '=', user.id), ('state', '=', 'accepted')]),
        ]).channel_id
        chats = self.sudo().search([
            ('channel_type', '=', 'chat'),
            ('channel_member_ids.partner_id', '=', user.partner_id.id),
        ])
        return (chats | relation_channels).sorted(lambda c: c.last_interest_dt or c.create_date, reverse=True)

    def _mobile_check_member(self, user):
        """Le canal, en sudo, si ``user`` en est membre et que c'est une conversation mobile."""
        self.ensure_one()
        channel = self.sudo()
        if channel.channel_type not in ('chat', 'group') or user.partner_id not in channel.channel_member_ids.partner_id:
            raise AccessError(_("Conversation introuvable."))
        return channel

    def _mobile_relation(self):
        return self.env['social_relation.relation'].sudo().search([('channel_id', '=', self.id)], limit=1)

    def _mobile_payload(self, user):
        """Résumé d'une conversation pour la liste : titre, dernier message, non-lus."""
        channel = self._mobile_check_member(user)
        Profile = self.env['club_social_profile.profile'].sudo()
        member = channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]
        last = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('message_type', '=', 'comment'),
        ], order='id desc', limit=1)
        payload = {
            'id': channel.id,
            'kind': 'chat' if channel.channel_type == 'chat' else 'relation',
            'unread': member.message_unread_counter if member else 0,
            'last_message': self._mobile_message(last, user, Profile) if last else None,
            'last_activity': iso(channel.last_interest_dt or channel.create_date),
        }
        if channel.channel_type == 'chat':
            other = channel.channel_member_ids.partner_id.filtered(lambda p: p != user.partner_id).user_ids[:1]
            payload.update({
                'title': Profile._display_name_for_user(other) if other else channel.name,
                'other_user_id': other.id or None,
                'relation_id': None,
            })
        else:
            relation = channel._mobile_relation()
            payload.update({
                'title': relation.name or channel.name,
                'other_user_id': None,
                'relation_id': relation.id or None,
            })
        return payload

    @api.model
    def _mobile_message(self, message, user, Profile):
        author = message.author_id.user_ids[:1]
        return {
            'id': message.id,
            'author_user_id': author.id or None,
            'author_name': Profile._display_name_for_user(author) if author else (message.author_id.name or ''),
            'is_mine': message.author_id == user.partner_id,
            'body': (html2plaintext(message.body or '') or '').strip(),
            'date': iso(message.date),
        }

    def _mobile_messages(self, user, before=None, after=None, limit=PAGE_SIZE):
        """Messages (texte, du plus ancien au plus récent) : une page avant ``before``, ou les
        nouveaux après ``after`` (relève périodique)."""
        channel = self._mobile_check_member(user)
        domain = [('model', '=', 'discuss.channel'), ('res_id', '=', channel.id), ('message_type', '=', 'comment')]
        if before:
            domain.append(('id', '<', int(before)))
        if after:
            domain.append(('id', '>', int(after)))
        limit = max(1, min(int(limit or PAGE_SIZE), 200))
        order = 'id asc' if after else 'id desc'
        messages = self.env['mail.message'].sudo().search(domain, order=order, limit=limit)
        Profile = self.env['club_social_profile.profile'].sudo()
        return [self._mobile_message(m, user, Profile) for m in messages.sorted('id')]

    def _mobile_post(self, user, body):
        """Envoie un message texte au nom de ``user`` (contrôle de blocage compris)."""
        channel = self._mobile_check_member(user)
        body = (body or '').strip()
        if not body:
            raise UserError(_("Message vide."))
        if len(body) > MAX_BODY:
            raise UserError(_("Message trop long (%(max)s caractères au plus).", max=MAX_BODY))
        # sudo() ne change pas l'utilisateur courant : l'auteur reste le membre, et le contrôle
        # de blocage de social_messaging_discuss s'applique.
        message = channel.with_user(user).sudo().message_post(
            body=plaintext2html(body), message_type='comment', subtype_xmlid='mail.mt_comment')
        member = channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]
        if member:
            member._mark_as_read(message.id)
        return self._mobile_message(message, user, self.env['club_social_profile.profile'].sudo())

    def _mobile_mark_read(self, user, last_message_id):
        channel = self._mobile_check_member(user)
        member = channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]
        if member and last_message_id:
            member._mark_as_read(int(last_message_id))

    @api.model
    def _mobile_open_chat(self, user, other):
        """Conversation à deux avec ``other`` : la politique de contact et le blocage de
        social_messaging_discuss s'appliquent (une conversation existante reste toujours ouverte)."""
        if not other or other == user or not other.active:
            raise UserError(_("Membre introuvable."))
        if self.env['social_safety.block'].sudo().is_blocked(user, other):
            raise UserError(_("Vous ne pouvez pas écrire à cette personne."))
        Channel = self.with_user(user)
        if not Channel._smd_can_open_chat_ui(other):
            raise UserError(_("Vous ne pouvez écrire qu'à vos connexions, aux membres de vos groupes et cercles, "
                              "ou à une personne disponible maintenant."))
        # sudo : la création de canal est réservée aux internes ; l'utilisateur courant reste
        # le membre, qui est donc bien ajouté à la conversation.
        return Channel.sudo()._get_or_create_chat([other.partner_id.id])
