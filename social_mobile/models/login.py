import datetime
import hmac
import secrets
import uuid

from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.tools import email_normalize

from .enrollment import hash_secret

CODE_MINUTES = 10
MAX_ATTEMPTS = 5
# Au-delà, le serveur répond comme d'habitude mais n'envoie plus de courriel à cette adresse.
MAX_MAILS_PER_EMAIL_HOUR = 5
MAX_PENDING_PER_CLIENT = 20
MAX_PENDING_TOTAL = 5000


class SocialMobileLogin(models.Model):
    """Connexion d'un membre existant depuis l'application, en cours de vérification.

    Une ligne par tentative : elle porte l'empreinte du code attendu (envoyé par courriel, ou
    code de double authentification) et celle du secret de l'appareil. Elle est créée même pour
    un courriel inconnu, avec un code que personne ne reçoit : la réponse ne révèle jamais si
    une adresse a un compte. Elle est effacée à la connexion, au dernier essai raté ou par la
    purge (au plus CODE_MINUTES minutes)."""
    _name = 'social_mobile.login'
    _description = "Connexion mobile en cours"
    _order = 'create_date desc'
    _rec_name = 'email'

    uuid = fields.Char(required=True, readonly=True, index=True, copy=False, default=lambda self: str(uuid.uuid4()))
    email = fields.Char("Courriel", required=True, readonly=True, index=True)
    user_id = fields.Many2one('res.users', "Compte", readonly=True, ondelete='cascade')
    step = fields.Selection([
        ('email', "Code envoyé par courriel"),
        ('totp', "Code de double authentification"),
    ], required=True, readonly=True)
    device_name = fields.Char("Appareil", readonly=True)
    code_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    secret_hash = fields.Char(readonly=True, copy=False, groups='base.group_system')
    client_hash = fields.Char(readonly=True, copy=False, index=True, groups='base.group_system')
    mail_sent = fields.Boolean(readonly=True)
    attempts = fields.Integer(readonly=True)
    expires_at = fields.Datetime("Échéance", required=True, readonly=True)

    _uuid_uniq = models.Constraint('UNIQUE(uuid)', "Identifiant de connexion en double.")

    # ── Ouverture ────────────────────────────────────────────────────────────

    @api.model
    def _check_client(self, client):
        Login = self.sudo()
        pending = [('expires_at', '>', fields.Datetime.now())]
        client_hash = hash_secret(client) if client else False
        if client_hash and Login.search_count(pending + [('client_hash', '=', client_hash)]) >= MAX_PENDING_PER_CLIENT:
            raise UserError(_("Trop de connexions en cours depuis cet appareil. Réessayez plus tard."))
        if Login.search_count(pending) >= MAX_PENDING_TOTAL:
            raise UserError(_("Trop de connexions en cours. Réessayez plus tard."))
        return client_hash

    @api.model
    def _open(self, email, user, step, device_name, client_hash):
        """Crée la ligne ; retourne ``(login, secret, code)``."""
        secret = secrets.token_urlsafe(32)
        code = f'{secrets.randbelow(10 ** 6):06d}'
        login = self.sudo().create({
            'email': email,
            'user_id': user.id if user else False,
            'step': step,
            'device_name': (device_name or '')[:64] or False,
            'code_hash': hash_secret(code) if step == 'email' else False,
            'secret_hash': hash_secret(secret),
            'client_hash': client_hash,
            'expires_at': fields.Datetime.now() + datetime.timedelta(minutes=CODE_MINUTES),
        })
        return login, secret, code

    @api.model
    def _api_request_code(self, email, device_name, client=None):
        """Code par courriel. Même réponse que l'adresse ait un compte ou non.

        Le courriel part seulement à un compte actif : le code si le compte peut ouvrir
        l'application, sinon la raison du refus (seul le titulaire de l'adresse la lit)."""
        email = email_normalize(email or '')
        if not email:
            raise ValidationError(_("Adresse courriel invalide."))
        client_hash = self._check_client(client)
        user = self._find_user(email)
        login, secret, code = self._open(email, user, 'email', device_name, client_hash)
        recent = self.sudo().search_count([
            ('email', '=', email), ('mail_sent', '=', True),
            ('create_date', '>', fields.Datetime.now() - datetime.timedelta(hours=1)),
        ])
        if user and recent < MAX_MAILS_PER_EMAIL_HOUR:
            login._send_mail(code, user._social_mobile_login_refusal())
        return login, secret

    @api.model
    def _api_password(self, email, password, device_name, client=None):
        """Connexion par mot de passe. Retourne ``(user, None, None)`` si elle est complète, ou
        ``(None, login, secret)`` quand un second code est exigé. AccessDenied sinon, toujours
        le même, que l'adresse ait un compte ou non."""
        email = email_normalize(email or '')
        if not email or not password:
            raise AccessDenied()
        Users = self.env['res.users'].sudo()
        # Identifiant du compte trouvé par courriel (il peut différer) ; sinon le courriel, qui
        # échoue comme un mauvais mot de passe.
        login = self._find_user(email).login or email
        auth_info = Users._login({'type': 'password', 'login': login, 'password': password},
                                 user_agent_env={'interactive': True})
        user = Users.browse(auth_info['uid'])
        mfa = user._mfa_type()
        if not mfa:
            return user, None, None
        client_hash = self._check_client(client)
        if mfa == 'totp':
            login, secret, _code = self._open(email, user, 'totp', device_name, client_hash)
            return None, login, secret
        if mfa == 'totp_mail':
            # Double authentification par courriel exigée : le code de l'application en tient lieu.
            login, secret, code = self._open(email, user, 'email', device_name, client_hash)
            login._send_mail(code, user._social_mobile_login_refusal())
            return None, login, secret
        raise UserError(_("Ce compte utilise une double authentification que l'application ne gère pas. "
                          "Contactez un administrateur du club."))

    @api.model
    def _find_user(self, email):
        """Compte actif dont l'identifiant est ``email`` ; sinon celui dont c'est l'adresse
        courriel (comptes administrateurs ou importés, à l'identifiant libre), s'il est le seul."""
        Users = self.env['res.users'].sudo()
        user = Users.search(Users._get_login_domain(email), order=Users._get_login_order(), limit=1)
        if user:
            return user
        users = Users.search([('partner_id.email_normalized', '=', email)], limit=2)
        return users if len(users) == 1 else Users.browse()

    def _send_mail(self, code, refusal):
        self.ensure_one()
        if refusal:
            subject = _("Connexion à l'application")
            body = Markup('<p>%s</p><p>%s</p>') % (
                refusal, _("Si vous n'avez pas tenté de vous connecter, ignorez ce courriel."))
        else:
            subject = _("Votre code de connexion")
            body = Markup('<p>%s</p><p style="font-size:28px;letter-spacing:6px;"><b>%s</b></p><p>%s</p>') % (
                _("Code à entrer dans l'application :"), escape(code),
                _("Il est valable %s minutes. Si vous n'avez pas demandé ce code, ignorez ce courriel.", CODE_MINUTES))
        company = self.env.company
        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': self.user_id.email_formatted or self.email,
            'email_from': company.email_formatted or company.partner_id.email_formatted,
            'auto_delete': True,
        })
        self.sudo().mail_sent = True
        # File d'envoi plutôt qu'un envoi immédiat : le temps de réponse ne trahit pas l'existence
        # du compte.
        self.env.ref('mail.ir_cron_mail_scheduler_action')._trigger()

    # ── Vérification ─────────────────────────────────────────────────────────

    @api.model
    def _api_find(self, login_uuid, secret):
        login = self.sudo().search([('uuid', '=', login_uuid or '')], limit=1)
        if (not login or login.expires_at <= fields.Datetime.now()
                or not hmac.compare_digest(login.secret_hash or '', hash_secret(secret))):
            return self.sudo().browse()
        return login

    def _api_verify(self, code):
        """Vérifie le code. Retourne le compte ; ``'totp'`` si un code de double authentification
        est encore exigé (même ligne) ; ``None`` si le code est faux (la ligne est effacée au
        dernier essai)."""
        self.ensure_one()
        login = self.sudo()
        code = (code or '').strip()
        if login.step == 'email':
            valid = bool(login.user_id) and bool(code) and hmac.compare_digest(login.code_hash or '', hash_secret(code))
        else:
            valid = login._check_totp(code)
        if not valid:
            login.attempts += 1
            if login.attempts >= MAX_ATTEMPTS:
                login.unlink()
            return None
        user = login.user_id
        if login.step == 'email' and user._mfa_type() == 'totp':
            # Le courriel ne suffit pas à qui a activé la double authentification.
            login.write({'step': 'totp', 'attempts': 0, 'code_hash': False})
            return 'totp'
        login.unlink()
        return user

    def _check_totp(self, code):
        user = self.user_id
        if not user or not code.isdigit():
            return False
        try:
            user.with_user(user).sudo()._check_credentials({'type': 'totp', 'token': int(code)}, {'interactive': True})
        except AccessDenied:
            return False
        return True

    # ── Nettoyage ────────────────────────────────────────────────────────────

    @api.model
    def _cron_purge(self):
        self.sudo().search([('expires_at', '<=', fields.Datetime.now())]).unlink()
