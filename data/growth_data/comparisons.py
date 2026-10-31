"""Comparison lifecycle: immutable inputs, caller-owned cohorts, measured proof."""

from . import models as M
from .errors import require
from .storage import fingerprint, insert, one, many, now, uid


class ComparisonMixin:
    def validate_pair(self,c,p,on,off):
        a=self.run(c,p,on);b=self.run(c,p,off)
        require(p.role in {"seller","orchestrator","evaluator","data_admin"},"FORBIDDEN","Không được đọc đối chứng tài chính",403)
        require(a["memory_enabled"] and not b["memory_enabled"],"COMPARISON_MISMATCH","Cặp phải đúng memory on/off")
        for key in ("scenario_version","simulator_version","seed","simulation_days","execution_profile","content_mode","learning_mode","initial_snapshot_hash","config"):
            require(a[key]==b[key],"COMPARISON_MISMATCH",f"Cấu hình đối chứng khác: {key}")
        require(a["initial_snapshot_hash"],"COMPARISON_UNVERIFIED","Run cũ chưa có snapshot đầu vào")
        return a,b

    def comparison_create(self,c,p,body):
        b=M.ComparisonCreate.model_validate(body)
        self.require_comparison_role(p)
        config=b.model_dump()
        if b.execution_profile=="reference":
            require(b.content_mode in {None,"local"} and b.learning_mode in {None,"skip"},"CONFIG_INVALID","Reference comparison dùng local/skip; worker thật dùng external profile",422)
            config.update(content_mode="local",learning_mode="skip")
        on=self.create_run(c,p,{**config,"memory_enabled":True},select=False)["run_id"]
        off=self.create_run(c,p,{**config,"memory_enabled":False},select=False)["run_id"]
        a,_=self.validate_pair(c,p,on,off)
        return self.insert_comparison(c,p,a,on,off,"queued")

    @staticmethod
    def require_comparison_role(p):
        require(p.role in {"seller","orchestrator","evaluator","data_admin"},"FORBIDDEN","Không được tạo đối chứng",403)

    def insert_comparison(self,c,p,a,on,off,status):
        gid=uid("group")
        insert(c,"comparison_groups",group_id=gid,session_id=p.session_id or a["session_id"],run_on_id=on,run_off_id=off,
               scenario_version=a["scenario_version"],simulator_version=a["simulator_version"],seed=a["seed"],days=a["simulation_days"],report_version="proof-v2-7d",created_at=now(),status=status,config_hash=fingerprint([a["initial_snapshot_hash"],a["config"]]))
        return {"comparison_id":gid,"run_on":on,"run_off":off,"status":status}

    def comparison_attach(self,c,p,body):
        b=M.ComparisonAttach.model_validate(body)
        a,other=self.validate_pair(c,p,b.run_on,b.run_off)
        require(a["phase"]==other["phase"]=="complete","COMPARISON_PENDING","Hai run chưa hoàn tất")
        return self.insert_comparison(c,p,a,b.run_on,b.run_off,"ready")

    def comparison_view(self,c,p,gid):
        group=one(c,"SELECT * FROM comparison_groups WHERE group_id=?",(gid,))
        require(group,"NOT_FOUND","Không tìm thấy đối chứng",404)
        self.require_comparison_role(p)
        a=self.run(c,p,group["run_on_id"]);b=self.run(c,p,group["run_off_id"])
        status="ready" if a["phase"]==b["phase"]=="complete" else "failed" if "failed" in {a["phase"],b["phase"]} else "running"
        return {"comparison_id":gid,"run_on":a["run_id"],"run_off":b["run_id"],"status":status,"days":group["days"],
                "on":self.safe_run(a),"off":self.safe_run(b),"source":"reference" if a["execution_profile"]=="reference" else "external_workers"}

    def drive_comparison(self,gid):
        """The same reference commands as the seller facade, one short tx/tick."""
        from .service import Principal
        from .facade import Facade
        with self.store.connect() as c:
            g=one(c,"SELECT * FROM comparison_groups WHERE group_id=?",(gid,))
            if not g:return
            runs=[self.entity(c,"runs",r,"run_id",r) for r in (g["run_on_id"],g["run_off_id"])]
        if any(r["execution_profile"]!="reference" for r in runs):return
        p=Principal("comparison_driver","seller",g["session_id"],tuple(r["run_id"] for r in runs),("D",))
        facade=Facade(self)
        for row in runs:
            r=row["run_id"]
            for _ in range(40):
                with self.store.connect(write=True) as c:
                    run=self.run(c,p,r)
                    if run["phase"]=="complete":break
                    if run["phase"]=="ready":
                        self.operation(c,p,r,"start_day",{"expected_day":run["current_day"],"expected_version":run["version"]})
                    else:
                        state=facade.state(c,p,r)
                        if state["pending_card"]:
                            card=state["pending_card"]
                            facade.decide(c,p,r,{"card_id":card["card_id"],"action":"accept",**({"rule_answer":True} if card["rule_question"] else {})})
                        elif run["phase"]=="content_review":facade.use_content(c,p,r,{"cover_option":"B"})
                        else:facade.night(c,p,r)
        with self.store.connect(write=True) as c:
            done=all(self.entity(c,"runs",row["run_id"],"run_id",row["run_id"])["phase"]=="complete" for row in runs)
            c.execute("UPDATE comparison_groups SET status=?,version=version+1 WHERE group_id=?",("ready" if done else "running",gid))
