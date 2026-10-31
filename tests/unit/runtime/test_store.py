import pytest
from app.domain.models.learning import Preference, StoreWrite
from app.infrastructure.store import MemoryStore, StoreConflict


def test_batch_atomic_scoped_receipts_and_stale_revision():
    store=MemoryStore(); ns=('run1','preferences','D')
    pref=Preference(pref_id='p1',shop_id='D',field='content_style',value='ảnh nền sáng',status='candidate',evidence_seqs=[1])
    item=StoreWrite(namespace=ns,key='p1',value=pref)
    bad=StoreWrite(namespace=('different','preferences','D'),key='p2',value=pref)
    with pytest.raises(ValueError):
        store.commit_batch([item,bad],run_id='run1',expected_revision=0,new_cursor=1,receipt_key='night:1')
    assert store.get(ns,'p1') is None and store.metadata('run1') == (0,0)
    result=store.commit_batch([item],run_id='run1',expected_revision=0,new_cursor=1,receipt_key='night:1')
    assert result.revision == 1
    assert store.commit_batch([item],run_id='run1',expected_revision=0,new_cursor=1,receipt_key='night:1').duplicate
    with pytest.raises(StoreConflict):
        store.commit_batch([item],run_id='run1',expected_revision=0,new_cursor=1,receipt_key='other')
    assert store.get(('run2','preferences','D'),'p1') is None
