"""Create a clean deployment containing only the web app and Python engine."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / '.vercel-deploy'
target.mkdir(exist_ok=True)
shutil.copytree(ROOT/'web',target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
shutil.copytree(ROOT/'retailmind',target/'retailmind',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
(target/'.python-version').write_text('3.12\n')
(target/'.vercelignore').write_text('__pycache__/\n*.pyc\n')
print(f'Vercel deployment prepared: {target}')
