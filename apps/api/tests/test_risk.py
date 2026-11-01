from app.risk import evaluate

def test_risk_traceability():
    rows=[{'id':str(i),'date':'2026-10-01','amount':str(i+1),'beneficiary':'Test fixture'} for i in range(10)]
    rows[-1]['amount']='1000'
    alerts=evaluate(rows)
    assert len(alerts)==1
    assert alerts[0]['score']==30
    assert alerts[0]['human_review'] is True
    assert alerts[0]['version']=='1.0.0'

def test_small_sample_no_outlier():
    assert evaluate([{'id':'1','date':'2026-10-01','amount':'100000','beneficiary':'Test fixture'}])==[]
