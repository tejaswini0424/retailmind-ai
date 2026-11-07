from pathlib import Path
import sys
# A project-local dependency installation is useful on managed Windows machines.
local_packages = Path(__file__).resolve().parent / '.local-packages'
if local_packages.exists():
    sys.path.insert(0, str(local_packages))
import hashlib
import pandas as pd
import plotly.express as px
import streamlit as st
import yaml
from dotenv import load_dotenv
from retailmind.data import Store, generate_sample, clean_data, REQUIRED
from retailmind.analytics import metrics, aggregate, trends, customers, product_changes
from retailmind.rag import Retriever
from retailmind.assistant import answer, EXAMPLES

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
config = yaml.safe_load((ROOT/'config.yaml').read_text())
st.set_page_config(page_title='RetailMind AI',page_icon='◈',layout='wide')
st.markdown('''<style>
.block-container {padding-top:2rem;max-width:1500px} h1 {letter-spacing:-1.5px} [data-testid="stMetric"] {background:linear-gradient(135deg,#19283e,#142036);border:1px solid #2b3e56;border-radius:16px;padding:20px} [data-testid="stSidebar"] {border-right:1px solid #24334a} .eyebrow {color:#34d4b5;font-size:12px;letter-spacing:3px;font-weight:700} .hero {padding:24px 0 28px;color:#9bacc5} .stButton>button {border-radius:10px} </style>''',unsafe_allow_html=True)

@st.cache_resource
def database(): return Store(ROOT/'data'/'retailmind.db')
store = database()
if store.list().empty:
    sample,_,_ = clean_data(generate_sample(config['sample_rows']))
    store.save('Demo · synthetic retail transactions',sample)

with st.sidebar:
    st.markdown('## ◈ RetailMind **AI**')
    st.caption('YOUR RETAIL INTELLIGENCE WORKSPACE')
    page = st.radio('Workspace',['Overview','Ask RetailMind','Products & stores','Customers','Data studio'],label_visibility='collapsed')
    st.divider()
    datasets = store.list()
    selected = st.selectbox('Active dataset',datasets.id.tolist(),format_func=lambda i:datasets.set_index('id').loc[i,'name'])
    st.caption('Local SQLite storage · no API key required')

df = store.load(selected)
dataset_name = datasets.set_index('id').loc[selected,'name']
with st.sidebar:
    dates = pd.to_datetime(df.date)
    period = st.date_input('Date range',value=(dates.min().date(),dates.max().date()),min_value=dates.min().date(),max_value=dates.max().date())
    regions = st.multiselect('Regions',sorted(df.region.unique()))
    categories = st.multiselect('Categories',sorted(df.category.unique()))
    stores = st.multiselect('Stores',sorted(df.store_id.unique()))
scope = df.copy()
if isinstance(period,(tuple,list)) and len(period)==2:
    scope = scope.loc[pd.to_datetime(scope.date).between(pd.Timestamp(period[0]),pd.Timestamp(period[1]))]
for col, values in [('region',regions),('category',categories),('store_id',stores)]:
    if values: scope = scope.loc[scope[col].isin(values)]
st.markdown('<div class="eyebrow">RETAIL INTELLIGENCE / WORKSPACE</div>',unsafe_allow_html=True)
st.title({'Overview':'A clearer view of your business.','Ask RetailMind':'Your data. A better conversation.','Products & stores':'Find your next growth opportunity.','Customers':'Understand who comes back.','Data studio':'Better decisions start with clean data.'}[page])
st.caption(f'{dataset_name}  ·  {len(scope):,} selected records  ·  Currency: {config["currency"]}')

def chart(fig):
    fig.update_layout(template='plotly_dark',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',font_color='#afbed1',margin=dict(l=10,r=10,t=35,b=10),colorway=['#26c9ac','#6f97ff','#e9b861','#b58cf5'])
    st.plotly_chart(fig,width='stretch')

if scope.empty and page!='Data studio':
    st.info('No records match these filters. Adjust the sidebar to continue.')
    st.stop()

if page=='Overview':
    st.markdown('<div class="hero">Track performance, discover patterns, and turn grounded insights into your next move.</div>',unsafe_allow_html=True)
    m = metrics(scope)
    for col,(label,value) in zip(st.columns(4),list(m.items())[:4]): col.metric(label,f'{value:,.0f}' if label=='Orders' else f'{config["currency"]} {value:,.2f}')
    left,right = st.columns([1.7,1])
    with left:
        st.subheader('Revenue over time')
        frequency = st.selectbox('Time interval',['Monthly','Weekly','Daily'])
        chart(px.area(trends(scope,{'Monthly':'MS','Weekly':'W','Daily':'D'}[frequency]),x='date',y='total_sales',labels={'total_sales':'Revenue','date':'Date'}))
    with right:
        st.subheader('Category mix')
        chart(px.pie(aggregate(scope,'category'),names='category',values='total_sales',hole=.65))
    a,b = st.columns(2)
    with a:
        st.subheader('Store leaderboard')
        chart(px.bar(aggregate(scope,'store_id'),x='store_id',y='total_sales',color='total_sales',color_continuous_scale=['#183b51','#26c9ac']))
    with b:
        st.subheader('Performance pulse')
        monthly = trends(scope)
        if len(monthly)>1 and monthly.total_sales.iloc[-2]:
            st.metric('Latest calendar bucket vs previous',f'{(monthly.total_sales.iloc[-1]/monthly.total_sales.iloc[-2]-1)*100:+.1f}%')
            st.caption('Boundary months may be incomplete; this is not a like-for-like growth comparison.')
        st.metric('Profit margin',f'{m["Margin %"]:.1f}%')
        st.info('Ask RetailMind to explore a metric and inspect the records supporting its answer.')
    st.download_button('Export selected records',scope.to_csv(index=False),'retailmind_export.csv','text/csv')

elif page=='Ask RetailMind':
    st.info('Grounded local assistant · deterministic answers · no cloud model. All answers use the active filters. Optional local embeddings enable semantic retrieval.')
    signature = hashlib.sha256(scope.to_csv(index=False).encode()).hexdigest()
    @st.cache_resource(max_entries=4)
    def build_retriever(signature, _frame, name): return Retriever(_frame,name)
    with st.spinner('Building retrieval index…'): retriever = build_retriever(signature,scope,dataset_name)
    st.caption(retriever.mode)
    example = st.selectbox('Explore a question',EXAMPLES)
    question = st.chat_input('Ask about sales, stores, products, or profit')
    if st.button('Ask selected question'): question=example
    history_key = f'chat_{selected}_{signature}'
    history = st.session_state.setdefault(history_key,[])
    if st.button('Clear conversation'): history.clear()
    if question:
        with st.spinner('Retrieving evidence and calculating metrics…'):
            history.append((question,answer(question,scope,retriever,store,selected)))
    for question,result in history:
        with st.chat_message('user'): st.write(question)
        with st.chat_message('assistant'):
            st.write(result['answer'])
            st.caption(result['scope'])
            st.write(result['explanation'])
            st.success(result['action'])
            if not result['data'].empty: st.dataframe(result['data'],hide_index=True,width='stretch')
            with st.expander('Inspect retrieval evidence and SQL'):
                st.caption('Retrieved examples are context, not exhaustive aggregate evidence. The supporting calculation table above covers the full selected scope.')
                for source in result['sources']:
                    st.write(source['text']); st.json(source['metadata'])
                if result['sql']:
                    st.code(result['sql'],language='sql'); st.json(result['params'])

elif page=='Products & stores':
    a,b,c = st.tabs(['Products','Stores & regions','Inventory review'])
    with a:
        field = st.selectbox('Measure',['total_sales','quantity','profit'])
        products = aggregate(scope,'product_name',field)
        chart(px.bar(products,x=field,y='product_name',orientation='h'))
        st.write('Best and least selling products'); st.dataframe(products,hide_index=True,width='stretch')
        st.write('Category profitability'); st.dataframe(aggregate(scope,'category','profit'),hide_index=True)
    with b:
        chart(px.bar(aggregate(scope,'store_id'),x='store_id',y='total_sales'))
        chart(px.bar(aggregate(scope,'region','profit'),x='region',y='profit'))
    with c:
        st.warning('Demand-based review only. Stock-on-hand and supplier lead times are unavailable, so reorder quantities cannot be calculated.')
        st.write('High-demand products'); st.dataframe(aggregate(scope,'product_name','quantity'),hide_index=True)
        st.write('Product movement · trailing 30 days vs prior 30 days'); st.dataframe(product_changes(scope),hide_index=True)

elif page=='Customers':
    segments = customers(scope)
    a,b,c = st.columns(3)
    a.metric('Customers',len(segments)); b.metric('Repeat customers',int((segments.orders>1).sum())); c.metric('Repeat rate',f'{(segments.orders>1).mean()*100:.1f}%')
    st.caption('K-Means segments use standardized purchase frequency, spend, and days since last purchase. Segment numbers are cluster IDs, not value rankings. Recency is relative to the latest selected record.')
    chart(px.scatter(segments,x='orders',y='spend',color='segment',hover_data=['customer_id','recency']))
    st.dataframe(segments,hide_index=True,width='stretch')

elif page=='Data studio':
    st.subheader('Bring your retail data')
    st.caption('Required schema: ' + ', '.join(REQUIRED))
    st.download_button('Download sample CSV template',generate_sample(20).to_csv(index=False),'retail_template.csv','text/csv')
    upload = st.file_uploader('Upload CSV or Excel',type=['csv','xlsx'])
    if upload:
        try:
            if upload.name.lower().endswith('.xlsx'):
                workbook = pd.ExcelFile(upload)
                sheet = st.selectbox('Worksheet',workbook.sheet_names)
                raw = pd.read_excel(workbook,sheet_name=sheet)
            else: raw=pd.read_csv(upload)
            st.write('Raw preview'); st.dataframe(raw.head(30),hide_index=True)
            cleaned,report,rejected = clean_data(raw)
            st.json(report)
            st.caption('Exact duplicates removed; invalid numeric/date records quarantined; missing descriptive fields set to Unknown. Discount must be a fraction from 0 to 1. Financial values are never imputed.')
            st.write('Cleaned preview'); st.dataframe(cleaned.head(30),hide_index=True)
            if len(rejected): st.download_button('Download rejected records',rejected.to_csv(index=False),'rejected.csv','text/csv')
            name = st.text_input('Dataset name',upload.name)
            if st.button('Save cleaned dataset',disabled=cleaned.empty or not name.strip()):
                store.save(name.strip(),cleaned); st.success('Dataset saved. Select it in the sidebar.'); st.rerun()
        except Exception as exc: st.error(f'Could not import dataset: {exc}')
    st.divider()
    st.subheader('Generate a demo dataset')
    rows = st.number_input('Rows',100,50000,5000,100)
    if st.button('Generate and save synthetic data'):
        generated,_,_ = clean_data(generate_sample(rows))
        store.save(f'Synthetic demo · {rows:,} rows',generated); st.rerun()
    st.subheader('Dataset library'); st.dataframe(store.list(),hide_index=True,width='stretch')
