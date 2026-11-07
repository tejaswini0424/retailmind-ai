'use strict';
const form=document.getElementById('login-form');
const errorBox=document.getElementById('login-error');
const password=document.getElementById('password');
const toggle=document.getElementById('toggle-password');
let mode=new URLSearchParams(window.location.search).get('mode')==='register'?'register':'login';
function setMode(value){
  mode=value;const registration=mode==='register';errorBox.hidden=true;
  document.getElementById('auth-heading').textContent=registration?'Create your account':'Sign in to RetailMind';
  document.getElementById('auth-description').textContent=registration?'Start your own retail intelligence workspace.':'Enter your dashboard credentials to continue.';
  document.getElementById('login-submit').textContent=registration?'Create account →':'Sign in →';
  password.autocomplete=registration?'new-password':'current-password';
  document.getElementById('login-tab').classList.toggle('selected',!registration);document.getElementById('login-tab').setAttribute('aria-pressed',String(!registration));
  document.getElementById('register-tab').classList.toggle('selected',registration);document.getElementById('register-tab').setAttribute('aria-pressed',String(registration));
  document.getElementById('auth-switch').innerHTML=registration?'Already have an account? <button id="switch-mode" type="button">Login</button>':'New to RetailMind? <button id="switch-mode" type="button">Create an account</button>';
  document.getElementById('switch-mode').onclick=()=>setMode(registration?'login':'register');
  password.value='';
}
document.getElementById('login-tab').onclick=()=>setMode('login');
document.getElementById('register-tab').onclick=()=>setMode('register');
setMode(mode);
toggle.onclick=()=>{const visible=password.type==='password';password.type=visible?'text':'password';toggle.textContent=visible?'Hide':'Show';toggle.setAttribute('aria-label',visible?'Hide password':'Show password');toggle.setAttribute('aria-pressed',String(visible));};
form.onsubmit=async event=>{
  event.preventDefault();errorBox.hidden=true;const button=document.getElementById('login-submit');button.disabled=true;button.textContent=mode==='register'?'Creating account…':'Signing in…';
  try{
    const response=await fetch('/api/index',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:mode,username:document.getElementById('username').value.trim(),password:password.value})});
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Could not sign in. Please try again.');
    password.value='';window.location.replace('/');
  }catch(error){errorBox.textContent=error.message;errorBox.hidden=false;password.value='';password.focus();}
  finally{button.disabled=false;button.textContent=mode==='register'?'Create account →':'Sign in →';}
};
if(mode!=='register')fetch('/api/index',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'session'})}).then(response=>{if(response.ok&&mode==='login')window.location.replace('/');}).catch(()=>{});
