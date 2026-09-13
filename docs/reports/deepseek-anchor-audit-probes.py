import json, runpy, tempfile
from pathlib import Path
from dataclasses import replace
from willfly.ingest.canonicalize import canonicalize_events
from willfly.ingest.runner import capture_to_store, backfill_to_store
from willfly.storage import BlockHeader, RawBatchStore
x=runpy.run_path('tests/test_header_reconciliation.py')
h=x['_hash']; anchor=x['_anchor']; ev=x['_event']; Client=x['_ForkCaptureClient']; V4=x['V4']
headers=[BlockHeader(99,h(99),h(98),1700000099),BlockHeader(100,h(100),h(99),1700000100),BlockHeader(101,h(101),h(100),1700000101)]
out={}
a=anchor(100,h(100),qualification='operator_declared_unverified')
r=canonicalize_events([ev(101,h(101),h(100))],tip_hash=h(101),headers=headers,anchor=a,expected_chain_id=4663,expected_config_identity=a.config_identity)
out['unverified_anchor']={'resolved':r.is_resolved,'state':r.anchor_state,'canonical_events':len(r.canonical_events)}
r=canonicalize_events([ev(99,h(99),h(98)),ev(101,h(101),h(100)),ev(102,h(102),h(101))],tip_hash=h(101),headers=headers,anchor=anchor(100,h(100)))
out['outside_window']={'resolved':r.is_resolved,'orphaned_heights':[e.block_number for e in r.orphaned_events]}
a=anchor(100,h(100),qualification='genesis')
r=canonicalize_events([],tip_hash=h(101),headers=headers,anchor=a)
out['false_genesis_at_100']={'resolved':r.is_resolved,'state':r.anchor_state}
with tempfile.TemporaryDirectory() as t:
 with RawBatchStore(Path(t)) as s:
  wrong=anchor(100,h(100),config_identity='WRONG')
  r=capture_to_store(Client({z.number:z for z in headers[1:]},{}),s,addresses=[V4],from_block=100,to_block=101,run_id='wrong-config',anchor=wrong)
  out['poisoned_anchor']={'first_state':r.header_evidence['ancestry_anchor_state'],'stored_config':s.get_ancestry_anchor(wrong.source).config_identity}
  try: capture_to_store(Client({z.number:z for z in headers[1:]},{}),s,addresses=[V4],from_block=100,to_block=101,run_id='correct-config',anchor=anchor(100,h(100)))
  except Exception as e:out['poisoned_anchor']['corrected_retry_error']=str(e)
for kind,run in [('capture',capture_to_store),('backfill',backfill_to_store)]:
 with tempfile.TemporaryDirectory() as t:
  with RawBatchStore(Path(t)) as s:
   hh={0:BlockHeader(0,h(1000),None,1700000000),1:BlockHeader(1,h(1001),h(1000),1700000001)}
   kw=dict(addresses=[V4],run_id='genesis-'+kind)
   kw.update(dict(from_block=0,to_block=1) if kind=='capture' else dict(start_block=0,target_block=1))
   r=run(Client(hh,{}),s,**kw)
   out[kind+'_genesis']={'state':r.header_evidence['ancestry_anchor_state']}
print(json.dumps(out,indent=2))
