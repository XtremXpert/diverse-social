from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied
from odoo.tools import html2plaintext


class DiscussChatsPortal(http.Controller):
    """Messagerie privée via Discuss natif (variante A/B de social_messaging).

    - /my/chats : liste portail des conversations (discuss.channel de type chat).
    - /discuss-message/<user_id> : ouvre/crée le chat Discuss avec un membre et
      redirige vers la page Discuss publique. Réutilise le MÊME canal que
      social_calling_discuss (/discuss-call) → chat et appel partagés.
    """

    @http.route(['/my/messages', '/my/chats'], type='http', auth='user', website=True, sitemap=False)
    def my_chats(self, **kw):
        user = request.env.user
        Profile = request.env['club_social_profile.profile'].sudo()
        # Canaux 'chat' dont l'utilisateur courant est membre. sudo + filtre
        # explicite sur son membership (le portail n'a pas de lecture large).
        channels = request.env['discuss.channel'].sudo().search([
            ('channel_type', '=', 'chat'),
            ('channel_member_ids.partner_id', '=', user.partner_id.id),
        ], order='last_interest_dt desc')

        chat_data = []
        for ch in channels:
            other_partner = ch.channel_member_ids.partner_id.filtered(
                lambda p: p != user.partner_id)[:1]
            other_user = other_partner.user_ids[:1]
            other_profile = Profile.search(
                [('user_id', '=', other_user.id)], limit=1) if other_user else None
            last_msg = ch.message_ids.sorted('id', reverse=True)[:1]
            preview = ''
            if last_msg:
                preview = (html2plaintext(last_msg.body or '') or '').strip()
                if len(preview) > 80:
                    preview = preview[:80] + '…'
            self_member = ch.channel_member_ids.filtered(
                lambda m: m.partner_id == user.partner_id)[:1]
            chat_data.append({
                'channel': ch,
                'other_user': other_user,
                'other_profile': other_profile,
                'preview': preview,
                'last_date': last_msg.date if last_msg else False,
                'unread': self_member.message_unread_counter if self_member else 0,
            })
        return request.render('social_messaging_discuss.portal_chats_list', {
            'chat_data': chat_data,
            'page_name': 'chats',
        })

    @http.route(['/discuss-message/<int:user_id>'], type='http', auth='user', website=True)
    def discuss_message_start(self, user_id, **kw):
        user = request.env.user
        other = request.env['res.users'].sudo().browse(user_id)
        if not other.exists() or other.id == user.id or not other.partner_id:
            return request.redirect('/my/messages')

        # Blocage mutuel (défense en profondeur ; _get_or_create_chat re-checke).
        if request.env['social_safety.block'].sudo().is_blocked(user, other):
            raise AccessDenied()

        # Politique de contact : autorité côté controller, avec le vrai
        # utilisateur (le check modèle est neutralisé sous sudo). Redirection
        # douce vers le profil plutôt qu'une page d'erreur.
        if not request.env['discuss.channel']._smd_can_open_chat_ui(other):
            return request.redirect('/profile/%s?msg=connect_first' % other.id)

        # sudo : la création de discuss.channel est réservée aux internes ;
        # .sudo() bypass l'ACL SANS changer self.env.user (reste l'utilisateur
        # portail) → le bon partenaire est ajouté comme membre.
        channel = request.env['discuss.channel'].sudo()._get_or_create_chat(
            [other.partner_id.id])
        return request.redirect('/discuss/channel/%s' % channel.id)
