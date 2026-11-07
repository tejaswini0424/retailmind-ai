from io import BytesIO
import pandas as pd
import pytest
from retailmind.data import clean_data, generate_sample

def test_excel_roundtrip():
    pytest.importorskip('openpyxl')
    source = generate_sample(20)
    stream = BytesIO()
    source.to_excel(stream,index=False)
    stream.seek(0)
    result,report,_ = clean_data(pd.read_excel(stream))
    assert report['accepted_rows']==20
    assert result.total_sales.sum()==pytest.approx(source.total_sales.sum())
