from concurrent.futures import ThreadPoolExecutor
import bcrypt
import pytest
from retailmind.auth import AuthError, COOKIE_NAME, current_user, password_material, register, sign_in
from retailmind.accounts import AccountStore, DuplicateAccount
from web.api.index import authorize_request

@pytest.fixture(autouse=True)
def local_accounts(monkeypatch,tmp_path):
    monkeypatch.delenv('VERCEL',raising=False)
    monkeypatch.setenv('AUTH_DATABASE_PATH',str(tmp_path/'accounts.db'))
    monkeypatch.setenv('AUTH_USERNAME','admin')
    monkeypatch.setenv('AUTH_PASSWORD_HASH',bcrypt.hashpw(b'admin-test-password',bcrypt.gensalt(rounds=4)).decode())
    monkeypatch.setenv('AUTH_SESSION_SECRET','registration-test-secret-'*3)

def test_registration_persistence_login_and_session():
    token,user=register(' New_User ','p')
    assert user['username']=='new_user' and 'name' not in user
    stored=AccountStore().get('new_user')
    assert 'name' not in stored
    assert bcrypt.checkpw(password_material('p'),stored['password_hash'].encode())
    assert current_user(f'{COOKIE_NAME}={token}')==user
    assert sign_in('NEW_USER','p')[1]==user
    with pytest.raises(AuthError):sign_in('new_user','wrong-password')

def test_duplicates_cannot_overwrite_account():
    register('retailer','first-password')
    with pytest.raises(AuthError) as duplicate:register('RETAILER','second-password')
    assert duplicate.value.status==409
    assert sign_in('retailer','first-password')[1]['username']=='retailer'
    with pytest.raises(AuthError):sign_in('retailer','second-password')
    with pytest.raises(AuthError):register('admin','a')

@pytest.mark.parametrize('username,password',[
    ('x','1'),('a b!@','a'),('व्यापारी','é'*100),('../bad','p'),('long-user-'*200,'p'*5000),
])
def test_no_username_format_or_password_length_rules(username,password):
    token,user=register(username,password)
    assert current_user(f'{COOKIE_NAME}={token}')==user
    assert len(token)<1000
    assert sign_in(username,password)[1]==user
    with pytest.raises(AuthError):sign_in(username,password+'different')

@pytest.mark.parametrize('username,password',[('','x'),('   ','x'),('x','')])
def test_fields_must_be_provided(username,password):
    with pytest.raises(AuthError) as rejected:register(username,password)
    assert rejected.value.status==400

def test_existing_password_hashes_still_work():
    AccountStore().create({'username':'legacy','name':'Old Display Name','password_hash':bcrypt.hashpw(b'old-password',bcrypt.gensalt(rounds=4)).decode()})
    assert sign_in('legacy','old-password')[1]['username']=='legacy'

def test_atomic_username_claim():
    store=AccountStore()
    def claim(i):
        try:store.create({'username':'same_name','value':i});return True
        except DuplicateAccount:return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(claim,range(4)))==1

def test_registration_http_boundary():
    response,cookie=authorize_request({'action':'register','username':'u','password':'p'},{},client_ip='registration-test')
    assert response['user']['username']=='u'
    assert 'HttpOnly' in cookie
