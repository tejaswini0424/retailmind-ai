"""Immutable account records: private Vercel Blob in cloud, SQLite locally."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3

class AccountStoreError(Exception):
    pass

class DuplicateAccount(Exception):
    pass

class AccountStore:
    def __init__(self):
        self.cloud = bool(os.getenv('VERCEL'))
        if not self.cloud:
            self.path = Path(os.getenv('AUTH_DATABASE_PATH',Path(__file__).resolve().parents[1]/'data'/'accounts.db'))
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with sqlite3.connect(self.path) as conn:
                conn.execute('CREATE TABLE IF NOT EXISTS accounts (username TEXT PRIMARY KEY, record TEXT NOT NULL)')

    def key(self, username):
        return 'accounts/'+hashlib.sha256(username.encode()).hexdigest()+'.json'

    def get(self, username):
        return self.get_by_id(hashlib.sha256(username.encode()).hexdigest())

    def get_by_id(self, account_id):
        if not self.cloud:
            with sqlite3.connect(self.path) as conn:
                conn.create_function('account_digest',1,lambda value:hashlib.sha256(value.encode()).hexdigest())
                row = conn.execute('SELECT record FROM accounts WHERE account_digest(username)=?',(account_id,)).fetchone()
            return json.loads(row[0]) if row else None
        from vercel.blob import sync as blob
        from vercel.blob import BlobError, BlobNotFoundError
        try:
            return json.loads(blob.get_blob('accounts/'+account_id+'.json',access='private').body)
        except BlobNotFoundError:
            return None
        except (BlobError,ValueError) as exc:
            raise AccountStoreError('Account storage is temporarily unavailable.') from exc

    def create(self, record):
        encoded=json.dumps(record,separators=(',',':'))
        if not self.cloud:
            try:
                with sqlite3.connect(self.path) as conn:
                    conn.execute('INSERT INTO accounts(username,record) VALUES (?,?)',(record['username'],encoded))
            except sqlite3.IntegrityError as exc:
                raise DuplicateAccount() from exc
            return
        from vercel.blob import sync as blob
        from vercel.blob import BlobError
        try:
            # A fixed path and disabled overwrites make username claiming atomic.
            blob.put_blob(self.key(record['username']),encoded.encode(),access='private',content_type='application/json',add_random_suffix=False,allow_overwrite=False,cache_control_max_age=60)
        except BlobError as exc:
            if exc.status_code==409 or 'already exists' in str(exc).lower():
                raise DuplicateAccount() from exc
            raise AccountStoreError('Account storage is temporarily unavailable.') from exc
