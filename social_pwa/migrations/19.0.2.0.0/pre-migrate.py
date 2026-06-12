"""social_pwa.subscription → mail.push.device.

Migre les clés VAPID custom (social_pwa.vapid_*) vers les paramètres
standard (mail.web_push_vapid_*) et copie les abonnements existants vers
mail.push.device, pour que les abonnés ne perdent pas leur push.

Si la clé privée configurée n'est pas convertible vers le format attendu
par l'outil jwt d'Odoo (scalaire P-256 brut en base64url), on ne migre
rien : le standard régénérera une paire et le front re-souscrira
silencieusement au prochain passage (rotation gérée dans pwa_register.js).
"""
import base64
import logging

_logger = logging.getLogger(__name__)


def _b64url_decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def _b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).decode('ascii').strip('=')


def _private_key_to_raw(value):
    """Retourne le scalaire privé P-256 (32 octets) ou None."""
    value = (value or '').strip()
    if not value:
        return None
    try:
        raw = _b64url_decode(value)
        if len(raw) == 32:
            return raw
    except Exception:
        raw = None
    try:
        from cryptography.hazmat.primitives import serialization
        if value.startswith('-----BEGIN'):
            key = serialization.load_pem_private_key(value.encode(), password=None)
        else:
            key = serialization.load_der_private_key(_b64url_decode(value), password=None)
        return key.private_numbers().private_value.to_bytes(32, 'big')
    except Exception:
        return None


def _derive_public(raw_private):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.derive_private_key(int.from_bytes(raw_private, 'big'), ec.SECP256R1())
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )


def _get_param(cr, key):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", (key,))
    row = cr.fetchone()
    return row[0] if row else None


def _set_param(cr, key, value):
    cr.execute("""
        INSERT INTO ir_config_parameter (key, value, create_date, write_date)
        VALUES (%s, %s, now(), now())
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, write_date = now()
    """, (key, value))


def migrate(cr, version):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'social_pwa_subscription'")
    if not cr.fetchone():
        return

    if _get_param(cr, 'mail.web_push_vapid_private_key'):
        _logger.info('social_pwa: mail VAPID keys already set, subscriptions not migrated')
        return

    raw = _private_key_to_raw(_get_param(cr, 'social_pwa.vapid_private_key'))
    if not raw:
        _logger.warning(
            'social_pwa: VAPID private key absent or unconvertible — '
            'subscriptions dropped, browsers will resubscribe on next visit')
        return

    _set_param(cr, 'mail.web_push_vapid_private_key', _b64url_encode(raw))
    _set_param(cr, 'mail.web_push_vapid_public_key', _b64url_encode(_derive_public(raw)))

    cr.execute("""
        INSERT INTO mail_push_device
            (partner_id, endpoint, keys, create_uid, create_date, write_uid, write_date)
        SELECT u.partner_id, s.endpoint,
               json_build_object('p256dh', s.p256dh, 'auth', s.auth)::text,
               1, now(), 1, now()
        FROM social_pwa_subscription s
        JOIN res_users u ON u.id = s.user_id
        WHERE u.partner_id IS NOT NULL
        ON CONFLICT (endpoint) DO NOTHING
    """)
    _logger.info('social_pwa: %s subscription(s) migrated to mail.push.device', cr.rowcount)

    cr.execute("""
        DELETE FROM ir_config_parameter
        WHERE key IN ('social_pwa.vapid_private_key',
                      'social_pwa.vapid_public_key',
                      'social_pwa.vapid_sub')
    """)
