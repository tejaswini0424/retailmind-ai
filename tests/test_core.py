import pandas as pd
import pytest
from retailmind.data import generate_sample, clean_data, Store
from retailmind.analytics import metrics, customers
from retailmind.rag import Retriever
from retailmind.assistant import answer, EXAMPLES

@pytest.fixture
def frame(): return clean_data(generate_sample(150))[0]

def test_cleaning_quarantines_and_deduplicates(frame):
    bad = frame.iloc[[0]].copy()
    bad['total_sales'] = 'invalid'
    raw = pd.concat([frame,frame.iloc[[1]],bad],ignore_index=True)
    clean,report,rejected = clean_data(raw)
    assert len(clean)==len(frame)
    assert report['duplicates_removed']==1
    assert len(rejected)==1

def test_storage_readonly_and_parameters(tmp_path,frame):
    store = Store(tmp_path/'test.db')
    ident = store.save("Quoted ' dataset",frame)
    assert len(store.load(ident))==len(frame)
    assert store.query(f'SELECT COUNT(*) AS n FROM records_{ident} WHERE store_id=:store',{'store':"S01' OR 1=1 --"}).iloc[0,0]==0
    for sql in ['DELETE FROM datasets','SELECT 1; DROP TABLE datasets','PRAGMA user_version=1','SELECT * FROM datasets --comment']:
        with pytest.raises(ValueError): store.query(sql)

def test_answers_grounded(frame,tmp_path):
    store=Store(tmp_path/'test.db')
    ident=store.save('Test',frame)
    retriever=Retriever(frame,'Test')
    for q in EXAMPLES:
        response=answer(q,frame,retriever,store,ident)
        assert response['answer']
        assert isinstance(response['data'],pd.DataFrame)
    response=answer('total revenue',frame,retriever,store,ident)
    assert response['data'].iloc[0]['Revenue']==pytest.approx(frame.total_sales.sum())
    response=answer('highest profit region',frame,retriever,store,ident)
    assert response['data'].iloc[0]['profit']==pytest.approx(frame.groupby('region').profit.sum().max())
    assert response['sql'].startswith('SELECT')
    assert 'Insufficient' in answer('weather tomorrow',frame,retriever,store,ident)['answer']
    assert 'not allowed' in answer('delete all transactions',frame,retriever,store,ident)['answer']

def test_retrieval_and_customers(frame):
    sources=Retriever(frame,'Test').search('Wireless Headphones')
    assert sources and 'Test'==sources[0]['metadata']['dataset']
    assert 'Headphones' in sources[0]['text']
    assert len(customers(frame))==frame.customer_id.nunique()
    assert metrics(frame)['Orders']==frame.transaction_id.nunique()

def test_schema_validation(frame):
    with pytest.raises(ValueError): clean_data(frame.drop(columns=['profit']))
