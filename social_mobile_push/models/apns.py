"""Client APNs minimal : jeton de fournisseur ES256 (clé .p8) et requête HTTP/2.

Apple n'accepte que HTTP/2 (httpx + h2). Le jeton de fournisseur est réutilisé environ 45 minutes :
le régénérer trop souvent fait répondre ``TooManyProviderTokenUpdates``.
"""
import json
import threading
import time

import jwt

HOSTS = {
    'production': 'https://api.push.apple.com',
    'sandbox': 'https://api.sandbox.push.apple.com',
}
TOKEN_TTL = 45 * 60

_token_cache = {}
_token_lock = threading.Lock()


def provider_token(team_id, key_id, private_key, now=None):
    """Jeton ES256 signé par la clé .p8, mis en cache par (équipe, clé)."""
    now = int(now or time.time())
    cache_key = (team_id, key_id, hash(private_key))
    with _token_lock:
        cached = _token_cache.get(cache_key)
        if cached and now - cached[1] < TOKEN_TTL:
            return cached[0]
        token = jwt.encode({'iss': team_id, 'iat': now}, private_key, algorithm='ES256', headers={'kid': key_id})
        _token_cache[cache_key] = (token, now)
        return token


def forget_token(team_id, key_id, private_key):
    with _token_lock:
        _token_cache.pop((team_id, key_id, hash(private_key)), None)


def post(client, environment, device_token, topic, provider_jwt, payload, collapse_id=None):
    """Envoie une notification. Retourne ``(statut HTTP, raison Apple ou None)``."""
    headers = {
        'authorization': f'bearer {provider_jwt}',
        'apns-topic': topic,
        'apns-push-type': 'alert',
        'apns-priority': '10',
    }
    if collapse_id:
        headers['apns-collapse-id'] = collapse_id[:64]
    response = client.post(f"{HOSTS[environment]}/3/device/{device_token}",
                           content=json.dumps(payload, ensure_ascii=False).encode(), headers=headers)
    reason = None
    if response.status_code != 200:
        try:
            reason = response.json().get('reason')
        except ValueError:
            reason = None
    return response.status_code, reason
