"""HTTP-only fake agents/workers for Gate A. Never a live-learning claim.

Token provisioning is injected by the local test/CLI administrator. All business
reads and writes thereafter go through HTTP, including media and learning.
"""

import hashlib
import re
import uuid

from .finance import safe_package
from .seed import placeholder_png


class HttpHarness:
    def __init__(self, client, issue_token):
        self.client=client
        self.issue_token=issue_token
        self.calls=[]
        self.memory={}

    def token(self,r,role,s="*",job=None):
        return self.issue_token(role,runs=(r,),shops=(s,),jobs=(job,) if job else ())

    def request(self,method,path,body=None,token=None,key=None,content=None):
        headers={"Idempotency-Key":key or uuid.uuid4().hex,"X-Request-ID":"gate-a-fixture"}
        if token:headers["Authorization"]="Bearer "+token
        kwargs={"headers":headers}
        if body is not None:kwargs["json"]=body
        if content is not None:kwargs["content"]=content
        response=self.client.request(method,path,**kwargs)
        assert 200<=response.status_code<300,(method,path,response.status_code,response.text[:1000])
        self.calls.append((method,path.split('?')[0],response.status_code))
        if response.headers.get("content-type","").startswith("application/json"):
            result=response.json()
            return result["data"] if "data" in result and "meta" in result else result
        return response.content

    def get(self,path,token=None):return self.request("GET",path,token=token)
    def post(self,path,body,token=None,key=None):return self.request("POST",path,body,token,key)

    def upload(self,r,token,raw,kind="image",product="SP004",job=None,purpose="product_media"):
        mime={"image":"image/png","video":"video/mp4","document":"text/markdown"}[kind]
        sha=hashlib.sha256(raw).hexdigest()
        b={"product_id":product,"job_id":job,"kind":kind,"mime_type":mime,"size_bytes":len(raw),"sha256":sha,"purpose":purpose}
        uploaded=self.post(f"/api/v1/runs/{r}/assets/uploads",b,token)
        assert self.request("PUT",uploaded["upload"]["url"],token=token,content=raw)["stored"]
        aid=uploaded["asset_id"]
        assert self.post(f"/api/v1/runs/{r}/assets/{aid}/complete",{"checksum":sha},token)["upload_status"]=="ready"
        assert self.get(f"/api/v1/runs/{r}/assets/{aid}/download",token)==raw
        return aid

    def worker(self,r,job):
        jid=job["job_id"];token=self.token(r,"content_worker",job["shop_id"],jid)
        job=self.get(f"/api/v1/runs/{r}/content-jobs/{jid}",token)
        drafts=self.get(f"/api/v1/runs/{r}/shops/{job['shop_id']}/content",token)
        draft=next(x for x in drafts if x["content_id"] in job["output_content_ids"])
        images=[]
        for i,opt in enumerate("ABC",1):
            aid=self.upload(r,token,placeholder_png(i+job["attempt"]),product=job["product_id"],job=jid)
            images.append({"option":opt,"status":"done","asset_id":aid,"prompt":"Fixture hình học; không gọi provider"})
        # A MIME/signature fixture, deliberately not a claimed playable Muse video.
        # Gate B must supply a real video artifact and verify playback separately.
        video=draft["video_job"]
        if job["retry_scope"]=="text":images=draft["cover_options"]
        result={"expected_job_version":job["version"],"status":"succeeded","provider_job_id":"fixture-no-paid-provider",
                "content_candidates":{"title":draft["title"],"description":draft["description"],"images":images,"video":video,"checks":["Fixture: verified facts; media không phải ảnh/video live"]}}
        saved=self.post(f"/internal/v1/runs/{r}/content-jobs/{jid}/result",result,token)
        assert saved["status"]=="succeeded"
        return draft

    def negotiate(self,r,s,orchestrator,source_card=None,note=None,first_safe=False):
        base=f"/api/v1/runs/{r}/shops/{s}"
        platform=self.token(r,"platform_agent",s);shop=self.token(r,"shop_agent",s)
        public=self.get(base+"/context",platform)
        assert "private" not in public
        private=self.get(base+"/context",shop)
        versions=self.get(base+"/inventory",shop)
        # shop runtime version is server-returned in eligibility context.
        day=private["day"]
        neg=self.post(f"/internal/v1/runs/{r}/shops/{s}/negotiations",{"day":day,"expected_shop_version":private["shop_version"],"kind":"renew" if day>1 else "propose","source_card_id":source_card,"owner_note_vi":note},orchestrator)
        nid=neg["negotiation_id"]
        self.post(f"/internal/v1/runs/{r}/events",{"external_id":nid+"-memory","type":"memory_read","shop_id":s,"day":day,"text_vi":"Fixture agent đọc memory riêng của run","data":{"who":"platform","items":self.memory.get(r,{}).get("lessons",[]),"memory_revision":day-1}},platform)
        requested={"content_refresh":True,"ads_daily_budget":70000,"voucher_pct":10,"stop_roas_below":4.0,"stop_after_days":2,"duration_days":3}
        rules=private["private"]["rules"]
        safe=safe_package(private["shop"]["price"],private["private"]["unit_cost"],rules,private["shop"]["stock"])
        if note and re.search(r"2\s*%",note):safe["voucher_pct"]=2
        self.post(base+"/checks",{"product_id":private["product_id"],"package":safe},shop)
        first=self.post(base+"/proposals",{"product_id":private["product_id"],"negotiation_id":nid,"package":safe if first_safe else requested,"stance":"propose","shared_reason":"Fixture đề xuất qua HTTP"},platform)
        self.get(f"/api/v1/runs/{r}/proposals/{first['proposal_id']}",platform)
        counter=self.post(base+"/proposals",{"product_id":private["product_id"],"negotiation_id":nid,"parent_proposal_id":first["proposal_id"],"package":safe,"stance":"accept" if first_safe else "propose","shared_reason":"Fixture shop kiểm luật rồi phản hồi"},shop)
        final=counter if first_safe else self.post(base+"/proposals",{"product_id":private["product_id"],"negotiation_id":nid,"parent_proposal_id":counter["proposal_id"],"package":safe,"stance":"accept"},platform)
        self.post(f"/internal/v1/runs/{r}/negotiations/{nid}/finalize",{"expected_version":neg['version']+(2 if first_safe else 3),"status":"agreed","final_proposal_id":final['proposal_id'],"rounds":1 if first_safe else 2,"referee_action":"continue","reason_vi":"Fixture verdict"},orchestrator)
        card=self.post(f"/api/v1/runs/{r}/proposals/{final['proposal_id']}/present",{"expected_version":final["version"]},orchestrator)
        return card,nid

    def accept_card(self,r,s,card,orchestrator,retry=False):
        seller=None if s=="D" else self.token(r,"simulated_seller",s)
        if card["kind"]=="question":
            question=next(x for x in self.get(f"/api/v1/runs/{r}/shops/{s}/rule-questions",orchestrator) if x["question_id"]==card["question_id"])
            decision=self.post(f"/api/v1/runs/{r}/decisions",{"target_type":"rule_question","target_id":question["question_id"],"target_version":1,"action":"approve","rule_answer":True},seller)
            self.request("PUT",f"/api/v1/runs/{r}/shops/{s}/rules",{"confirmation_decision_id":decision["decision_id"],"expected_rules_version":question["based_on_rules_version"],"rules":self.get(f"/api/v1/runs/{r}/shops/{s}/rules",orchestrator)["rules"]},seller)
            return
        proposal=self.get(f"/api/v1/runs/{r}/proposals/{card['proposal_id']}",orchestrator)
        approval=self.post(f"/api/v1/runs/{r}/decisions",{"target_type":"proposal","target_id":proposal["proposal_id"],"target_version":proposal["version"],"action":"approve"},seller)
        context=self.get(f"/api/v1/runs/{r}/shops/{s}/context",orchestrator)
        job=self.post(f"/api/v1/runs/{r}/shops/{s}/content-jobs",{"proposal_id":proposal["proposal_id"],"product_id":context["product_id"]},orchestrator)
        self.worker(r,job)
        if retry:
            job=self.post(f"/api/v1/runs/{r}/shops/{s}/content-jobs",{"proposal_id":proposal["proposal_id"],"product_id":context["product_id"],"expected_current_attempt":job["attempt"],"feedback_vi":"Ảnh nền tối quá, làm sáng hơn","retry_scope":"images"},orchestrator)
            self.worker(r,job)
        content=next(x for x in self.get(f"/api/v1/runs/{r}/shops/{s}/content",orchestrator) if x["content_id"] in job["output_content_ids"])
        content_approval=self.post(f"/api/v1/runs/{r}/decisions",{"target_type":"content","target_id":content["content_id"],"target_version":content["version"],"action":"approve","cover_option":"B"},seller)
        listing=self.post(f"/api/v1/runs/{r}/content/{content['content_id']}/publish",{"approval_decision_id":content_approval["decision_id"],"expected_active_content_id":context["active_content_id"]},orchestrator)
        assert listing["active_voucher_pct"]==proposal["package"]["voucher_pct"]

    def external_day(self,r,day,learn=True,policy="good"):
        o=self.token(r,"orchestrator")
        run=self.get(f"/api/v1/runs/{r}",o)
        op=self.post(f"/api/v1/runs/{r}/days/start",{"expected_day":day,"expected_version":run["version"]},o)
        assert op["status"]=="queued"
        assert self.get(f"/api/v1/runs/{r}/operations?status=queued",o)
        claim=self.post(f"/internal/v1/runs/{r}/operations/{op['operation_id']}/claim",{"expected_version":op["version"]},o)
        catalog=self.get(f"/api/v1/runs/{r}/shops",o)
        d_evidence=None
        for shop in catalog:
            s=shop["shop_id"];context=self.get(f"/api/v1/runs/{r}/shops/{s}/context",o)
            if not context["eligibility"]["eligible"]:continue
            learned=bool(self.memory.get(r,{}).get("lessons"))
            first_safe=(learned if policy=="good" else not learned)
            card,nid=self.negotiate(r,s,o,first_safe=first_safe)
            if s=="D":d_evidence=nid
            else:self.accept_card(r,s,card,o)
        self.post(f"/internal/v1/runs/{r}/operations/{op['operation_id']}/result",{"expected_version":claim["version"],"status":"succeeded"},o)
        pending=self.get(f"/api/v1/runs/{r}/state",o)["pending_cards"]
        if pending:self.accept_card(r,"D",pending[0],o,retry=day==1)
        current=self.get(f"/api/v1/runs/{r}",o)
        self.post(f"/api/v1/runs/{r}/days/close",{"expected_day":day,"expected_version":current["version"]},o)
        learner=self.token(r,"learning_worker","D")
        inputs=self.get(f"/internal/v1/runs/{r}/learning-input?day={day}",learner)
        if learn:
            mem=self.memory.setdefault(r,{"lessons":[],"cursor":0})
            assert inputs["settlement_cursor"]>mem["cursor"]
            history=inputs["history"]["D"]
            evidence=d_evidence or next(x["negotiation_id"] for x in history)
            if day==1:
                self.post(f"/internal/v1/runs/{r}/shops/D/rule-questions",{"external_pref_id":"fixture-bright","field":"content_style","value":"ảnh nền sáng","text_vi":"Lần sau tạo ảnh nền sáng?","based_on_rules_version":self.get(f"/api/v1/runs/{r}/shops/D/rules",o)["rules_version"]},learner)
            summary={"day":day,"history_updates":["Fixture memory owner đã đọc applied history"],"pref_candidates":["ảnh nền sáng"] if day==1 else [],"calibration":{"factor":1.0,"points":day,"mape_today":None},"lesson_ops":[{"op":"ADD","lesson_id":f"fixture-{day}","text_vi":"Mở đầu từ gói đã được chấp nhận","scope":"strategy","evidence":[evidence]}],"rejected_ops":0,"memory_md_path":""}
            raw_report=self.upload(r,learner,b"# Internal fixture report\n",kind="document",product=None,purpose="learning_report")
            result=self.post(f"/internal/v1/runs/{r}/learning-results",{"day":day,"settlement_cursor":inputs["settlement_cursor"],"expected_version":inputs["version"],"status":"completed","night_summary":summary,"receipt_id":f"fixture:{r}:{inputs['settlement_cursor']}","memory_report_asset_id":raw_report,"lesson_scores":{f"fixture-{day}":2}},learner)
            mem["cursor"]=inputs["settlement_cursor"];mem["lessons"]=["Mở đầu từ gói đã được chấp nhận"]
        night=self.get(f"/api/v1/runs/{r}/shops/D/night-summary?day={day}",o)
        if learn:
            assert night["learning_status"]=="completed" and night["summary"]["memory_md_path"]
            self.get(night["summary"]["memory_md_path"],o)
        else:assert night["learning_status"]=="skipped"
        current=self.get(f"/api/v1/runs/{r}",o)
        self.post(f"/api/v1/runs/{r}/days/advance",{"expected_day":day,"expected_version":current["version"]},o)
        final=self.get(f"/api/v1/runs/{r}",o)
        assert final["current_day"]==min(day+1,7)
        return final

    def comparison(self,days=7,policy="good"):
        self.get("/api/state")
        created=self.post("/api/v1/comparisons",{"execution_profile":"external","content_mode":"worker","learning_mode":"external","simulation_days":days,"data_source":"fixture","driver_config":{"prompt_version":"fixture-"+policy}})
        for day in range(1,days+1):
            self.external_day(created["run_on"],day,True,policy)
            self.external_day(created["run_off"],day,False,policy)
        status=self.get(f"/api/v1/comparisons/{created['comparison_id']}")
        assert status["status"]=="ready"
        report=self.get(f"/api/v1/runs/{created['run_on']}/proof?group_id={created['comparison_id']}")
        assert report["days"]==days and len(report["metrics"])==5
        self.get(f"/api/v1/runs/{created['run_on']}/events/export")
        return {"gate":"A","source":"HTTP fake agents/workers; no paid providers","gate_b":"PENDING","comparison":created,"proof":report,"http_calls":len(self.calls)}
