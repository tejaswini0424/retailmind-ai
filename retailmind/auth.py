"""Password verification and signed, expiring dashboard session cookies."""
import base64
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
import json
import os
import secrets
import time
import re

import bcrypt
from .accounts import AccountStore, AccountStoreError, DuplicateAccount

COOKIE_NAME = 'retailmind_session'
SESSION_SECONDS = 8 * 60 * 60

class AuthError(Exception):
    def __init__(self, message='Please log in to continue.', status=401):
        super().__init__(message)
        self.status = status

def settings():
    username = os.getenv('AUTH_USERNAME', '').strip().lower()
    password_hash = os.getenv('AUTH_PASSWORD_HASH', '')
    secret = os.getenv('AUTH_SESSION_SECRET', '')
    if not username or not password_hash or len(secret) < 32:
        raise AuthError('Dashboard login is not configured. Contact the project owner.',503)
    # Password changes also invalidate existing sessions.
    key = hmac.new(secret.encode(), password_hash.encode(), hashlib.sha256).digest()
    return username, password_hash, key

def public_user(username):
    return {'username': username, 'id': hashlib.sha256(username.encode()).hexdigest()[:32]}

def password_material(password):
    # Hash the full UTF-8 password before bcrypt, avoiding bcrypt's 72-byte limit.
    return base64.b64encode(hashlib.sha256(password.encode()).digest())

def encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def sign_in(username, password, now=None):
    configured, password_hash, secret = settings()
    username=str(username).strip().lower()
    if not username or not str(password):
        raise AuthError('Incorrect username or password.')
    user=public_user(configured)
    scheme='bcrypt'
    if username != configured:
        try:
            record=AccountStore().get(username)
        except AccountStoreError as exc:
            raise AuthError(str(exc),503) from exc
        if record:
            password_hash=record['password_hash']
            user=public_user(username)
            scheme=record.get('password_scheme','bcrypt')
        else:
            user=None
    # Check the password even for unknown usernames to avoid a username timing oracle.
    raw = password_material(str(password)) if scheme=='bcrypt-sha256' else str(password).encode()
    try:
        valid_password = 1 <= len(raw) <= 72 and bcrypt.checkpw(raw,password_hash.encode())
    except ValueError:
        raise AuthError('Dashboard login is not configured. Contact the project owner.',503)
    if user is None or not valid_password:
        raise AuthError('Incorrect username or password.')
    return issue_session(user,secret,now)

def issue_session(user, secret, now=None):
    issued = int(time.time() if now is None else now)
    payload = encode(json.dumps({'sub':hashlib.sha256(user['username'].encode()).hexdigest(),'v':2,'iat':issued,'exp':issued+SESSION_SECONDS,'nonce':secrets.token_urlsafe(18)},separators=(',',':')).encode())
    signature = encode(hmac.new(secret,payload.encode(),hashlib.sha256).digest())
    return payload+'.'+signature, user

def register(username, password, now=None):
    configured,_,secret=settings()
    username=str(username).strip().lower()
    password=str(password)
    if not username or not password:
        raise AuthError('Enter a username and password.',400)
    if username==configured:
        raise AuthError('That username is unavailable. Choose another.',409)
    record={'username':username,'password_hash':bcrypt.hashpw(password_material(password),bcrypt.gensalt(rounds=12)).decode(),'password_scheme':'bcrypt-sha256','created_at':int(time.time())}
    try:
        AccountStore().create(record)
    except DuplicateAccount as exc:
        raise AuthError('That username is unavailable. Choose another.',409) from exc
    except AccountStoreError as exc:
        raise AuthError(str(exc),503) from exc
    return issue_session(public_user(username),secret,now)

def current_user(cookie_header, now=None):
    username, _, secret = settings()
    try:
        cookies = SimpleCookie()
        cookies.load(cookie_header or '')
        token = cookies[COOKIE_NAME].value
        if len(token)>2048:
            raise ValueError('Oversize token')
        payload, supplied = token.split('.')
        expected = encode(hmac.new(secret,payload.encode(),hashlib.sha256).digest())
        if not hmac.compare_digest(supplied,expected):
            raise ValueError('Invalid signature')
        data = json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        clock = int(time.time() if now is None else now)
        if not isinstance(data['sub'],str) or not data['sub'] or not data['iat'] <= clock < data['exp'] or data['exp']-data['iat'] != SESSION_SECONDS:
            raise ValueError('Expired or invalid session')
        if data.get('v')==2 and not re.fullmatch(r'[0-9a-f]{64}',data['sub']):
            raise ValueError('Invalid account identifier')
    except (KeyError,ValueError,TypeError,AttributeError,CookieError):
        raise AuthError()
    version2=data.get('v')==2
    if data['sub']==(hashlib.sha256(username.encode()).hexdigest() if version2 else username):
        return public_user(username)
    try:
        store=AccountStore()
        record=store.get_by_id(data['sub']) if version2 else store.get(data['sub'])
    except AccountStoreError as exc:
        raise AuthError(str(exc),503) from exc
    if not record:
        raise AuthError()
    return public_user(record['username'])

def session_cookie(token='', secure=True):
    cookie = SimpleCookie()
    cookie[COOKIE_NAME] = token
    value = cookie[COOKIE_NAME]
    value['path'] = '/'
    value['httponly'] = True
    value['samesite'] = 'Strict'
    value['max-age'] = SESSION_SECONDS if token else 0
    if not token:
        value['expires'] = 'Thu, 01 Jan 1970 00:00:00 GMT'
    if secure:
        value['secure'] = True
    return value.OutputString()
