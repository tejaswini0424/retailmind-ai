import base64
from io import BytesIO
import pandas as pd
import pytest
from web.api.index import dispatch
from retailmind.data import generate_sample

def test_demo_and_health():
    assert dispatch({'action':'health'})['status']=='ok'
    result=dispatch({'action':'demo'})
    assert len(result['rows'])==5000
    assert len(result['examples'])==12

def test_web_analytics_and_answer():
    rows=generate_sample(150).to_dict('records')
    payload={'rows':rows,'filters':{'region':['North']}}
    expected=sum(r['total_sales'] for r in rows if r['region']=='North')
    result=dispatch(dict(payload,action='analytics'))
    assert result['metrics']['Revenue']==pytest.approx(expected)
    result=dispatch(dict(payload,action='ask',question='total sales'))
    assert result['data'][0]['Revenue']==pytest.approx(expected)
    assert all(s['metadata']['record_id'] for s in result['sources'])
    assert dispatch(dict(payload,action='customers'))['count']>0

def test_web_upload_and_isolation():
    frame=generate_sample(50)
    csv=base64.b64encode(frame.to_csv(index=False).encode()).decode()
    result=dispatch({'action':'upload','name':'retail.csv','content':csv})
    assert result['report']['accepted_rows']==50
    assert dispatch({'action':'analytics','rows':result['rows']})['row_count']==50
    # No uploaded records leak into another request or the demo dataset.
    assert dispatch({'action':'analytics'})['row_count']==5000

def test_web_excel_sheets_and_cleaning():
    pytest.importorskip('openpyxl')
    buffer=BytesIO()
    with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
        generate_sample(25).to_excel(writer,sheet_name='Retail',index=False)
    payload={'action':'upload','name':'retail.xlsx','content':base64.b64encode(buffer.getvalue()).decode()}
    assert dispatch(dict(payload,list_sheets=True))['sheets']==['Retail']
    assert dispatch(dict(payload,sheet='Retail'))['report']['accepted_rows']==25

def test_web_validation():
    with pytest.raises(ValueError): dispatch({'action':'analytics','filters':{'region':['nonexistent']}})
    with pytest.raises(ValueError): dispatch({'action':'ask','question':''})
    with pytest.raises(ValueError): dispatch({'action':'upload','name':'test.exe','content':''})
