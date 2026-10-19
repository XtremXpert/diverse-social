"""Client FCM minimal (Firebase Cloud Messaging, API HTTP v1) pour les téléphones Android.

Authentification par compte de service Google : une assertion JWT RS256 signée par sa clé privée
s'échange contre un jeton d'accès OAuth 2 d'une heure, réutilisé jusqu'à cinq minutes de son
échéance. Les messages sont des messages de données seulement : l'application construit elle-même
la notification, et Google ne voit passer que le texte discret (« Nouveau message »).
"""
import json
import threading
import time

import jwt

SCOPE = 'https://www.googleapis.com/auth/firebase.messaging'
TOKEN_URI = 'https://oauth2.googleapis.com/token'
SEND_URL = 'https://fcm.googleapis.com/v1/projects/%s/messages:send'
TOKEN_MARGIN = 5 * 60

_token_cache = {}
_token_lock = threading.Lock()


def parse_service_account(text):
    """Compte de service (fichier JSON téléchargé de la console Google Cloud), ou ``None``."""
    try:
        account = json.loads(text or '')
    except ValueError:
        return None
    if not isinstance(account, dict):
        return None
    if not all(account.get(k) for k in ('project_id', 'client_email', 'private_key')):
        return None
    return account


def assertion(account, now=None):
    """Assertion JWT RS256 du compte de service, à échanger contre un jeton d'accès."""
    now = int(now or time.time())
    claims = {
        'iss': account['client_email'],
        'scope': SCOPE,
        'aud': account.get('token_uri') or TOKEN_URI,
        'iat': now,
        'exp': now + 3600,
    }
    headers = {'kid': account['private_key_id']} if account.get('private_key_id') else None
    return jwt.encode(claims, account['private_key'], algorithm='RS256', headers=headers)


def _cache_key(account):
    return (account['client_email'], hash(account['private_key']))


def access_token(client, account, now=None):
    """Jeton d'accès OAuth 2, mis en cache par compte de service."""
    now = int(now or time.time())
    key = _cache_key(account)
    with _token_lock:
        cached = _token_cache.get(key)
        if cached and now < cached[1] - TOKEN_MARGIN:
            return cached[0]
    response = client.post(account.get('token_uri') or TOKEN_URI, data={
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': assertion(account, now),
    })
    response.raise_for_status()
    body = response.json()
    token = body['access_token']
    with _token_lock:
        _token_cache[key] = (token, now + int(body.get('expires_in', 3600)))
    return token


def forget_token(account):
    with _token_lock:
        _token_cache.pop(_cache_key(account), None)


def post(client, project_id, token, message):
    """Envoie un message. Retourne ``(statut HTTP, code d'erreur FCM ou None)``."""
    response = client.post(SEND_URL % project_id, json={'message': message},
                           headers={'authorization': f'Bearer {token}'})
    if response.status_code == 200:
        return 200, None
    code = None
    try:
        error = response.json().get('error') or {}
        code = error.get('status')
        for detail in error.get('details') or []:
            code = detail.get('errorCode') or code
    except ValueError:
        pass
    return response.status_code, code
