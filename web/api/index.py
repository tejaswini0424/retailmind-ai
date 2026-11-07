"""Stateless Vercel HTTP adapter around the original Python analytics engine."""
import base64
from functools import lru_cache
from http.server import BaseHTTPRequestHandler
from io import BytesIO
import json
from pathlib import Path
import sys
import os
from collections import OrderedDict
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / 'retailmind').exists():
    ROOT = ROOT.parent
if (ROOT / 'retailmind').exists():
    sys.path.insert(0, str(ROOT))
if (ROOT / '.local-packages').exists():
    sys.path.insert(0, str(ROOT / '.local-packages'))

import pandas as pd
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from retailmind.auth import AuthError, current_user, sign_in, register, session_cookie
from retailmind.data import REQUIRED, clean_data, generate_sample
from retailmind.analytics import metrics, aggregate, trends, customers, product_changes
from retailmind.assistant import EXAMPLES, answer
from retailmind.rag import Retriever

MAX_BYTES = 4_000_000
MAX_ROWS = 10000
LOGIN_ATTEMPTS = OrderedDict()
LOGIN_LOCK = threading.Lock()

def authorize_request(body, headers, secure=True, client_ip='local'):
    """Enforce auth at the HTTP boundary before any business computation."""
    action = body.get('action','analytics')
    if headers.get('Origin'):
        origin = urlsplit(headers['Origin'])
        if origin.netloc != headers.get('Host') or origin.scheme not in ('https','http'):
            raise AuthError('Request origin is not allowed.',403)
    if action in ('login','register'):
        now = time.time()
        with LOGIN_LOCK:
            recent = [t for t in LOGIN_ATTEMPTS.get(client_ip,[]) if t>now-600]
            if len(recent)>=10:
                raise AuthError('Too many login attempts. Please try again in 10 minutes.',429)
            recent.append(now)
            LOGIN_ATTEMPTS[client_ip] = recent
            LOGIN_ATTEMPTS.move_to_end(client_ip)
            while len(LOGIN_ATTEMPTS)>5000:
                LOGIN_ATTEMPTS.popitem(last=False)
        if action=='register':
            token,user=register(body.get('username',''),body.get('password',''))
        else:
            token, user = sign_in(body.get('username',''),body.get('password',''))
        with LOGIN_LOCK:
            LOGIN_ATTEMPTS.pop(client_ip,None)
        return {'user':user}, session_cookie(token,secure)
    if action == 'logout':
        return {'message':'You have been logged out.'}, session_cookie(secure=secure)
    user = current_user(headers.get('Cookie',''))
    if action == 'session':
        return {'user':user}, None
    return None, None

def records(frame):
    return json.loads(frame.to_json(orient='records', date_format='iso'))

@lru_cache(maxsize=2)
def demo(day):
    return clean_data(generate_sample(5000))[0]

def frame_for(body):
    if body.get('rows') is None:
        frame = demo(str(pd.Timestamp.now().date())).copy()
    else:
        raw = body['rows']
        if not isinstance(raw, list) or len(raw) > MAX_ROWS:
            raise ValueError(f'Datasets must contain at most {MAX_ROWS:,} rows.')
        frame, _, _ = clean_data(pd.DataFrame(raw))
    filters = body.get('filters') or {}
    for column in ['region','category','store_id']:
        if filters.get(column):
            frame = frame.loc[frame[column].isin(filters[column])]
    if filters.get('start'):
        frame = frame.loc[frame.date >= filters['start']]
    if filters.get('end'):
        frame = frame.loc[frame.date <= filters['end']]
    return frame

def dispatch(body):
    action = body.get('action','analytics')
    if action == 'health':
        return {'status':'ok','service':'RetailMind AI','mode':'Vercel Python API'}
    if action == 'demo':
        frame = demo(str(pd.Timestamp.now().date()))
        return {'rows':records(frame),'name':'Demo · synthetic retail transactions','examples':EXAMPLES}
    if action == 'upload':
        content = base64.b64decode(body.get('content',''), validate=True)
        if len(content)>2_500_000:
            raise ValueError('Use a file smaller than 2.5 MB.')
        name = str(body.get('name','')).lower()
        stream = BytesIO(content)
        if name.endswith('.csv'):
            raw = pd.read_csv(stream, nrows=MAX_ROWS+1)
        elif name.endswith('.xlsx'):
            workbook = pd.ExcelFile(stream,engine='openpyxl')
            sheet = body.get('sheet', workbook.sheet_names[0])
            if body.get('list_sheets'):
                return {'sheets':workbook.sheet_names}
            raw = pd.read_excel(workbook,sheet_name=sheet,nrows=MAX_ROWS+1)
        else:
            raise ValueError('Choose a CSV or XLSX file.')
        if len(raw)>MAX_ROWS:
            raise ValueError(f'The web version accepts at most {MAX_ROWS:,} rows per dataset.')
        frame, report, rejected = clean_data(raw)
        if frame.empty:
            raise ValueError('No valid records remain after cleaning.')
        rows = records(frame)
        # Leave room for JSON request overhead on every subsequent analysis request.
        if len(json.dumps(rows).encode())>3_600_000:
            raise ValueError('Cleaned dataset is too large for web analysis; upload a smaller file.')
        return {'rows':rows,'report':report,'rejected':records(rejected),'preview':records(frame.head(30))}
    frame = frame_for(body)
    if frame.empty:
        raise ValueError('No records match the filters. Choose a wider date range or clear filters.')
    if action == 'ask':
        question = str(body.get('question','')).strip()
        if not question or len(question)>1000:
            raise ValueError('Enter a question between 1 and 1,000 characters.')
        name = str(body.get('dataset_name','Selected dataset'))[:150]
        retriever = Retriever(frame,name)
        result = answer(question,frame,retriever,None,None)
        result['data'] = records(result['data'])
        result['retrieval_mode'] = retriever.mode
        return result
    if action == 'customers':
        result = customers(frame)
        return {'rows':records(result),'count':len(result),'repeat':int((result.orders>1).sum()),'repeat_rate':float((result.orders>1).mean()*100)}
    if action != 'analytics':
        raise ValueError('Unknown action.')
    return {
        'metrics':metrics(frame), 'row_count':len(frame),
        'monthly':records(trends(frame)), 'daily':records(trends(frame,'D')), 'weekly':records(trends(frame,'W')),
        'stores':records(aggregate(frame,'store_id')), 'regions':records(aggregate(frame,'region','profit')),
        'categories':records(aggregate(frame,'category')), 'category_profit':records(aggregate(frame,'category','profit')),
        'products':records(aggregate(frame,'product_name')), 'demand':records(aggregate(frame,'product_name','quantity')),
        'product_profit':records(aggregate(frame,'product_name','profit')), 'changes':records(product_changes(frame)),
        'preview':records(frame.head(50)), 'examples':EXAMPLES,
    }

class handler(BaseHTTPRequestHandler):
    def send_json(self, status, payload, cookie=None):
        encoded = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.send_header('Content-Length',str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        self.send_json(200,dispatch({'action':'health'}))

    def do_POST(self):
        try:
            if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
                return self.send_json(415,{'error':'Use an application/json request.'})
            size = int(self.headers.get('Content-Length','0'))
            if size<=0 or size>MAX_BYTES:
                return self.send_json(413,{'error':'Request exceeds the 4 MB web limit. Use a smaller dataset.'})
            body = json.loads(self.rfile.read(size))
            if not isinstance(body,dict):
                raise ValueError('Request must be a JSON object.')
            secure = bool(os.getenv('VERCEL')) or self.headers.get('X-Forwarded-Proto')=='https'
            client_ip = self.headers.get('X-Vercel-Forwarded-For',self.client_address[0]).split(',')[0]
            result,cookie = authorize_request(body,self.headers,secure,client_ip)
            self.send_json(200,dispatch(body) if result is None else result,cookie)
        except AuthError as exc:
            self.send_json(exc.status,{'error':str(exc)})
        except (ValueError,KeyError,TypeError,pd.errors.ParserError) as exc:
            self.send_json(400,{'error':str(exc)})
        except Exception:
            self.send_json(500,{'error':'Could not process this dataset. Verify the file format and try again.'})
