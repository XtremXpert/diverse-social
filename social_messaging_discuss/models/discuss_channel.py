from odoo import models, _
from odoo.exceptions import UserError


class DiscussChannel(models.Model):
    """Applique le blocage social_safety sur la messagerie Discuss.

    Discuss natif n'a AUCUNE notion de blocage. Pour un réseau social avec
    blocage + panic mode, c'est une exigence de sécurité : deux personnes qui
    se sont bloquées ne doivent ni démarrer une conversation, ni s'envoyer de
    message.

    Le point critique est `message_post` : la route native /mail/message/post
    (auth=public) fait `thread.sudo().message_post(...)` et contourne donc tout
    controller custom. `.sudo()` ne change PAS `self.env.user`, on peut donc
    baser le check sur l'utilisateur réellement connecté.

    Scope STRICT : uniquement les chats 1:1 (`channel_type == 'chat'`). On ne
    touche jamais aux canaux d'équipe, groupes, livechat ou au Discuss interne
    → aucune régression sur la messagerie interne d'Odoo.
    """
    _inherit = 'discuss.channel'

    def _smd_blocking_user(self):
        """Retourne l'utilisateur courant SI le blocage social doit être évalué,
        sinon None (contexte public/invité → pas de relation de blocage)."""
        user = self.env.user
        if not user or user._is_public():
            return None
        return user

    def _smd_assert_not_blocked_on_post(self):
        """Lève UserError si l'auteur courant est bloqué (ou a bloqué) l'autre
        membre d'un chat 1:1. No-op pour tout autre type de canal."""
        sender = self._smd_blocking_user()
        if not sender:
            return
        Block = self.env['social_safety.block'].sudo()
        for channel in self:
            if channel.channel_type != 'chat':
                continue
            others = channel.sudo().channel_member_ids.partner_id.filtered(
                lambda p: p != sender.partner_id)
            for other_partner in others:
                other_user = other_partner.user_ids[:1]
                if other_user and Block.is_blocked(sender, other_user):
                    raise UserError(_(
                        "Vous ne pouvez pas envoyer de message à cette personne."))

    def message_post(self, *, message_type="notification", partner_ids=None, **kwargs):
        # On ne bloque que les messages "humains". Les messages système
        # (notification / user_notification : « X a rejoint », etc.) ne doivent
        # jamais lever — ils font partie de la machinerie Discuss.
        if message_type not in ("notification", "user_notification"):
            self._smd_assert_not_blocked_on_post()
        return super().message_post(
            message_type=message_type, partner_ids=partner_ids, **kwargs)

    # ── Politique de contact : qui peut OUVRIR une nouvelle conversation ──────
    #
    # Par défaut, Discuss laisse n'importe qui écrire à n'importe qui. Sur ce
    # réseau, la communication passe par la confiance : on ne peut démarrer une
    # NOUVELLE conversation qu'avec une connexion, un membre d'un groupe commun,
    # une personne rangée dans un cercle (dans un sens ou l'autre), ou une
    # personne « Disponible maintenant » (hook, Phase 2). Un utilisateur interne
    # peut écrire à tous si le réglage social_messaging_discuss.internal_bypass
    # est actif.
    #
    # Grand-père : les conversations DÉJÀ existantes ne sont jamais fermées — le
    # gating ne s'applique qu'à la création. On ne touche donc pas message_post.

    def _smd_gating_user(self):
        """Utilisateur courant SI la politique de contact doit s'appliquer.

        Skip si public, superuser (appels sudo — le controller fait alors
        autorité avec le vrai utilisateur) ou non-membre social (admins
        internes via le backend Discuss)."""
        user = self.env.user
        if not user or user._is_public() or self.env.su:
            return None
        if not user.has_group('social_base.group_social_user'):
            return None
        return user

    def _smd_can_message(self, sender, other_user):
        """True si `sender` a le droit d'ouvrir une nouvelle conversation avec
        `other_user` selon la politique sociale."""
        if not other_user or other_user == sender:
            return True
        env = self.env
        # 0. Utilisateur interne, si le réglage « Utilisateurs internes : écrire
        #    à tout membre » est actif (Paramètres › Discuss).
        if sender._is_internal() and env['ir.config_parameter'].sudo().get_bool(
                'social_messaging_discuss.internal_bypass'):
            return True
        # 1. Connexion acceptée (bidirectionnel)
        Conn = env['club_social_profile.connection'].sudo()
        if Conn.is_connected(sender, other_user) or Conn.is_connected(other_user, sender):
            return True
        # 2. Groupe commun
        if 'social_group.group' in env:
            if env['social_group.group'].sudo().search_count([
                ('member_ids', 'in', sender.id),
                ('member_ids', 'in', other_user.id),
            ], limit=1):
                return True
        # 3. Cercle partagé (l'un range l'autre)
        if 'social_circles.circle' in env:
            if env['social_circles.circle'].sudo().search_count([
                '|',
                '&', ('profile_id.user_id', '=', sender.id), ('member_ids', 'in', other_user.id),
                '&', ('profile_id.user_id', '=', other_user.id), ('member_ids', 'in', sender.id),
            ], limit=1):
                return True
        # 4. Exception « Disponible maintenant » — hook, surchargé en Phase 2
        if self._smd_message_exception(sender, other_user):
            return True
        return False

    def _smd_message_exception(self, sender, other_user):
        """Point d'extension : `social_right_now` autorisera le contact vers une
        personne ayant une session « Disponible maintenant » active."""
        return False

    def _smd_chat_exists_with(self, partner_ids):
        """Un chat 1:1 existe-t-il déjà entre l'utilisateur courant et ces
        partenaires ? (grand-père des conversations en cours)"""
        want = set(partner_ids) | {self.env.user.partner_id.id}
        domain = [('channel_type', '=', 'chat')]
        for pid in want:
            domain.append(('channel_member_ids.partner_id', '=', pid))
        for ch in self.sudo().search(domain):
            if set(ch.channel_member_ids.partner_id.ids) == want:
                return True
        return False

    def _smd_can_open_chat_ui(self, other_user):
        """Pour l'UI (bouton Message) et le controller : autorisé si la politique
        permet une nouvelle conversation OU si un fil existe déjà."""
        user = self.env.user
        if not other_user or other_user == user or user._is_public():
            return False
        if self._smd_can_message(user, other_user):
            return True
        return self._smd_chat_exists_with(other_user.partner_id.ids)

    def _get_or_create_chat(self, partners_to):  # Odoo 20 : plus de paramètre pin
        # Défense en profondeur + UX : empêche d'ouvrir/réouvrir un chat avec une
        # personne bloquée (les controllers /discuss-message et /discuss-call
        # checkent aussi, mais ceci protège tout chemin futur).
        sender = self._smd_blocking_user()
        if sender:
            Block = self.env['social_safety.block'].sudo()
            Partner = self.env['res.partner'].sudo()
            for pid in partners_to:
                other_user = Partner.browse(pid).user_ids[:1]
                if (other_user and other_user != sender
                        and Block.is_blocked(sender, other_user)):
                    raise UserError(_(
                        "Vous ne pouvez pas démarrer une conversation avec "
                        "cette personne."))
        # Politique de contact — uniquement pour une NOUVELLE conversation.
        gating = self._smd_gating_user()
        if gating and not self._smd_chat_exists_with(partners_to):
            Partner = self.env['res.partner'].sudo()
            for pid in partners_to:
                other_user = Partner.browse(pid).user_ids[:1]
                if (other_user and other_user != gating
                        and not self._smd_can_message(gating, other_user)):
                    raise UserError(_(
                        "Vous ne pouvez écrire qu'à vos connexions, aux membres "
                        "de vos groupes et cercles, ou à une personne disponible "
                        "maintenant. Envoyez d'abord une demande de connexion."))
        return super()._get_or_create_chat(partners_to)
