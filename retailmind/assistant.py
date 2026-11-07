import re
from datetime import date
import pandas as pd
from .analytics import metrics, aggregate, trends, product_changes

EXAMPLES = ['What were the total sales this month?', 'Which store generated the highest revenue?', 'What is the most profitable product category?', 'Which products have declining sales?', 'Compare revenue across all stores.', 'What are the top five selling products?', 'Which region has the highest profit?', 'What is the average transaction value?', 'Show monthly sales trends.', 'Why did sales decrease?', 'Which products should receive more inventory?', 'Summarize the overall retail performance.']

def answer(question, df, retriever, store, dataset_id):
    q = question.lower().strip()
    sources = retriever.search(question)
    result = {'sources':sources, 'sql':None, 'params':{}, 'data':pd.DataFrame(), 'scope':'Current dashboard filters', 'explanation':'Metrics are calculated from every record in the selected scope. Retrieved examples provide context; they are not used to estimate totals.', 'action':'Review the supporting table before making an operational decision.'}
    if re.search(r'\b(drop|delete|update|insert|alter|attach|pragma|replace|create)\b', q):
        return dict(result, answer='Write operations are not allowed. Ask a read-only business question.')
    filtered = df.copy()
    if 'this month' in q:
        today = pd.Timestamp(date.today())
        dates = pd.to_datetime(filtered.date)
        filtered = filtered.loc[(dates.dt.month==today.month)&(dates.dt.year==today.year)]
        result['scope'] += f'; calendar month {today:%Y-%m}'
    # Match known entity values, never interpolate user text into SQL.
    for column in ['store_id','region','category','product_name']:
        matches = [v for v in df[column].unique() if re.search(r'(?<!\w)'+re.escape(str(v).lower())+r'(?!\w)', q)]
        if matches:
            filtered = filtered.loc[filtered[column].isin(matches)]
            result['scope'] += f'; {column}: ' + ', '.join(matches)
    if filtered.empty:
        return dict(result,answer='Insufficient supporting data: no records match this period and the active filters.',sources=[])
    m = metrics(filtered)
    metric = 'profit' if any(w in q for w in ['profit','profitable']) else 'quantity' if any(w in q for w in ['selling','demand','inventory']) else 'total_sales'
    group = next((c for term,c in [('categor','category'),('store','store_id'),('region','region'),('product','product_name')] if term in q), None)
    if any(w in q for w in ['declin','decrease','why']):
        data = product_changes(filtered)
        result['data'] = data
        change = float(data.change.sum())
        result['answer'] = f'Revenue changed by {change:,.2f} between the two trailing 30-day windows, anchored to the latest selected record. {int((data.change<0).sum())} products declined.'
        result['explanation'] = 'The table decomposes the observed revenue change by product. Transactions alone cannot establish causes such as stockouts, competition, or campaign effects. Incomplete windows can distort comparisons.'
        result['action'] = 'Investigate declining products with inventory and promotion records before attributing causes.'
    elif any(w in q for w in ['trend','daily','weekly','monthly']):
        result['data'] = trends(filtered, 'D' if 'daily' in q else 'W' if 'weekly' in q else 'MS')
        result['answer'] = f'Revenue totals {m["Revenue"]:,.2f} over the selected period. The supporting table shows the time series.'
    elif group:
        # Derive a bounded SQL plan from recognized intent and trusted schema.
        # Scope is represented by a temporary in-memory SQLite table, keeping SQL exact even for dashboard filters.
        import sqlite3
        with sqlite3.connect(':memory:') as conn:
            filtered.to_sql('scope',conn,index=False)
            sql = f'SELECT {group}, SUM({metric}) AS {metric} FROM scope GROUP BY {group} ORDER BY {metric} DESC'
            limit = re.search(r'\btop\s+(\d+)\b',q)
            n = max(1,min(int(limit.group(1)),100)) if limit else 5 if 'top five' in q else None
            params = {'limit':n} if n else {}
            if n: sql += ' LIMIT :limit'
            conn.execute('PRAGMA query_only=ON')
            result['data'] = pd.read_sql_query(sql,conn,params=params)
        result['sql'],result['params'] = sql,params
        row = result['data'].iloc[0]
        result['answer'] = f'{row[group]} leads by {metric.replace("_"," ")} at {row[metric]:,.2f}. Results cover {len(filtered):,} selected records.'
        if 'inventory' in q:
            result['action'] = 'Prioritize a stock review for high-unit-demand products. Reorder quantities require stock-on-hand, lead times, and service targets, which this dataset does not contain.'
    elif any(w in q for w in ['average','transaction value','order value']):
        result['answer'] = f'Average order value is {m["Average order"]:,.2f}, calculated as revenue divided by {m["Orders"]:,} distinct transactions.'
        result['data'] = pd.DataFrame([m])
    elif any(w in q for w in ['sales','revenue','performance','summary','summarize','profit']):
        result['answer'] = f'Total revenue is {m["Revenue"]:,.2f}; profit is {m["Profit"]:,.2f}; margin is {m["Margin %"]:.2f}%, across {m["Orders"]:,} orders and {m["Units sold"]:,.0f} units.'
        result['data'] = pd.DataFrame([m])
    else:
        result['answer'] = 'Insufficient supporting data or unsupported analytical intent. Try one of the suggested retail questions.'
    return result
