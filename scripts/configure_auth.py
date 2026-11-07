"""Create project-local credentials once. Never print secrets to the terminal."""
from pathlib import Path
import os
import secrets
import bcrypt
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'.env'
existing=dotenv_values(path) if path.exists() else {}
username=existing.get('AUTH_USERNAME') or 'admin'
password=secrets.token_urlsafe(18)
values={
    'AUTH_USERNAME':username,
    'AUTH_PASSWORD_HASH':existing.get('AUTH_PASSWORD_HASH') or bcrypt.hashpw(password.encode(),bcrypt.gensalt(rounds=12)).decode(),
    'AUTH_SESSION_SECRET':existing.get('AUTH_SESSION_SECRET') or secrets.token_urlsafe(48),
}
new_account=not existing.get('AUTH_PASSWORD_HASH')
with path.open('a',encoding='utf-8') as file:
    for key,value in values.items():
        if not existing.get(key):file.write(f'\n{key}={value}\n')
if new_account:
    details=ROOT/'LOGIN_CREDENTIALS.txt'
    details.write_text(f'RetailMind AI dashboard\n\nURL: https://retailmind-ai-zeta.vercel.app\nUsername: {username}\nPassword: {password}\n\nKeep this file private. Credentials are not included in the deployment files.\n',encoding='utf-8')
    print('Created credentials in LOGIN_CREDENTIALS.txt (git-ignored).')
else:print('Existing dashboard account preserved.')
