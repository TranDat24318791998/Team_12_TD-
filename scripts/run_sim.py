#!/usr/bin/env python3
"""Run two independent offline, Data-backed native simulation arms."""
import argparse
import json
import sqlite3
import sys
from uuid import uuid4
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.paths import RUNS_DIR
from app.core.settings import Settings
from data.growth_data.service import DataService
from app.simulation.runner import compare, provenance, run


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--days',type=int,choices=range(1,8),default=7)
    parser.add_argument('--shop',choices=list('ABCDE'),default='D')
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    settings=Settings(llm_mode='offline',media_mode='offline',demo_shop=args.shop,seed=args.seed)
    home=RUNS_DIR/f'sim-{args.shop}-{uuid4().hex}'
    on=run(settings,args.days,True,args.seed,home=home)
    with sqlite3.connect(home/'growth.db') as c:
        sid=c.execute('SELECT session_id FROM runs WHERE run_id=?',(on.run_id,)).fetchone()[0]
    off=run(settings,args.days,False,args.seed,home=home,seller_session_id=sid)
    service=DataService(home,content_mode='worker',learning_mode='external')
    seller=service.authenticate(sid=sid)
    with service.store.connect(write=True) as c:
        group=service.comparison_attach(c,seller,{'run_on':on.run_id,'run_off':off.run_id})
    report=compare(on,off)
    path=home/'comparison.json'
    path.write_text(json.dumps({'comparison_id':group['comparison_id'],'report':report.model_dump(mode='json'),'on':on.model_dump(mode='json'),
        'off':off.model_dump(mode='json'),'seller_policy_version':'accept-valid-v1',
        'market_source':'offline_simulator','content_effect':'simulated','provider_eval':'not_run',
        'on_provenance':provenance(on),'off_provenance':provenance(off)},
        ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report_path':str(path),'report':report.model_dump(mode='json')},ensure_ascii=False))


if __name__=='__main__': main()
