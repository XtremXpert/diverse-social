import datetime
import io
import os

from PIL import Image, ImageOps

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext, plaintext2html
from odoo.tools.mimetypes import guess_mimetype

PAGE_SIZE = 50
MAX_BODY = 4000
# Message vocal de l'application : AAC dans un conteneur MP4 (.m4a), ~0,25 Mo par minute à 32 kb/s.
VOICE_MIMETYPE = 'audio/mp4'
MAX_VOICE_BYTES = 3 * 1024 * 1024
# Pièce jointe envoyée de l'application (photo, document).
MAX_FILE_BYTES = 15 * 1024 * 1024
# Jamais acceptés d'un membre : ouverts dans Discuss sur le site, ils exécuteraient du code chez les
# autres (le garde-fou SVG d'Odoo ne joue pas ici : l'envoi se fait en sudo).
FORBIDDEN_MIMETYPES = {
    'image/svg+xml', 'text/html', 'application/xhtml+xml', 'text/javascript', 'application/javascript',
    'application/x-javascript', 'text/xml', 'application/xml',
}
FORBIDDEN_EXTENSIONS = {'.svg', '.svgz', '.html', '.htm', '.xhtml', '.js', '.mjs', '.xml'}
# Photos réenregistrées sans métadonnées (EXIF : position GPS exacte, appareil, date).
CLEANED_IMAGES = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}
MAX_IMAGE_SIDE = 4096
THUMB_SIDE = 512


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
        # sudo : pièces jointes d'un message déjà lisible par le membre (vérifié par l'appelant).
        attachments = message.sudo().attachment_ids
        voice = attachments.filtered('voice_ids')[:1]
        return {
            'id': message.id,
            'author_user_id': author.id or None,
            'author_name': Profile._display_name_for_user(author) if author else (message.author_id.name or ''),
            'is_mine': message.author_id == user.partner_id,
            'body': (html2plaintext(message.body or '') or '').strip(),
            'date': iso(message.date),
            # Message vocal (de l'application ou de Discuss) : à télécharger par /attachments/<id>.
            'voice': {'attachment_id': voice.id, 'mimetype': voice.mimetype} if voice else None,
            # Photos et fichiers (de l'application ou du site) : /attachments/<id>, ?thumb=1 pour une image.
            'attachments': [self._mobile_attachment_payload(a) for a in attachments - voice],
            # Ancien champ, gardé pour les versions installées de l'application.
            'attachment_count': len(attachments - voice),
        }

    @api.model
    def _mobile_attachment_payload(self, attachment):
        mimetype = attachment.mimetype or 'application/octet-stream'
        return {
            'id': attachment.id,
            'name': attachment.name or '',
            'mimetype': mimetype,
            'size': attachment.file_size or 0,
            'is_image': mimetype.startswith('image/') and mimetype not in FORBIDDEN_MIMETYPES,
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

    def _mobile_post_voice(self, user, data):
        """Envoie un message vocal (.m4a) au nom de ``user``, comme le fait Discuss : pièce jointe
        marquée vocale, contrôle de blocage et notification compris."""
        channel = self._mobile_check_member(user)
        if not data:
            raise UserError(_("Message vocal vide."))
        if len(data) > MAX_VOICE_BYTES:
            raise UserError(_("Message vocal trop long."))
        # Conteneur MP4 : « ftyp » à l'octet 4. Le type annoncé par l'appareil ne fait pas foi.
        if data[4:8] != b'ftyp':
            raise UserError(_("Format audio non pris en charge."))
        message = channel.with_user(user).sudo().message_post(
            body='', message_type='comment', subtype_xmlid='mail.mt_comment',
            attachments=[('Message vocal.m4a', data, {'voice': True})])
        message.sudo().attachment_ids.mimetype = VOICE_MIMETYPE
        member = channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]
        if member:
            member._mark_as_read(message.id)
        return self._mobile_message(message, user, self.env['club_social_profile.profile'].sudo())

    def _mobile_post_file(self, user, name, data, body=None):
        """Envoie une photo ou un fichier au nom de ``user``, avec une légende facultative. Le type
        vient du contenu (jamais de l'appareil) ; une photo est réenregistrée sans métadonnées."""
        channel = self._mobile_check_member(user)
        if not data:
            raise UserError(_("Fichier vide."))
        if len(data) > MAX_FILE_BYTES:
            raise UserError(_("Fichier trop lourd (%(max)s Mo au plus).", max=MAX_FILE_BYTES // (1024 * 1024)))
        name = os.path.basename((name or '').strip())[:120] or _("Fichier")
        mimetype = guess_mimetype(data, default='application/octet-stream')
        if mimetype in FORBIDDEN_MIMETYPES or os.path.splitext(name)[1].lower() in FORBIDDEN_EXTENSIONS:
            raise UserError(_("Ce type de fichier n'est pas accepté."))
        if mimetype in CLEANED_IMAGES:
            data = self._mobile_clean_image(data, CLEANED_IMAGES[mimetype])
        body = (body or '').strip()
        if len(body) > MAX_BODY:
            raise UserError(_("Message trop long (%(max)s caractères au plus).", max=MAX_BODY))
        message = channel.with_user(user).sudo().message_post(
            body=plaintext2html(body) if body else '', message_type='comment', subtype_xmlid='mail.mt_comment',
            attachments=[(name, data)])
        message.sudo().attachment_ids.mimetype = mimetype
        member = channel.channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]
        if member:
            member._mark_as_read(message.id)
        return self._mobile_message(message, user, self.env['club_social_profile.profile'].sudo())

    @api.model
    def _mobile_clean_image(self, data, image_format):
        """Photo redressée (orientation EXIF), réduite à 4096 px, réenregistrée sans métadonnées."""
        try:
            with Image.open(io.BytesIO(data)) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
                if image_format == 'JPEG' and image.mode not in ('RGB', 'L'):
                    image = image.convert('RGB')
                out = io.BytesIO()
                # Sans « exif=… » ni « pnginfo=… » : aucune métadonnée n'est recopiée.
                image.save(out, image_format, **({'quality': 90} if image_format in ('JPEG', 'WEBP') else {}))
                return out.getvalue()
        except (OSError, ValueError, Image.DecompressionBombError) as e:
            raise UserError(_("Image illisible.")) from e

    def _mobile_attachment(self, user, attachment_id, thumb=False):
        """Pièce jointe d'un message de cette conversation : ``(contenu, type)`` ; ``thumb`` : une
        miniature JPEG de 512 px au plus pour une image. AccessError si l'utilisateur n'en est pas
        membre ou si la pièce jointe appartient à une autre conversation."""
        channel = self._mobile_check_member(user)
        attachment = self.env['ir.attachment'].sudo().browse(int(attachment_id)).exists()
        message = self.env['mail.message'].sudo().search([
            ('model', '=', 'discuss.channel'), ('res_id', '=', channel.id),
            ('attachment_ids', 'in', attachment.ids),
        ], limit=1) if attachment else False
        if not message or attachment.res_model != 'discuss.channel' or attachment.res_id != channel.id:
            raise AccessError(_("Pièce jointe introuvable."))
        # ``raw`` est un BinaryValue (fichier du filestore) : bytes() en lit le contenu.
        data, mimetype = bytes(attachment.raw or b''), attachment.mimetype or 'application/octet-stream'
        if thumb and mimetype.startswith('image/') and mimetype not in FORBIDDEN_MIMETYPES:
            try:
                with Image.open(io.BytesIO(data)) as source:
                    image = ImageOps.exif_transpose(source)
                    image.thumbnail((THUMB_SIDE, THUMB_SIDE))
                    out = io.BytesIO()
                    image.convert('RGB').save(out, 'JPEG', quality=80)
                    return out.getvalue(), 'image/jpeg'
            except (OSError, ValueError, Image.DecompressionBombError):
                pass  # image illisible : l'original, tel quel
        return data, mimetype

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
