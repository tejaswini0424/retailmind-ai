from pathlib import Path
import re
import sqlite3
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

REQUIRED = ['transaction_id', 'date', 'store_id', 'product_id', 'category', 'product_name', 'quantity', 'unit_price', 'total_sales', 'discount', 'customer_id', 'region', 'payment_method', 'profit']

def generate_sample(rows=5000, seed=42):
    rng = np.random.default_rng(seed)
    products = [('Electronics', 'Wireless Headphones', 2400), ('Electronics', 'Smart Speaker', 3800), ('Home', 'Desk Lamp', 950), ('Home', 'Storage Basket', 450), ('Grocery', 'Coffee Beans', 620), ('Grocery', 'Organic Tea', 280), ('Fashion', 'Cotton Shirt', 1200), ('Fashion', 'Running Shoes', 2800), ('Beauty', 'Face Serum', 850), ('Beauty', 'Shampoo', 340)]
    p = rng.integers(0, len(products), rows)
    stores = rng.integers(0, 6, rows)
    dates = pd.Timestamp.today().normalize() - pd.to_timedelta(rng.integers(0, 365, rows), unit='D')
    quantity = rng.integers(1, 7, rows)
    price = np.array([products[i][2] for i in p], dtype=float)
    discount = rng.choice([0, .05, .10, .15], rows)
    sales = np.round(quantity * price * (1-discount), 2)
    return pd.DataFrame(dict(transaction_id=[f'T{i+1:07}' for i in range(rows)], date=dates.strftime('%Y-%m-%d'), store_id=[f'S{i+1:02}' for i in stores], product_id=[f'P{i+1:03}' for i in p], category=[products[i][0] for i in p], product_name=[products[i][1] for i in p], quantity=quantity, unit_price=price, total_sales=sales, discount=discount, customer_id=[f'C{i:04}' for i in rng.integers(1, max(2, rows//3), rows)], region=[['North','South','East','West','North','South'][i] for i in stores], payment_method=rng.choice(['UPI','Card','Cash'], rows, p=[.5,.35,.15]), profit=np.round(sales-price*quantity*rng.uniform(.52,.78,rows),2)))

def clean_data(raw):
    df = raw.copy()
    df.columns = [re.sub(r'[^a-z0-9]+', '_', str(c).strip().lower()).strip('_') for c in df.columns]
    df = df.rename(columns={'product_category':'category', 'total_sale':'total_sales'})
    if df.columns.duplicated().any():
        raise ValueError('Column names collide after normalization.')
    missing = sorted(set(REQUIRED)-set(df.columns))
    if missing:
        raise ValueError('Missing required columns: ' + ', '.join(missing))
    df = df[REQUIRED].copy()
    before = len(df)
    missing_cells = int(df.isna().sum().sum())
    df = df.drop_duplicates()
    duplicates = before-len(df)
    df['date'] = pd.to_datetime(df['date'], errors='coerce', utc=True).dt.tz_convert(None).dt.normalize()
    for col in ['quantity','unit_price','total_sales','discount','profit']:
        df[col] = pd.to_numeric(df[col], errors='coerce').replace([np.inf,-np.inf], np.nan)
    # Financial values are never imputed: invalid monetary records are quarantined.
    valid = df[['date','quantity','unit_price','total_sales','discount','profit','transaction_id']].notna().all(axis=1)
    valid &= (df.quantity > 0) & (df.unit_price >= 0) & (df.total_sales >= 0) & df.discount.between(0,1)
    rejected = df.loc[~valid].copy()
    df = df.loc[valid].copy()
    for col in set(REQUIRED)-{'date','quantity','unit_price','total_sales','discount','profit'}:
        df[col] = df[col].fillna('Unknown').astype(str).str.strip().replace('', 'Unknown')
    df['date'] = df.date.dt.strftime('%Y-%m-%d')
    return df.reset_index(drop=True), {'input_rows':before, 'duplicates_removed':duplicates, 'missing_cells':missing_cells, 'rejected_rows':len(rejected), 'accepted_rows':len(df)}, rejected

class Store:
    def __init__(self, path='data/retailmind.db'):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine('sqlite:///' + self.path.as_posix())
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE IF NOT EXISTS datasets (id INTEGER PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP, row_count INTEGER NOT NULL)'))

    def list(self):
        return pd.read_sql('SELECT * FROM datasets ORDER BY id DESC', self.engine)

    def save(self, name, df):
        with self.engine.begin() as conn:
            result = conn.execute(text('INSERT INTO datasets(name,row_count) VALUES (:name,:n)'), {'name':name,'n':len(df)})
            ident = result.lastrowid
            df.to_sql(f'records_{ident}', conn, index=False, if_exists='fail')
        return ident

    def load(self, ident):
        return self.query(f'SELECT * FROM records_{int(ident)}')

    def query(self, sql, params=None):
        if not re.match(r'^\s*SELECT\b', sql, re.I) or ';' in sql or '--' in sql or '/*' in sql:
            raise ValueError('Only one read-only SELECT statement is allowed.')
        uri = self.path.as_uri() + '?mode=ro'
        with sqlite3.connect(uri, uri=True) as conn:
            conn.execute('PRAGMA query_only = ON')
            # SQLite itself enforces the read-only boundary, including nested operations.
            budget = [0]
            def progress():
                budget[0] += 1
                return int(budget[0] > 10000)
            conn.set_progress_handler(progress, 1000)
            return pd.read_sql_query(sql, conn, params=params or {})
