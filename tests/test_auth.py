from http.cookies import SimpleCookie
import bcrypt
import pytest
from retailmind.auth import AuthError, current_user, sign_in, session_cookie, COOKIE_NAME, SESSION_SECONDS
from web.api.index import authorize_request

@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv('AUTH_USERNAME','test-admin')
    monkeypatch.setenv('AUTH_PASSWORD_HASH',bcrypt.hashpw(b'correct-test-password',bcrypt.gensalt(rounds=4)).decode())
    monkeypatch.setenv('AUTH_SESSION_SECRET','test-secret-not-for-production-'*3)

def test_login_expiry_and_tampering():
    token,user=sign_in('test-admin','correct-test-password',now=1000)
    cookie=f'{COOKIE_NAME}={token}'
    assert current_user(cookie,now=1001)==user
    assert 'test-admin'==user['username']
    for value in ['',cookie+'tampered']:
        with pytest.raises(AuthError):current_user(value,now=1001)
    with pytest.raises(AuthError):current_user(cookie,now=1000+SESSION_SECONDS)
    with pytest.raises(AuthError):current_user(cookie,now=999)

def test_incorrect_credentials():
    for username,password in [('test-admin','wrong'),('someone','correct-test-password'),('test-admin','x'*73)]:
        with pytest.raises(AuthError):sign_in(username,password)

def test_cookie_flags_and_logout():
    token,_=sign_in('test-admin','correct-test-password')
    cookie=session_cookie(token)
    assert all(flag in cookie for flag in ['HttpOnly','Secure','SameSite=Strict','Max-Age=28800','Path=/'])
    assert 'Max-Age=0' in session_cookie()
    result,expired=authorize_request({'action':'logout'},{})
    assert 'logged out' in result['message']
    assert 'Max-Age=0' in expired

def test_backend_requires_authentication():
    for action in ['analytics','demo','ask','customers','upload','session']:
        with pytest.raises(AuthError):authorize_request({'action':action},{})
    response,cookie=authorize_request({'action':'login','username':'test-admin','password':'correct-test-password'},{},client_ip='auth-test')
    parsed=SimpleCookie();parsed.load(cookie)
    headers={'Cookie':f'{COOKIE_NAME}={parsed[COOKIE_NAME].value}'}
    assert authorize_request({'action':'session'},headers)[0]['user']==response['user']
    assert authorize_request({'action':'analytics'},headers)==(None,None)

def test_origin_and_missing_configuration(monkeypatch):
    with pytest.raises(AuthError) as cross_origin:
        authorize_request({'action':'logout'},{'Origin':'https://other.example','Host':'retailmind.example'})
    assert cross_origin.value.status==403
    monkeypatch.delenv('AUTH_SESSION_SECRET')
    with pytest.raises(AuthError) as unconfigured:current_user('')
    assert unconfigured.value.status==503

def test_failed_login_rate_limit():
    for _ in range(10):
        with pytest.raises(AuthError):authorize_request({'action':'login','username':'test-admin','password':'wrong'},{},client_ip='rate-test')
    with pytest.raises(AuthError) as limited:
        authorize_request({'action':'login','username':'test-admin','password':'wrong'},{},client_ip='rate-test')
    assert limited.value.status==429

def test_password_change_revokes_sessions(monkeypatch):
    token,_=sign_in('test-admin','correct-test-password')
    monkeypatch.setenv('AUTH_PASSWORD_HASH',bcrypt.hashpw(b'new-test-password',bcrypt.gensalt(rounds=4)).decode())
    with pytest.raises(AuthError):current_user(f'{COOKIE_NAME}={token}')
