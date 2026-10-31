"""uv run growth-data: reproducible local setup, scenarios and handoff exports."""

import argparse
import json
from pathlib import Path
import os

from .service import DataService
from .seed import prepare, world
from .storage import fingerprint, many, one
from .evidence import run_scenario, compare, proof, replay_export


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")


def main():
    parser=argparse.ArgumentParser(description="Growth Agents local data service")
    parser.add_argument("--home",type=Path,default=Path(__file__).resolve().parents[1]/"runtime")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("init-db")
    seed=sub.add_parser("seed");seed.add_argument("--output",type=Path,default=Path(__file__).resolve().parents[1]/"datasets")
    sub.add_parser("validate-data")
    docs=sub.add_parser("export-docs");docs.add_argument("--output",type=Path,default=Path(__file__).resolve().parents[1]/"datasets");docs.add_argument("--font",type=Path)
    sub.add_parser("recover")
    serve=sub.add_parser("serve");serve.add_argument("--host",default="127.0.0.1");serve.add_argument("--port",type=int,default=8001)
    run=sub.add_parser("run-scenario");run.add_argument("--seed",type=int,default=42);run.add_argument("--days",type=int,choices=[6,7],default=7);run.add_argument("--compare",action="store_true")
    for command in ("export-proof","export-replay"):
        export=sub.add_parser(command);export.add_argument("--run-id",required=True);export.add_argument("--output",type=Path,required=True)
        if command=="export-proof":export.add_argument("--group-id",required=True);export.add_argument("--variant",choices=["full_7d","legacy_6d"],default="full_7d")
    token=sub.add_parser("issue-token");token.add_argument("--role",required=True);token.add_argument("--run-id",action="append",required=True);token.add_argument("--shop",action="append",required=True);token.add_argument("--job",action="append");token.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();service=DataService(args.home)
    if args.command=="init-db":
        # Explicit development setup only. Never embedded into source/browser scripts.
        path=service.home/"dev-credentials.json"
        if not path.exists():
            roles=["platform_agent","shop_agent","orchestrator","simulator","content_worker","learning_worker","evaluator","knowledge_admin","data_admin"]
            write_json(path,{role:service.issue_token(role,shops=("D",) if role=="shop_agent" else ("*",)) for role in roles});path.chmod(0o600)
        print(json.dumps({"database":str(service.store.path),"credentials_file":str(path),"note":"Development-only tokens; do not share wildcard tokens with a browser"}))
    elif args.command=="seed":
        manifest=prepare(args.output)
        write_json(args.output/"seed.json",world())
        write_json(args.output/"simulator"/"scenario.json",{"seed":42,"history_days":14,"days":7,"start_date":"2026-11-01","is_simulated":True,"one_unit_per_order":True,"replenishment":False})
        write_json(args.output/"simulator"/"seller_behaviors.json",{sid:s["persona"] for sid,s in world()["shops"].items()})
        write_json(args.output/"simulator"/"market_parameters.json",{"cpc":1800,"noise_sigma":.10,"ctr":[.015,.02],"cvr":[.03,.03,.002],"quality_gain":.25,"prior_cvr_bias":1.5})
        write_json(args.output/"simulator"/"market_schedule.json",{"daily_trend_growth":.12,"plateau_day":7,"calendar":world()["calendar"]})
        write_json(args.output/"public"/"shops.json",[s["public"] for s in world()["shops"].values()])
        import hashlib
        for path in sorted(args.output.rglob("*")):
            if path.is_file() and path.name!="manifest.json":
                name=str(path.relative_to(args.output));manifest["files"].setdefault(name,{"access":"public" if name.startswith(("public/","knowledge/","originals/")) else "backend_only"})
                manifest["files"][name]["sha256"]=hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(args.output/"manifest.json",manifest)
        print(json.dumps({"output":str(args.output),"files":len(manifest["files"]),"is_simulated":True}))
    elif args.command=="validate-data":
        with service.store.connect() as c:
            assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall()==[]
            for run in many(c,"SELECT * FROM runs"):
                rid=run["run_id"]
                assert c.execute("SELECT COUNT(*) FROM daily_metrics WHERE run_id=? AND source='seeded'",(rid,)).fetchone()[0]==140
                if run["phase"]=="complete":
                    assert c.execute("SELECT COUNT(*) FROM day_settlements WHERE run_id=?",(rid,)).fetchone()[0]==5*run["simulation_days"]
                    assert c.execute("SELECT COUNT(*) FROM daily_metrics WHERE run_id=? AND source='simulated'",(rid,)).fetchone()[0]==10*run["simulation_days"]
                assert not one(c,"SELECT product_id FROM inventory WHERE run_id=? AND available_units<0",(rid,))
                assert not one(c,"SELECT campaign_id FROM campaigns WHERE run_id=? AND spent_vnd>approved_total_vnd",(rid,))
            print(json.dumps({"integrity":"ok","runs":c.execute("SELECT COUNT(*) FROM runs").fetchone()[0],"knowledge_documents":c.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]}))
    elif args.command=="recover":print(json.dumps(service.recover()))
    elif args.command=="export-docs":
        from .documents import export_guides
        prepare(args.output)
        print(json.dumps({"pdfs":[str(p) for p in export_guides(args.output,args.font)]}))
    elif args.command=="serve":
        from .api import create_app
        import uvicorn
        uvicorn.run(create_app(args.home),host=args.host,port=args.port)
    elif args.command=="run-scenario":
        rid,p=run_scenario(service,seed=args.seed,days=args.days)
        result={"run_id":rid,"session_id":p.session_id,"driver":"offline_reference","learning":"not_connected"}
        if args.compare:
            off,_=run_scenario(service,seed=args.seed,days=args.days,memory=False,seller=p)
            gid=compare(service,p,rid,off)
            with service.store.connect() as c:report=proof(service,c,p,rid,gid)
            write_json(service.home/"exports"/"proof.json",report)
            result.update(run_off=off,group_id=gid,proof=str(service.home/"exports"/"proof.json"))
        print(json.dumps(result,ensure_ascii=False))
    elif args.command=="issue-token":
        output=args.output.resolve();require_path=service.home.resolve()
        if not output.is_relative_to(require_path):parser.error("Token output phải nằm trong --home (runtime Git-ignored)")
        write_json(output,{"token":service.issue_token(args.role,runs=tuple(args.run_id),shops=tuple(args.shop),jobs=tuple(args.job or ())) });output.chmod(0o600)
        print(json.dumps({"credentials_file":str(output)}))
    else:
        from .service import Principal
        p=Principal("cli_admin","data_admin",None,("*",),("*",))
        with service.store.connect() as c:
            report=proof(service,c,p,args.run_id,args.group_id,args.variant) if args.command=="export-proof" else replay_export(service,c,p,args.run_id)
        write_json(args.output,report);print(str(args.output))


if __name__=="__main__":main()
