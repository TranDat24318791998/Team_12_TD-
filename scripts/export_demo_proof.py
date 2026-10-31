#!/usr/bin/env python3
"""Export one completed D comparison for the configured local proof endpoint."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from data.growth_data.demo_proof import export_demo_proof


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source-home',type=Path,required=True)
    parser.add_argument('--comparison-id',required=True)
    parser.add_argument('--output-home',type=Path,default=Path(os.environ.get('GROWTH_DATA_HOME') or ROOT/'data'/'runtime'))
    args=parser.parse_args()
    artifact=export_demo_proof(args.source_home,args.comparison_id)
    args.output_home.mkdir(parents=True,exist_ok=True)
    path=args.output_home/'demo-proof.json'
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=args.output_home,prefix='.demo-proof-',delete=False) as output:
        temporary=Path(output.name)
        try:
            json.dump(artifact,output,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({'path':str(path),'comparison_id':artifact['manifest']['comparison_id'],
                      'run_on':artifact['manifest']['run_on'],'run_off':artifact['manifest']['run_off'],
                      'source':artifact['manifest']['source']},ensure_ascii=False))


if __name__=='__main__': main()
