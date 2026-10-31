"""Durable orchestration seams. No LLM, provider or agent memory is owned here."""

from datetime import datetime, timezone
import hashlib
import json
import re
import os
from urllib.parse import urlsplit,parse_qs

from . import models as M
from .errors import Fault, require
from .finance import redact, financials
from .simulation import business_date, aggregate
from .storage import dumps, fingerprint, insert, many, now, one, timestamps, uid


class IntegrationMixin:
    @staticmethod
    def operation_view(op,role=None):
        result={key: op.get(key) for key in ("operation_id", "day", "kind", "status", "result", "error_code", "version", "lease_until")}
        if result["result"] and role not in {"orchestrator","evaluator","data_admin"} and result["result"].get("trace_shop_id")!="D":
            result["result"]={key:value for key,value in result["result"].items() if key!="trace_url"}
        return result

    def queue_renegotiation(self, c, p, r, card_id, note):
        run = self.run(c, p, r)
        oid = uid("operation")
        insert(c, "operations", run_id=r, operation_id=oid, day=run["current_day"], kind=f"renegotiate:{card_id}", status="queued", result_json={"source_card_id": card_id, "owner_note_vi": note}, error_code=None, lease_until=None, claimed_by=None, **timestamps())
        c.execute("UPDATE runs SET phase='negotiating',version=version+1 WHERE run_id=?", (r,))
        return oid
    def fee_config(self, c, r, version=None, day=None):
        version = version or one(c, "SELECT fee_policy_version FROM run_policies WHERE run_id=?", (r,))["fee_policy_version"]
        day=day if day is not None else self.entity(c,"runs",r,"run_id",r)["current_day"]
        rows = many(c, "SELECT * FROM fee_rules WHERE policy_version=? AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?)", (version,business_date(day),business_date(day)))
        require(rows, "POLICY_UNAVAILABLE", "Không tìm thấy chính sách phí", 409)
        return {"rate_bps": sum(x["rate_bps"] or 0 for x in rows),
                "per_order": sum(x["fixed_vnd"] or 0 for x in rows)}, version

    def current_cost(self, c, r, s, day=None, version=None):
        product = self.product(c, r, s)
        run = self.entity(c, "runs", r, "run_id", r)
        sql = "SELECT * FROM product_costs WHERE run_id=? AND product_id=?"
        args = [r, product["product_id"]]
        if version is not None:
            sql += " AND cost_version=?"; args.append(version)
        else:
            sql += " AND effective_day<=?"; args.append(run["current_day"] if day is None else day)
        result = one(c, sql + " ORDER BY cost_version DESC LIMIT 1", args)
        require(result, "COST_UNAVAILABLE", "Chưa có giá vốn tại ngày này", 409)
        return result

    def eligibility(self, c, r, s):
        public = self.public(c, r, s)
        run = self.entity(c, "runs", r, "run_id", r)
        runtime = self.entity(c, "shop_runtime", r, "shop_id", s)
        reasons = []
        if public["stock"] < 30: reasons.append("STOCK_BELOW_MINIMUM")
        if one(c, "SELECT campaign_id FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'", (r, s)):
            reasons.append("ACTIVE_PACKAGE")
        if run["current_day"] < runtime["cooldown_until_day"]: reasons.append("COOLDOWN")
        if public["listing_quality"] >= .6 and public["search_rank_page"] < 2: reasons.append("LISTING_ALREADY_STRONG")
        growth = self.market_summary(c, r, run)["growth_7d_pct"]
        if growth is None or growth <= 0: reasons.append("NO_POSITIVE_TREND")
        return {"eligible": not reasons, "reason_codes": reasons}

    def safe_text(self, c, r, text, own_shop=None):
        """Strip shared financial secrets; seller view may retain its own values."""
        sensitive=r'giá\s*vốn|vốn\s*nhập|lãi\s*(?:tối\s*thiểu|mỗi\s*đơn|trên\s*mỗi\s*đơn)|(?:roas\s*)?hòa\s*vốn|(?:roas\s*)?hoà\s*vốn|private[_\s-]*note'
        if own_shop is None and re.search(sensitive,text,re.IGNORECASE):
            return 'Shop đề xuất điều chỉnh gói để phù hợp với quy tắc đã đặt.'
        from .seed import world
        owners=world()['shops']
        for s in "ABCDE":
            if s == own_shop:
                continue
            owner=owners[s]['private']['owner_name']
            if owner and re.search(r'(?<!\w)'+re.escape(owner)+r'(?!\w)',text,re.IGNORECASE):
                return 'Shop đề xuất điều chỉnh gói để phù hợp với quy tắc đã đặt.'
            cost = self.current_cost(c, r, s)["unit_cost_vnd"]
            rules, _ = self.rules(c, r, s)
            text = redact(text, self.product(c, r, s)["list_price_vnd"], cost, rules, self.fee_config(c,r)[0])
        return text

    def job_access(self, c, p, r, jid):
        job = self.entity(c, "content_jobs", r, "job_id", jid)
        self.scope(c, p, r, job["shop_id"])
        if p.role == "content_worker":
            require("*" in p.allowed_job_ids or jid in p.allowed_job_ids,
                    "NOT_FOUND", "Job không được giao", 404)
        return job

    def operation_claim(self, c, p, r, oid, body):
        self.scope(c, p, r, roles={"orchestrator"})
        b = M.Version.model_validate(body)
        op = self.entity(c, "operations", r, "operation_id", oid)
        run=self.run(c,p,r)
        require(run["current_day"]==op["day"] and run["phase"] not in {"settling","learning","day_closed","complete"},"DAY_CLOSED","Operation không còn thuộc ngày đang chạy")
        require(op["kind"] == "start_day" or op["kind"].startswith("renegotiate:"), "OPERATION_INTERNAL", "Operation do Data API điều phối", 403)
        require(op["version"] == b.expected_version and op["status"] == "queued")
        c.execute("UPDATE operations SET status='running',claimed_by=?,lease_until=?,version=version+1,updated_at=? WHERE run_id=? AND operation_id=?",
                  (p.principal_id, self.expires(120), now(), r, oid))
        return self.entity(c, "operations", r, "operation_id", oid)

    def operation_result(self, c, p, r, oid, body):
        self.scope(c, p, r, roles={"orchestrator"})
        b = M.OperationResult.model_validate(body)
        op = self.entity(c, "operations", r, "operation_id", oid)
        run=self.run(c,p,r)
        require(run["current_day"]==op["day"] and run["phase"] not in {"settling","learning","day_closed","complete"},"DAY_CLOSED","Operation không còn thuộc ngày đang chạy")
        require((op["kind"] == "start_day" or op["kind"].startswith("renegotiate:")) and op["claimed_by"] == p.principal_id,
                "FORBIDDEN", "Operation chưa được giao cho caller", 403)
        require(op["version"] == b.expected_version and op["status"] == "running")
        require(op["lease_until"] and op["lease_until"]>=now(),"LEASE_EXPIRED","Lease operation đã hết hạn")
        if b.status == "succeeded":
            require(not one(c, "SELECT negotiation_id FROM negotiations WHERE run_id=? AND day=? AND status='running'", (r, op["day"])),
                    "NEGOTIATION_PENDING", "Còn thương lượng chưa hoàn tất")
            require(not one(c,"SELECT n.negotiation_id FROM negotiations n JOIN proposals p ON p.run_id=n.run_id AND p.proposal_id=n.final_proposal_id WHERE n.run_id=? AND n.day=? AND n.status IN ('agreed','warning_only') AND p.status='validated'",(r,op["day"])),"CARD_NOT_PRESENTED","Còn final proposal chưa trình seller")
            demo=run['demo_shop_id']
            q=one(c,"SELECT * FROM rule_questions WHERE run_id=? AND shop_id=? AND status='pending' ORDER BY rowid LIMIT 1",(r,demo))
            card = one(c, "SELECT card_id FROM cards WHERE run_id=? AND shop_id=? AND status='pending'", (r,demo))
            if q and not card and one(c,"SELECT campaign_id FROM campaigns WHERE run_id=? AND shop_id=? AND status='active'",(r,demo)):
                self.make_card(c,r,demo,op["day"],question=q)
                card=True
            c.execute("UPDATE runs SET phase=?,version=version+1 WHERE run_id=?", ("awaiting_seller" if card else "negotiating", r))
        if b.status == "failed":
            self.event(c, r, op["day"], "operation_failed", "orchestrator", visibility="internal", payload={"operation_id": oid, "error_code": b.error_code})
        result=op["result"] or {}
        if b.trace_url:
            url=urlsplit(b.trace_url)
            allowed={x.strip() for x in os.environ.get("GROWTH_TRACE_HOSTS","").split(',') if x.strip()}
            require(url.scheme=="https" and url.hostname in allowed and not url.username and not url.password and not any(re.search("token|key|secret|password",key,re.I) for key in parse_qs(url.query)),"TRACE_URL_INVALID","Trace URL phải thuộc host cấu hình, không có credential",422)
            result={**result,"trace_url":b.trace_url,"trace_shop_id":b.trace_shop_id}
        c.execute("UPDATE operations SET status=?,error_code=?,lease_until=?,version=version+1,updated_at=? WHERE run_id=? AND operation_id=?",
                  (b.status, b.error_code, self.expires(120) if b.status == "running" else None, now(), r, oid))
        c.execute("UPDATE operations SET result_json=? WHERE run_id=? AND operation_id=?",(dumps(result),r,oid))
        return self.entity(c, "operations", r, "operation_id", oid)

    def begin_night(self, p, r, key, expected_day=None):
        def begin(c):
            run = self.scope(c, p, r, roles={"seller"})
            day = run["current_day"]
            require(expected_day is None or expected_day==day,'DAY_CHANGED','Ngày đã thay đổi')
            previous = one(c, "SELECT * FROM operations WHERE run_id=? AND day=? AND kind='night'", (r, day))
            if previous:
                return {"operation_id": previous["operation_id"], "day": day}
            self.operation(c, p, r, "close_day", {"expected_day": day, "expected_version": run["version"]})
            oid = uid("operation")
            insert(c, "operations", run_id=r, operation_id=oid, day=day, kind="night", status="running",
                   result_json=None, error_code=None, lease_until=None, claimed_by=None, **timestamps())
            c.execute("UPDATE learning_handoffs SET auto_advance=1 WHERE run_id=? AND day=?", (r, day))
            self.finish_night_tx(c, r, day)
            return {"operation_id": oid, "day": day}
        receipt = self.command(p, r, "/api/night", key, {} if expected_day is None else {'expected_day':expected_day}, begin)
        with self.store.connect() as c:
            return self.entity(c, "operations", r, "operation_id", receipt["operation_id"])

    def finish_night_tx(self, c, r, day):
        from .service import Principal
        handoff = one(c, "SELECT * FROM learning_handoffs WHERE run_id=? AND day=?", (r, day))
        op = one(c, "SELECT * FROM operations WHERE run_id=? AND day=? AND kind='night'", (r, day))
        if not op or op["status"] == "succeeded" or not handoff or not handoff["auto_advance"]:
            return
        if handoff["status"] == "failed":
            c.execute("UPDATE operations SET status='failed',error_code=?,version=version+1 WHERE run_id=? AND operation_id=? AND status!='failed'", (handoff["error_code"], r, op["operation_id"]))
            return
        if handoff["status"] not in {"completed", "skipped"}:
            return
        run = self.entity(c, "runs", r, "run_id", r)
        if run["current_day"] == day and run["phase"] == "day_closed":
            internal = Principal("night_adapter", "orchestrator", None, (r,), ("*",))
            self.operation(c, internal, r, "advance_day", {"expected_day": day, "expected_version": run["version"]})
        run = self.entity(c, "runs", r, "run_id", r)
        result = {"summary": handoff["night_summary"], "next_day": None if run["phase"] == "complete" else run["current_day"]}
        c.execute("UPDATE operations SET status='succeeded',result_json=?,error_code=NULL,version=version+1,updated_at=? WHERE run_id=? AND operation_id=?", (dumps(result), now(), r, op["operation_id"]))

    def learning_control(self, c, p, r, day, action, body):
        self.scope(c, p, r, roles={"seller", "orchestrator"})
        b = M.LearningControl.model_validate(body)
        h = one(c, "SELECT * FROM learning_handoffs WHERE run_id=? AND day=?", (r, day))
        require(h, "NOT_FOUND", "Không có handoff", 404)
        run = self.run(c, p, r)
        allowed={'failed'} if action=='retry' else {'pending','running','failed'}
        require(run["current_day"] == day and h["version"] == b.expected_version and h["status"] in allowed)
        reflection=one(c,'SELECT status FROM reflection_receipts WHERE run_id=? AND day=?',(r,day))
        if action=='retry': require(not reflection or reflection['status'] not in {'reserved','unknown'},'REFLECTION_UNKNOWN','Kết quả học chưa rõ; không gửi lại model')
        status = "pending" if action == "retry" else "skipped"
        summary = None if action == "retry" else self.empty_summary(day)
        c.execute("UPDATE learning_handoffs SET status=?,night_summary_json=?,error_code=?,version=version+1,attempt=attempt+1,lease_until=?,updated_at=? WHERE run_id=? AND day=?",
                  (status, dumps(summary) if summary else None, None if action == "retry" else "SELLER_SKIPPED", self.expires(60) if action == "retry" else None, now(), r, day))
        c.execute("UPDATE runs SET phase=?,version=version+1 WHERE run_id=?", ("learning" if action == "retry" else "day_closed", r))
        c.execute("UPDATE operations SET status='running',error_code=NULL,version=version+1 WHERE run_id=? AND day=? AND kind='night'", (r, day))
        self.event(c, r, day, "learning_control", p.role, "D", {"action": action, "reason_vi": self.safe_text(c, r, b.reason_vi, "D")}, visibility="shop_private")
        self.finish_night_tx(c, r, day)
        return one(c, "SELECT * FROM learning_handoffs WHERE run_id=? AND day=?", (r, day))

    @staticmethod
    def empty_summary(day):
        return {"day": day, "history_updates": [], "pref_candidates": [], "calibration": {"factor": 1.0, "points": 0, "mape_today": None}, "lesson_ops": [], "rejected_ops": 0, "memory_md_path": ""}

    def learning_result(self, c, p, r, body):
        self.scope(c, p, r, roles={"learning_worker"})
        b = M.LearningResult.model_validate(body)
        self.scope(c, p, r, b.shop_id)
        run=self.run(c,p,r)
        require(not (b.status=='completed' and run['config'].get('driver',{}).get('agent_version')=='native'),'NATIVE_PUBLICATION_REQUIRED','Hoàn tất học phải đi qua giao dịch publication')
        require(b.shop_id == run['demo_shop_id'], "SUMMARY_SCOPE", "Handoff không thuộc shop của run", 422)
        h = one(c, "SELECT * FROM learning_handoffs WHERE run_id=? AND day=?", (r, b.day))
        require(h and h["settlement_cursor"] == b.settlement_cursor, "EVIDENCE_INVALID", "Sai evidence cursor", 409)
        if h["status"] in {"completed", "failed"} and b.receipt_id and h["receipt_id"] == b.receipt_id:
            require(h["receipt_hash"]==fingerprint(body),"HANDOFF_TERMINAL","Receipt có request khác")
            require(h["status"] == b.status, "HANDOFF_TERMINAL", "Receipt có kết quả khác")
            summary = b.night_summary.model_dump() if b.night_summary else None
            if summary:
                summary["memory_md_path"] = h["night_summary"]["memory_md_path"]
            require(summary == h["night_summary"], "HANDOFF_TERMINAL", "Receipt có nội dung khác")
            return {"day": b.day, "status": h["status"], "version": h["version"]}
        require(h["version"] == b.expected_version and h["status"] in {"pending", "running"}, "HANDOFF_TERMINAL", "Handoff/version không còn nhận kết quả")
        require(b.status=="failed" or (h["lease_until"] and h["lease_until"]>=now()),"LEASE_EXPIRED","Lease học đã hết hạn")
        if b.status == "running":
            c.execute("UPDATE learning_handoffs SET status='running',lease_until=?,version=version+1,updated_at=? WHERE run_id=? AND day=?", (self.expires(60), now(), r, b.day))
            return {"day": b.day, "status": "running", "version": h["version"]+1}
        require(b.night_summary is not None and b.night_summary.day == b.day, "SUMMARY_INVALID", "Cần summary đúng ngày", 422)
        summary = b.night_summary.model_dump()
        summary["memory_md_path"] = ""
        for op in summary["lesson_ops"]:
            category=self.entity(c,"shops",r,"shop_id",b.shop_id)["category"]
            require(op["scope"] in {"strategy", category}, "SUMMARY_SCOPE", "Sai scope bài học", 422)
            for evidence in op["evidence"]:
                require(one(c, "SELECT negotiation_id FROM negotiations WHERE run_id=? AND shop_id=? AND negotiation_id=? AND day<=?", (r, b.shop_id, evidence, b.day)), "EVIDENCE_INVALID", "Bằng chứng không thuộc shop/ngày được giao", 422)
            require(self.safe_text(c, r, op["text_vi"]) == op["text_vi"], "PRIVATE_TEXT", "Bài học chứa tài chính riêng", 422)
        require(set(b.lesson_scores) <= {op["lesson_id"] for op in summary["lesson_ops"] if op["lesson_id"]}, "EVIDENCE_INVALID", "Điểm không gắn lesson đã báo cáo", 422)
        # Free text is only a presentation, never a second learned-memory store.
        for name in ("history_updates", "pref_candidates"):
            summary[name] = [self.safe_text(c, r, text, b.shop_id) for text in summary[name]]
        if b.memory_report_asset_id:
            asset = self.asset_access(c, p, r, b.memory_report_asset_id)
            require(asset["kind"] == "document" and asset["purpose"] == "learning_report" and asset["upload_status"] == "ready", "REPORT_INVALID", "Report chưa sẵn sàng", 422)
        # Generate a separate seller-safe report from validated typed fields, not
        # from the arbitrary internal attachment supplied by the worker.
        aid = uid("asset")
        content = (f"# Tối ngày {b.day} — shop {b.shop_id}\n\n" + json.dumps({**summary, "lesson_scores": b.lesson_scores}, ensure_ascii=False, indent=2)).encode()
        key = f"reports/{r}/{aid}.md"
        path = self.object_path(key); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
        insert(c, "assets", run_id=r, asset_id=aid, shop_id=b.shop_id, product_id=None, kind="document", object_key=key, mime_type="text/markdown", size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), width=None, height=None, duration_seconds=None, origin="generated", source_reference=f"handoff:{b.day}:{b.settlement_cursor}", visibility="shop_private", upload_status="ready", upload_owner=p.principal_id, purpose="seller_report", job_id=None, created_at=now())
        summary["memory_md_path"] = f"/api/v1/runs/{r}/assets/{aid}/download"
        presentation = {"lesson_scores": b.lesson_scores, "source": "external_worker", "shop_id": b.shop_id}
        c.execute("UPDATE learning_handoffs SET status=?,night_summary_json=?,memory_report_asset_id=?,error_code=?,receipt_id=?,receipt_hash=?,summary_shop_id=?,presentation_json=?,lease_until=NULL,version=version+1,updated_at=? WHERE run_id=? AND day=?",
                  (b.status, dumps(summary), b.memory_report_asset_id, b.error_code, b.receipt_id, fingerprint(body), b.shop_id, dumps(presentation), now(), r, b.day))
        c.execute("UPDATE runs SET phase=?,version=version+1 WHERE run_id=?", ("day_closed" if b.status == "completed" else "learning", r))
        self.event(c, r, b.day, "night_summary", "learning_worker", b.shop_id, {"summary": summary, "status": b.status}, visibility="shop_private", text="Worker đã báo kết quả học" if b.status == "completed" else "Học thất bại; chưa chuyển ngày")
        self.finish_night_tx(c, r, b.day)
        return {"day": b.day, "status": b.status, "version": h["version"]+1}

    def night_view(self, c, p, r, s, day):
        self.scope(c, p, r, s, {"seller", "shop_agent", "orchestrator", "evaluator", "data_admin"})
        run = self.run(c, p, r)
        require(1 <= day <= run["current_day"], "FUTURE_UNAVAILABLE", "Ngày chưa quan sát", 422)
        rows = many(c, "SELECT * FROM daily_metrics WHERE run_id=? AND shop_id=? AND day=? AND source='simulated'", (r, s, day))
        require(len(rows) == 2, "DAY_NOT_SETTLED", "Ngày chưa chốt", 409)
        f = one(c, "SELECT f.* FROM forecasts f JOIN campaigns a ON a.run_id=f.run_id AND a.proposal_id=f.proposal_id WHERE f.run_id=? AND a.shop_id=? AND a.start_day<=? AND a.end_day>=? AND f.period_start_day<=? AND f.period_end_day>=? ORDER BY a.start_day DESC LIMIT 1", (r, s, day, day, day, day))
        paid = next(x for x in rows if x["channel"] == "paid")
        campaign = self.entity(c, "campaigns", r, "campaign_id", paid["campaign_id"]) if paid["campaign_id"] else None
        h = one(c, "SELECT * FROM learning_handoffs WHERE run_id=? AND day=?", (r, day))
        paid = next(x for x in rows if x["channel"] == "paid")
        # Reconstruct the streak as of this day; the campaign row may be newer.
        streak = 0
        if campaign:
            past = many(c, "SELECT * FROM daily_metrics WHERE run_id=? AND campaign_id=? AND day<=? ORDER BY day DESC", (r, campaign["campaign_id"], day))
            for m in past:
                if not m["ad_spend_vnd"] or m["realized_roas"] >= campaign["package_snapshot"]["stop_roas_below"]: break
                streak += 1
        own_summary = h and h["summary_shop_id"] == s
        return {"day": day, "shop_id": s, "actual_orders": sum(x["orders"] for x in rows),
                "forecast_orders": f["daily_point_units"][day-f["period_start_day"]] if f else None,
                "raw_forecast": f["raw_daily_units"][day-f["period_start_day"]] if f else None,
                "paid_roas": paid["realized_roas"], "paid_spend_vnd": paid["ad_spend_vnd"], "low_roas_streak": streak,
                "learning_status": h["status"] if h else None, "learning_error": h["error_code"] if h else None,
                "summary": h["night_summary"] if own_summary else None,
                "presentation": h["presentation"] if own_summary else {}}

    def restore_content(self, c, p, r, cid, body):
        b=M.Restore.model_validate(body)
        target=self.entity(c,"content_versions",r,"content_id",cid)
        product=self.entity(c,"products",r,"product_id",target["product_id"])
        run=self.scope(c,p,r,product["shop_id"],{"seller"})
        receipt=one(c,"SELECT * FROM restore_receipts WHERE run_id=? AND source_content_id=? AND previous_content_id=?",(r,cid,b.expected_active_content_id))
        if receipt:
            require(receipt["request_hash"]==fingerprint(body),"RESTORE_CONFLICT","Yêu cầu hoàn tác có version khác")
            return receipt["result"]
        require(product["active_content_id"]==b.expected_active_content_id and target["version"]==b.expected_content_version)
        require(target["published_day"] is not None and cid!=product["active_content_id"],"RESTORE_INVALID","Chỉ khôi phục bản đã từng xuất bản",422)
        require(not one(c,"SELECT content_id FROM content_versions WHERE run_id=? AND product_id=? AND status IN ('draft','validated')",(r,product["product_id"])),"PENDING_CONTENT","Xử lý draft trước khi hoàn tác")
        asset=self.asset_access(c,p,r,target["cover_asset_id"])
        require(asset["upload_status"]=="ready","ASSET_PENDING","Ảnh bản cũ chưa sẵn sàng")
        new_id,did=uid("content"),uid("decision")
        version=c.execute("SELECT MAX(content_version)+1 FROM content_versions WHERE run_id=? AND product_id=?",(r,product["product_id"])).fetchone()[0]
        self.persist_copy(c,"content_versions",target,content_id=new_id,content_version=version,parent_content_id=cid,status="published",version=1,published_day=run["current_day"],created_at=now(),updated_at=now())
        insert(c,"decisions",run_id=r,decision_id=did,shop_id=product["shop_id"],target_type="content",target_id=new_id,target_version=1,action="approve",edited_package_json=None,cover_option=None,rule_answer=None,actor_type=p.role,actor_id=p.principal_id,feedback_private="Seller xác nhận khôi phục",feedback_shared=None,created_at=now())
        c.execute("UPDATE content_versions SET status='superseded',version=version+1 WHERE run_id=? AND content_id=?",(r,product["active_content_id"]))
        c.execute("UPDATE products SET active_content_id=?,version=version+1 WHERE run_id=? AND product_id=?",(new_id,r,product["product_id"]))
        self.event(c,r,run["current_day"],"content_restored","seller",product["shop_id"],{"source_content_id":cid,"content_id":new_id,"decision_id":did},text="Đã khôi phục nội dung; không đổi quảng cáo/voucher")
        result={"listing":self.public(c,r,product["shop_id"]),"content_id":new_id}
        insert(c,"restore_receipts",run_id=r,source_content_id=cid,previous_content_id=product["active_content_id"],result_content_id=new_id,decision_id=did,request_hash=fingerprint(body),result_json=result)
        return result

    def register_recording(self,c,p,r,body):
        self.scope(c,p,r,roles={"orchestrator","data_admin"})
        require(set(body)=={"recording_asset_id"} and isinstance(body["recording_asset_id"],str),"RECORDING_SCHEMA","Cần recording_asset_id",422)
        asset=self.asset_access(c,p,r,body["recording_asset_id"])
        require(asset["purpose"]=="replay_recording" and asset["upload_status"]=="ready" and asset["mime_type"]=="text/markdown","RECORDING_SCHEMA","Cần manifest JSON trong document UTF-8 nội bộ",422)
        try:manifest=M.RecordingManifest.model_validate_json(self.object_path(asset["object_key"]).read_bytes())
        except ValueError:raise Fault("RECORDING_SCHEMA","Recording manifest không hợp lệ",422)
        run=self.run(c,p,r)
        cursor=c.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE run_id=?",(r,)).fetchone()[0]
        require(manifest.run_id==r and run["phase"]=="complete" and manifest.events_through==cursor,"RECORDING_INCOMPLETE","Recording phải thuộc run hoàn tất và đúng event boundary")
        require(len({x.call_id for x in manifest.calls})==len(manifest.calls),"RECORDING_SCHEMA","Call IDs phải duy nhất",422)
        for call in manifest.calls:
            response=self.asset_access(c,p,r,call.response_asset_id)
            require(response["purpose"]=="replay_recording" and response["upload_status"]=="ready","RECORDING_INCOMPLETE","Thiếu response artifact",422)
        old=one(c,"SELECT * FROM run_artifacts WHERE run_id=? AND kind='recording'",(r,))
        if old:
            require(old["sha256"]==asset["sha256"],"RECORDING_CONFLICT","Recording đã được chốt")
            return
        insert(c,"run_artifacts",run_id=r,kind="recording",asset_id=asset["asset_id"],sha256=asset["sha256"],metadata_json=manifest.model_dump(),created_at=now())

    def ingest_event(self, c, p, r, body):
        b = M.ExternalEvent.model_validate(body)
        run = self.scope(c, p, r, b.shop_id)
        allowed = {"opportunity": {"platform_agent", "orchestrator"}, "memory_read": {"platform_agent", "shop_agent", "orchestrator"},
                   "memory_write": {"learning_worker"}, "referee_review": {"orchestrator"}, "agent_telemetry": {"orchestrator"}}
        require(p.role in allowed[b.type], "FORBIDDEN", "Writer không được ghi event này", 403)
        require(b.day == run["current_day"], "EVIDENCE_INVALID", "Event phải thuộc ngày hiện tại", 422)
        fields = {"opportunity": {"chosen", "excluded", "keyword", "growth_7d_pct"},
                  "memory_read": {"who", "items", "memory_revision"}, "memory_write": {"compartment", "receipt_id", "memory_revision"},
                  "referee_review": {"negotiation_id", "round", "action", "reason_vi", "evidence_refs", "unresolved_terms", "next_actor", "focused_question"},
                  "agent_telemetry": {"negotiation_id", "task_id", "status", "phase", "label_vi", "round"}}
        require(set(b.data) <= fields[b.type], "EVENT_SCHEMA", "Event có trường không hỗ trợ", 422)
        if b.type == "opportunity":
            touched=set(b.data.get("chosen", [])) | {x["shop_id"] for x in b.data.get("excluded",[])}
            require("*" in p.allowed_shop_ids or touched <= set(p.allowed_shop_ids), "EVENT_SCOPE", "Không ghi shop ngoài scope", 422)
        if b.type in {"referee_review", "agent_telemetry"}:
            neg = self.entity(c, "negotiations", r, "negotiation_id", b.data.get("negotiation_id"))
            require(neg["shop_id"] == b.shop_id, "EVENT_SCOPE", "Sai negotiation shop", 422)
            if b.type=="referee_review":
                for seq in b.data.get("evidence_refs",[]):
                    evidence=one(c,"SELECT * FROM events WHERE run_id=? AND seq=?",(r,seq))
                    require(evidence and evidence["visibility"]=="shared" and evidence["shop_id"]==b.shop_id and evidence["payload"].get("negotiation_id")==neg["negotiation_id"],"EVIDENCE_INVALID","Trọng tài chỉ đọc evidence shared đúng negotiation",422)
            if b.type=="agent_telemetry":
                old_task=one(c,"SELECT * FROM events WHERE run_id=? AND type='agent_telemetry' AND json_extract(payload_json,'$.task_id')=? ORDER BY seq DESC LIMIT 1",(r,b.data["task_id"]))
                require(not (old_task and old_task["payload"]["status"] in {"done","failed","stopped"}),"TASK_TERMINAL","Task đã kết thúc")
                require(b.data["status"]!="running" or neg["status"]=="running","TASK_TERMINAL","Attempt đã kết thúc")
        if b.type == "memory_write":
            h = one(c, "SELECT * FROM learning_handoffs WHERE run_id=? AND day=?", (r, b.day))
            require(h and h["receipt_id"] == b.data.get("receipt_id") and h["status"] == "completed", "EVIDENCE_INVALID", "Thiếu memory receipt đã hoàn tất", 422)
        digest = fingerprint(body)
        old = one(c, "SELECT * FROM external_event_receipts WHERE run_id=? AND principal_id=? AND external_id=?", (r, p.principal_id, b.external_id))
        if old:
            require(old["request_hash"] == digest, "EVENT_CONFLICT", "External ID có nội dung khác")
            return {"seq": old["seq"]}
        def clean(value):
            if isinstance(value, str): return self.safe_text(c, r, value)
            if isinstance(value, list): return [clean(x) for x in value]
            if isinstance(value, dict): return {key: clean(value) for key, value in value.items()}
            return value
        seq = self.event(c, r, b.day, b.type, p.role, b.shop_id, clean(b.data), text=self.safe_text(c, r, b.text_vi), eid=b.entity_id or b.external_id)
        insert(c, "external_event_receipts", run_id=r, principal_id=p.principal_id, external_id=b.external_id, request_hash=digest, seq=seq)
        return {"seq": seq}
