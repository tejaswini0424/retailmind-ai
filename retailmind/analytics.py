import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

def metrics(df):
    orders = df.transaction_id.nunique()
    return {'Revenue':float(df.total_sales.sum()), 'Profit':float(df.profit.sum()), 'Orders':orders, 'Average order':float(df.total_sales.sum()/orders) if orders else 0, 'Units sold':float(df.quantity.sum()), 'Margin %':float(df.profit.sum()/df.total_sales.sum()*100) if df.total_sales.sum() else 0}

def aggregate(df, group, metric='total_sales'):
    return df.groupby(group, dropna=False)[metric].sum().sort_values(ascending=False).reset_index()

def trends(df, frequency='MS'):
    return df.assign(date=pd.to_datetime(df.date)).set_index('date').resample(frequency)[['total_sales','profit','quantity']].sum().reset_index()

def customers(df):
    if df.empty:
        return pd.DataFrame(columns=['customer_id','orders','spend','last_purchase','recency','segment'])
    x = df.groupby('customer_id').agg(orders=('transaction_id','nunique'),spend=('total_sales','sum'),last_purchase=('date','max')).reset_index()
    x['recency'] = (pd.to_datetime(df.date).max()-pd.to_datetime(x.last_purchase)).dt.days
    features = StandardScaler().fit_transform(x[['orders','spend','recency']])
    count = min(3, len(x), len(np.unique(features,axis=0)))
    x['segment'] = KMeans(n_clusters=count, random_state=42, n_init=10).fit_predict(features).astype(str) if count>1 else '0'
    return x

def product_changes(df):
    if df.empty: return pd.DataFrame()
    end = pd.to_datetime(df.date).max()
    dates = pd.to_datetime(df.date)
    current = df.loc[dates.gt(end-pd.Timedelta(days=30))].groupby('product_name').total_sales.sum()
    previous = df.loc[dates.gt(end-pd.Timedelta(days=60)) & dates.le(end-pd.Timedelta(days=30))].groupby('product_name').total_sales.sum()
    result = pd.concat([current.rename('current_30d'),previous.rename('previous_30d')],axis=1).fillna(0)
    result['change'] = result.current_30d-result.previous_30d
    result['change_pct'] = result.change.div(result.previous_30d.replace(0,np.nan))*100
    return result.sort_values('change').reset_index()
