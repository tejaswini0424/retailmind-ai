"""Upload project auth settings to Vercel through stdin, without printing values."""
import os
from pathlib import Path
import shutil
import subprocess
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
values=dotenv_values(ROOT/'.env')
npm=shutil.which('npm.cmd') or shutil.which('npm')
if not npm:raise SystemExit('npm is required.')
environment=dict(os.environ,NODE_USE_SYSTEM_CA='1',npm_config_cache=str(ROOT/'.test-tmp'/'npm-vercel'))
for key in ['AUTH_USERNAME','AUTH_PASSWORD_HASH','AUTH_SESSION_SECRET']:
    value=values.get(key)
    if not value:raise SystemExit(f'Missing {key}. Run scripts/configure_auth.py first.')
    result=subprocess.run([npm,'exec','--yes','--package=vercel','--','vercel','env','add',key,'--environment','production','--sensitive','--force','--yes','--cwd',str(ROOT/'.vercel-deploy')],input=value,encoding='utf-8',capture_output=True,env=environment)
    if result.returncode:
        # Do not echo CLI output: configuration values must not enter logs.
        raise SystemExit(f'Could not configure {key}; inspect Vercel project environment settings.')
    print(f'Configured {key} as a Vercel secret.',flush=True)
