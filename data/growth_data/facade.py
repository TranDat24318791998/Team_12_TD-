"""Nine legacy demo endpoints share the same commands as the versioned API."""

from .service import Principal
from .storage import many, one
from .simulation import aggregate
from .errors import require


class Facade:
    def __init__(self, service): self.s=service

    def current(self,c,p):
        row=one(c,"SELECT * FROM runs WHERE session_id=? ORDER BY rowid DESC LIMIT 1",(p.session_id,))
        require(row,"RUN_REQUIRED","Cần đặt lại hoặc khởi tạo phiên",404)
        return row

    def internal(self,p,r,s="D"):
        return Principal("legacy_orchestrator","orchestrator",p.session_id,(r,),(s,))

    def forecast_view(self,c,r,fid):
        if not fid:return None
        f=self.s.entity(c,"forecasts",r,"forecast_id",fid)
        return {k:f[k] for k in ("low","point","high","factor_used","stock_warning")}

    def card(self,c,r,card):
        if not card:return None
        prop=self.s.entity(c,"proposals",r,"proposal_id",card["proposal_id"]) if card["proposal_id"] else None
        question=self.s.entity(c,"rule_questions",r,"question_id",card["question_id"]) if card["question_id"] else None
        ev=self.s.evaluation(c,r,card["shop_id"],prop["package"])[0] if prop else {}
        return {"card_id":card["card_id"],"shop_id":card["shop_id"],"day":card["day"],"kind":card["kind"],
                "package":prop["package"] if prop else None,"forecast":self.forecast_view(c,r,prop["forecast_id"]) if prop else None,
                "profit_after_fees_per_unit":ev.get("unit_contribution_vnd"),
                "breakeven_roas_display":ev.get("stop_threshold") if prop and prop["package"]["ads_daily_budget"] else None,
                "reasons_vi":card["reasons"],"warnings_vi":["Giá bán đang lỗ sau phí; chỉ làm mới nội dung"] if ev.get("unprofitable") else card["warnings"],"notices_vi":card["notices"],
                "rule_question":{"pref_id":question["question_id"],"field":question["field"],"value":str(question["value"]),"text_vi":question["text_vi"]} if question else None}

    def draft(self,c,r,s="D"):
        job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id=? ORDER BY rowid DESC LIMIT 1",(r,s))
        if not job:return None
        content=self.s.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
        return {"shop_id":s,"version":job["attempt"],"title":content["title"],"description":content["description"],
                "images":[{k:v for k,v in x.items() if k!="asset_id"} for x in content["cover_options"]],
                "video":{k:v for k,v in content["video_job"].items() if k!="asset_id"},"feedback_history":content["feedback_history"],"style_notes":content["style_notes"],"checks":content["validation"]}

    def state(self,c,p):
        run=self.current(c,p);r=run["run_id"];self.s.scope(c,p,r,"D",{"seller"})
        card=one(c,"SELECT * FROM cards WHERE run_id=? AND shop_id='D' AND status='pending'",(r,))
        active=one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id='D' AND status='active'",(r,))
        handoff=one(c,"SELECT * FROM learning_handoffs WHERE run_id=? ORDER BY day DESC LIMIT 1",(r,))
        original=self.s.public(c,r,"D").copy()
        from .seed import world
        original.update({k:v for k,v in world()["shops"]["D"]["public"].items() if k not in {"images"}})
        seed_content=one(c,"SELECT * FROM content_versions WHERE run_id=? AND product_id='SP004' AND content_version=1",(r,))
        original["images"]=[f"/api/v1/runs/{r}/assets/{seed_content['cover_asset_id']}/download"]
        phase=run["phase"]
        step={"ready":"idle","awaiting_seller":"awaiting_decision","negotiating":"day_done","content_review":"content_review","settling":"day_done","learning":"day_done","day_closed":"night_done","complete":"complete","failed":"day_done"}[phase]
        if card:step="awaiting_decision"
        return {"run_id":r,"day":run["current_day"],"mode":run["mode"],"memory_enabled":bool(run["memory_enabled"]),"step":step,
                "demo_shop":self.s.public(c,r,"D"),"demo_shop_original":original,
                "active_package":{"package":active["package_snapshot"],"start_day":active["start_day"],"end_day":active["end_day"],"ads_paused":active["ads_status"]=="paused","card_id":""} if active else None,
                "pending_card":self.card(c,r,card),"content_draft":self.draft(c,r),"last_night":handoff["night_summary"] if handoff else None,"live_calls_left":0}

    def decide(self,c,p,r,body):
        self.s.scope(c,p,r,"D",{"seller"})
        require(set(body)<={"card_id","action","note_vi","edited_package","rule_answer"},"INVALID_FIELDS","Trường không được hỗ trợ",422)
        card=self.s.entity(c,"cards",r,"card_id",body["card_id"])
        require(card["shop_id"]=="D" and card["status"]=="pending","NOT_FOUND","Không tìm thấy thẻ đang chờ",404)
        if card["question_id"] and body.get("rule_answer") is not None:
            q=self.s.entity(c,"rule_questions",r,"question_id",card["question_id"])
            self.s.decision(c,p,r,dict(target_type="rule_question",target_id=q["question_id"],target_version=1,action="approve" if body["rule_answer"] else "reject",rule_answer=body["rule_answer"]))
        if card["kind"]=="question":
            require(body.get("rule_answer") is not None,"ANSWER_REQUIRED","Cần trả lời câu hỏi",422)
            c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
        else:
            require(body.get("action") in {"accept","edit","reject","negotiate"},"ACTION_INVALID","Hành động không hợp lệ",422)
            prop=self.s.entity(c,"proposals",r,"proposal_id",card["proposal_id"])
            decision=self.s.decision(c,p,r,dict(target_type="proposal",target_id=prop["proposal_id"],target_version=prop["version"],action={"accept":"approve","edit":"approve","reject":"reject","negotiate":"request_changes"}[body["action"]],edited_package=body.get("edited_package"),feedback_private=body.get("note_vi","")))
            internal=self.internal(p,r)
            if body["action"] in {"accept","edit"}:
                prop=self.s.entity(c,"proposals",r,"proposal_id",decision["target_id"])
                _,ver=self.s.evaluation(c,r,"D",prop["package"])
                self.s.apply(c,internal,r,dict(proposal_id=prop["proposal_id"],approval_decision_id=decision["decision_id"],expected_inventory_version=ver["inventory_version"],expected_rules_version=ver["rules_version"]))
                if prop["package"]["content_refresh"]:self.s.content_create(c,internal,r,"D",dict(proposal_id=prop["proposal_id"],product_id=prop["product_id"]))
                else:c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
            elif body["action"]=="negotiate":
                # An authorized reference driver, not an agent model, handles the local branch.
                self.s.reference_offer(c,internal,r,"D",source_card_id=card["card_id"],owner_note=body.get("note_vi"))
            else:c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
        state=self.state(c,p)
        return {"step":state["step"],"card":state["pending_card"]}

    def retry(self,c,p,r,body):
        require(set(body)=={"feedback_vi"},"INVALID_FIELDS","Cần feedback_vi",422)
        job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D' ORDER BY rowid DESC LIMIT 1",(r,))
        require(job,"CONTENT_REQUIRED","Chưa có nội dung")
        self.s.content_create(c,p,r,"D",dict(proposal_id=job["proposal_id"],product_id=job["product_id"],feedback_vi=body["feedback_vi"],expected_current_attempt=job["attempt"]))
        return {"draft":self.draft(c,r)}

    def use_content(self,c,p,r,body):
        require(set(body)=={"cover_option"},"INVALID_FIELDS","Cần cover_option",422)
        job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D' ORDER BY rowid DESC LIMIT 1",(r,))
        require(job,"CONTENT_REQUIRED","Chưa có nội dung")
        content=self.s.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
        d=self.s.decision(c,p,r,dict(target_type="content",target_id=content["content_id"],target_version=content["version"],action="approve",cover_option=body["cover_option"]))
        listing=self.s.publish(c,self.internal(p,r),r,content["content_id"],dict(approval_decision_id=d["decision_id"],expected_active_content_id=self.s.product(c,r,"D")["active_content_id"]))
        return {"listing":listing}

    def night(self,c,p,r):
        run=self.s.run(c,p,r)
        self.s.operation(c,p,r,"close_day",dict(expected_day=run["current_day"],expected_version=run["version"]))
        run=self.s.run(c,p,r)
        handoff=one(c,"SELECT * FROM learning_handoffs WHERE run_id=? AND day=?",(r,run["current_day"]))
        self.s.operation(c,p,r,"advance_day",dict(expected_day=run["current_day"],expected_version=run["version"]))
        run=self.s.run(c,p,r)
        return {"summary":handoff["night_summary"],"next_day":None if run["phase"]=="complete" else run["current_day"]}
