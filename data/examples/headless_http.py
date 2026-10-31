"""Gate A fixture over TCP to a local Data API sharing the supplied runtime home."""

import argparse
import json
from pathlib import Path
import httpx
from growth_data.harness import HttpHarness
from growth_data.service import DataService


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--base-url",default="http://127.0.0.1:8001")
    parser.add_argument("--home",type=Path,default=Path(__file__).resolve().parents[1]/"runtime")
    parser.add_argument("--report",type=Path,default=Path(__file__).resolve().parents[1]/"runtime/headless-http-report.json")
    args=parser.parse_args()
    # Local test administrator issues scoped tokens; business mutations use HTTP.
    # The server must use the same home. No service tokens are printed or exported.
    admin=DataService(args.home)
    with httpx.Client(base_url=args.base_url,timeout=60) as client:
        result=HttpHarness(client,admin.issue_token).comparison()
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"gate":"A","gate_b":"PENDING","http_calls":result["http_calls"],"report":str(args.report)},ensure_ascii=False))


if __name__=="__main__":main()
