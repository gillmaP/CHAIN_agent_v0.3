"""Semantic checks for the generated Host's synthetic recorded-HITL demo."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()


def verify(directory):
    directory = Path(directory)
    read = lambda name: json.loads((directory/name).read_text(encoding='utf-8'))
    outcome, snapshot = read('outcome.json'), read('snapshot.json')
    assert outcome['status'] == 'COMPLETED' and outcome['state'] == 'S3'
    assert snapshot['state_history'] == ['S0','S1','S2','S2_1','S3']
    audit = snapshot['audit']
    previous = 'sha256:' + '0'*64
    for entry in audit:
        assert entry['prev_hash'] == previous
        assert digest({k:v for k,v in entry.items() if k != 'entry_hash'}) == entry['entry_hash']
        previous = entry['entry_hash']
    reviews = [r for r in snapshot['hitl_history'].values()
               if r['request']['checkpoint'] == 'HITL_2_THROMBOLYSIS']
    assert reviews and all(r['status'] == 'DECIDED' for r in reviews)
    first = reviews[0]
    request, evidence = first['request'], first['snapshot']
    assert request['evidence_mode'] == 'SOURCE_SNAPSHOT'
    assert request['result_ids'] == [] and first['results'] == []
    assert evidence['snapshot_id'] == request['evidence_snapshot_id']
    facts = evidence['facts']
    assert facts['ncct_completed']['value'] is True
    assert facts['ncct_order_id']['value'] == facts['ct_order_id']['value']
    opened = next(i for i,e in enumerate(audit) if e['type']=='HITL_REQUESTED' and e['request_id']==request['request_id'])
    assert not any(e['type']=='AGENT_RESULT_ACCEPTED' and e.get('alias')=='tpa_decision_support'
                   and e.get('mode')=='final' for e in audit[:opened])
    assert request['roles'] and request['required_confirmations']
    decisions = [e for e in audit if e['type']=='HITL_DECISION_RECORDED' and e.get('request_id')==request['request_id']]
    assert decisions and decisions[0]['actor']['role'] in request['roles']
    assert set(request['required_confirmations']) <= set(decisions[0]['confirmed_items'])
    for run in snapshot['agent_outputs'].values():
        if run['alias'] == 'tpa_decision_support':
            domain = run['output']['result']
            assert domain['mock_only'] is True
            assert domain['assessment']['dose_preview']['auto_order'] is False
            assert domain['assessment']['dose_preview']['auto_administration'] is False
    return {'status':'PASS','checks':['completed state flow','audit hash chain','CT/order binding',
        'HITL-2 before final success','fixed source-only evidence','human decision','no automatic order']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    print(json.dumps(verify(parser.parse_args().directory),indent=2))
