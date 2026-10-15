import datetime
import hashlib
import hmac
import secrets
import uuid

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_normalize

# Le QR code du nouveau venu change toutes les PERIOD secondes ; un code des CODE_WINDOW
# périodes précédentes est encore accepté (scan, puis confirmation par le parrain).
PERIOD = 30
CODE_WINDOW = 3
ENROLLMENT_HOURS = 24
# Après la remise de la clé, l'appareil peut la redemander pendant ce délai si la réponse
# s'est perdue (réseau mobile) ; la ligne est effacée dès son premier appel authentifié.
REDELIVERY_MINUTES = 15
MAX_PENDING_PER_EMAIL = 3
MAX_PENDING_PER_CLIENT = 10
MAX_PENDING_TOTAL = 5000


def hash_secret(secret):
    return hashlib.sha256((secret or '').encode()).hexdigest()


def like_escape(value):
    return value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


def totp(qr_secret, step):
    digest = hmac.new(qr_secret.encode(), str(step).encode(), hashlib.sha256).hexdigest()
    return digest[:10]


class SocialMobileEnrollment(models.Model):
    """Demande d'inscription faite depuis l'application, en attente d'un parrain.

    Ce n'est pas un compte : le compte (``res.users``) n'est créé qu'au parrainage. La ligne ne
    garde que le courriel saisi, des secrets de l'appareil et son échéance ; elle est effacée dès
    que l'application a reçu sa clé, ou à l'échéance (Loi 25 : courriel d'une personne pas encore
    admise)."""
    _name = 'social_mobile.enrollment'
    _description = "Inscription mobile en attente de parrainage"
    _order = 'create_date desc'
    _rec_name = 'email'

    uuid = fields.Char(required=True, readonly=True, index=True, copy=False, default=lambda self: str(uuid.uuid4()))
    email = fields.Char("Courriel", required=True, readonly=True)
    device_name = fields.Char("Appareil", readonly=True)
    state = fields.Selection([
        ('pending', "En attente d'un parrain"),
        ('sponsored', "Parrainée, clé à remettre"),
        ('delivered', "Clé remise"),
    ], default='pending', required=True, readonly=True, index=True)
    # Secret du QR code : l'appareil en dérive le code affiché ; le serveur le vérifie.
    qr_secret = fields.Char(readonly=True, copy=False, groups='base.group_system')
    # Empreinte du secret de suivi : seul l'appareil peut récupérer sa clé.
    poll_secret_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    # Empreinte de l'adresse IP : limite le nombre d'inscriptions ouvertes par client, sans
    # conserver l'adresse elle-même.
    client_hash = fields.Char(readonly=True, copy=False, index=True, groups='base.group_system')
    consent_at = fields.Datetime("Consentement", readonly=True)
    policy_version_id = fields.Many2one('social_privacy.policy.version', "Politique acceptée", readonly=True,
                                        ondelete='restrict')
    delivered_at = fields.Datetime("Clé remise le", readonly=True)
    expires_at = fields.Datetime("Échéance", required=True, readonly=True)
    sponsor_id = fields.Many2one('res.users', "Parrain", readonly=True, ondelete='cascade')
    user_id = fields.Many2one('res.users', "Compte créé", readonly=True, ondelete='cascade')

    _uuid_uniq = models.Constraint('UNIQUE(uuid)', "Identifiant d'inscription en double.")

    # ── Côté nouveau venu (routes publiques) ─────────────────────────────────

    @api.model
    def _api_start(self, email, device_name, consent, client=None):
        """Ouvre une inscription. Retourne ``(enrollment, poll_secret)``.

        On ne dit jamais si le courriel a déjà un compte : ce serait révéler qui est membre.
        Le parrain l'apprend au moment de confirmer, en personne."""
        email = email_normalize(email or '')
        if not email:
            raise ValidationError(_("Adresse courriel invalide."))
        if not consent:
            raise ValidationError(_("Le consentement est requis."))
        policy = self._current_policy()
        if not policy:
            raise UserError(_("Les inscriptions sont fermées : aucune politique de confidentialité n'est en vigueur."))
        Enrollment = self.sudo()
        now = fields.Datetime.now()
        pending = [('state', '=', 'pending'), ('expires_at', '>', now)]
        if Enrollment.search_count(pending + [('email', '=', email)]) >= MAX_PENDING_PER_EMAIL:
            raise UserError(_("Trop d'inscriptions en attente pour ce courriel. Réessayez plus tard."))
        client_hash = hash_secret(client) if client else False
        if client_hash and Enrollment.search_count(pending + [('client_hash', '=', client_hash)]) >= MAX_PENDING_PER_CLIENT:
            raise UserError(_("Trop d'inscriptions en attente depuis cet appareil. Réessayez plus tard."))
        if Enrollment.search_count(pending) >= MAX_PENDING_TOTAL:
            raise UserError(_("Trop d'inscriptions en attente. Réessayez plus tard."))
        poll_secret = secrets.token_urlsafe(32)
        enrollment = Enrollment.create({
            'email': email,
            'device_name': (device_name or '')[:64] or False,
            'qr_secret': secrets.token_urlsafe(32),
            'poll_secret_hash': hash_secret(poll_secret),
            'client_hash': client_hash,
            'consent_at': now,
            'policy_version_id': policy.id,
            'expires_at': now + datetime.timedelta(hours=ENROLLMENT_HOURS),
        })
        return enrollment, poll_secret

    @api.model
    def _api_find(self, enrollment_uuid, poll_secret):
        """Inscription ``enrollment_uuid`` si ``poll_secret`` est le bon (sinon vide)."""
        enrollment = self.sudo().search([('uuid', '=', enrollment_uuid or '')], limit=1)
        if not enrollment or not hmac.compare_digest(enrollment.poll_secret_hash or '', hash_secret(poll_secret)):
            return self.sudo().browse()
        return enrollment

    def _api_collect(self):
        """Suivi par l'appareil. Une fois parrainée, remet une clé.

        La ligne n'est pas effacée tout de suite : si la réponse se perd, l'appareil redemande
        pendant REDELIVERY_MINUTES et reçoit une nouvelle clé (la précédente est supprimée). Elle
        l'est au premier appel authentifié de l'appareil (``_api_acknowledge``) ou par la purge.

        Retourne ``('pending', None)``, ``('active', payload)`` ou ``('gone', None)``."""
        self.ensure_one()
        now = fields.Datetime.now()
        if self.state == 'pending':
            return ('gone', None) if self.expires_at <= now else ('pending', None)
        if self.state == 'delivered' and self.delivered_at < now - datetime.timedelta(minutes=REDELIVERY_MINUTES):
            return 'gone', None
        user = self.user_id
        if not user or not user.active:
            return 'gone', None
        Keys = self.env['res.users.apikeys'].with_user(user)
        if self.state == 'delivered':
            Keys._social_mobile_revoke_all()  # clé d'une réponse perdue : jamais utilisée
        key, expiration = Keys._social_mobile_generate(self.device_name or 'Application mobile')
        self.sudo().write({'state': 'delivered', 'delivered_at': now})
        payload = {
            'key': key,
            'expires_at': expiration.replace(tzinfo=datetime.UTC).isoformat(),
            'user_id': user.id,
        }
        return 'active', payload

    @api.model
    def _api_acknowledge(self, user):
        """Premier appel authentifié de l'appareil : sa clé est arrivée, l'inscription (et le
        courriel qu'elle portait) est effacée."""
        self.sudo().search([('user_id', '=', user.id), ('state', '=', 'delivered')]).unlink()

    # ── Côté parrain ──────────────────────────────────────────────────────────

    def _current_step(self):
        return int(fields.Datetime.now().timestamp() // PERIOD)

    def _check_code(self, code):
        self.ensure_one()
        secret = self.sudo().qr_secret
        if not secret or not code:
            return False
        step = self._current_step()
        return any(hmac.compare_digest(totp(secret, step - i), code) for i in range(CODE_WINDOW + 1))

    @api.model
    def _api_scanned(self, enrollment_uuid, code):
        """Inscription désignée par un QR code scanné, s'il est encore valide (sinon vide)."""
        enrollment = self.sudo().search([('uuid', '=', enrollment_uuid or '')], limit=1)
        if not enrollment or enrollment.expires_at <= fields.Datetime.now() or not enrollment._check_code(code):
            return self.sudo().browse()
        return enrollment

    def _api_sponsor(self, sponsor, statement=None):
        """Le membre ``sponsor`` parraine cette inscription : crée le compte, le parrainage et
        l'adhésion active (accès immédiat au réseau). Idempotent pour le même parrain."""
        self.ensure_one()
        enrollment = self.sudo()
        if enrollment.state == 'sponsored':
            if enrollment.sponsor_id == sponsor:
                return enrollment.user_id
            raise UserError(_("Cette personne vient d'être parrainée par un autre membre."))
        refusal = sponsor._social_mobile_sponsor_refusal()
        if refusal:
            raise UserError(refusal)
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        if Users.search_count([('login', '=ilike', like_escape(enrollment.email))], limit=1):
            raise UserError(_("Ce courriel a déjà un compte : la personne doit choisir « J'ai déjà un compte » dans l'application."))

        portal = self.env.ref('base.group_portal')
        # Nom neutre : le début du courriel est souvent un vrai nom (« jean.tremblay »), et c'est
        # ce nom que voient les autres membres tant qu'aucun pseudonyme n'est choisi.
        newcomer = Users.with_context(no_reset_password=True).create({
            'name': _("Nouveau membre %s", secrets.token_hex(2).upper()),
            'login': enrollment.email,
            'email': enrollment.email,
            'group_ids': [(6, 0, [portal.id])],
        })
        self.env['club_social_profile.profile'].sudo().get_or_create_for_user(newcomer)
        # Le parrainage est créé au nom du parrain : vouch_for() prend l'utilisateur courant.
        self.env['social_reputation.vouching'].with_user(sponsor).sudo().vouch_for(newcomer, statement=statement)
        membership = self.env['club_membership.membership'].sudo().create({
            'partner_id': newcomer.partner_id.id,
            'membership_type_id': self._membership_type().id,
        })
        membership.action_activate()  # accorde l'accès au réseau (_sync_social_access)
        # Le parrain et son filleul sont connectés d'office : sans cela, la politique de contact
        # empêcherait le nouveau membre, qui ne connaît encore personne, d'écrire à son parrain.
        Connection = self.env['club_social_profile.connection'].sudo()
        now = fields.Datetime.now()
        for user, other in ((sponsor, newcomer), (newcomer, sponsor)):
            Connection.create({'user_id': user.id, 'connected_user_id': other.id, 'connection_type': 'friend',
                               'state': 'accepted', 'accepted_date': now})
        self.env['social_privacy.consent'].sudo().record_consent(
            newcomer, enrollment.policy_version_id, source='api')
        enrollment.write({'state': 'sponsored', 'sponsor_id': sponsor.id, 'user_id': newcomer.id})
        return newcomer

    def _membership_type(self):
        type_id = self.env['ir.config_parameter'].sudo().get_int('social_mobile.membership_type_id')
        membership_type = self.env['club_membership.type'].sudo().browse(type_id).exists()
        return membership_type or self.env.ref('club_membership.membership_type_regular')

    @api.model
    def _current_policy(self):
        return self.env['social_privacy.policy.version'].sudo().get_current_for_user()

    # ── Nettoyage ────────────────────────────────────────────────────────────

    @api.model
    def _cron_purge(self):
        """Efface les inscriptions échues, celles dont la clé a été remise, et celles parrainées
        dont l'appareil n'est jamais revenu. Le compte créé reste ; un administrateur peut lui
        remettre une clé ou le supprimer."""
        now = fields.Datetime.now()
        self.sudo().search([
            '|', '|',
            '&', ('state', '=', 'pending'), ('expires_at', '<=', now),
            '&', ('state', '=', 'delivered'), ('delivered_at', '<=', now - datetime.timedelta(minutes=REDELIVERY_MINUTES)),
            '&', ('state', '=', 'sponsored'), ('write_date', '<=', now - datetime.timedelta(days=7)),
        ]).unlink()
