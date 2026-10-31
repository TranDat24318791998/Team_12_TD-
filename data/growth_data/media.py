"""Local object storage, approval-gated drafts and authorized keyword knowledge."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import unicodedata

from . import models as M
from .errors import Fault, require
from .seed import ATTRIBUTES
from .simulation import business_date
from .storage import dumps, fingerprint, insert, many, now, one, timestamps, uid


class MediaMixin:
    def object_path(self,key):
        path=(self.objects/key).resolve()
        require(path.is_relative_to(self.objects.resolve()),"PATH_INVALID","Đường dẫn không hợp lệ",422)
        return path

    def upload_create(self,c,p,r,body):
        b=M.UploadCreate.model_validate(body)
        self.scope(c,p,r,roles={"seller","content_worker","learning_worker","orchestrator"})
        s=None
        if b.product_id:
            prod=self.entity(c,"products",r,"product_id",b.product_id);s=prod["shop_id"]
            self.scope(c,p,r,s)
        require(b.product_id is not None or (b.kind=="document" and p.role=="learning_worker"),"PRODUCT_REQUIRED","Cần sản phẩm cho media",422)
        if p.role=="learning_worker": require(b.kind=="document" and b.product_id is None,"FORBIDDEN","Chỉ được gửi báo cáo học",403)
        require((b.kind=="image" and b.mime_type.startswith("image/")) or (b.kind=="video" and b.mime_type=="video/mp4") or (b.kind=="document" and b.mime_type in {"text/markdown","application/pdf"}),"MIME_INVALID","Loại file không khớp",422)
        require(b.size_bytes<=(50 if b.kind=="video" else 10)*1024*1024,"FILE_TOO_LARGE","File vượt giới hạn",422)
        aid=uid("asset")
        insert(c,"assets",run_id=r,asset_id=aid,shop_id=s,product_id=b.product_id,kind=b.kind,object_key=f"uploads/{r}/{aid}",mime_type=b.mime_type,size_bytes=b.size_bytes,sha256=b.sha256,width=None,height=None,duration_seconds=None,origin="generated",source_reference="local_upload",visibility="shop_private" if s else "internal",upload_status="pending",upload_owner=p.principal_id,created_at=now())
        return {"asset_id":aid,"upload":{"method":"PUT","url":f"/api/v1/runs/{r}/assets/{aid}/bytes","headers":{"Content-Type":b.mime_type},"expires_at":self.expires(300)}}

    def expires(self,seconds):
        from datetime import timedelta
        return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()

    def asset_access(self,c,p,r,aid,write=False):
        asset=self.entity(c,"assets",r,"asset_id",aid)
        self.scope(c,p,r,asset["shop_id"])
        if asset["visibility"]=="internal": require(p.role in {"learning_worker","evaluator","orchestrator","data_admin"},"NOT_FOUND","Không tìm thấy file",404)
        if p.role=="platform_agent": require(asset["visibility"]=="published","NOT_FOUND","Không tìm thấy file",404)
        if write:
            require(asset["upload_owner"]==p.principal_id and asset["upload_status"]=="pending","FORBIDDEN","Không được ghi file này",403)
            require((datetime.now(timezone.utc)-datetime.fromisoformat(asset["created_at"])).total_seconds()<=300,"UPLOAD_EXPIRED","Phiên upload đã hết hạn")
        return asset

    def upload_bytes(self,p,r,aid,content):
        with self.store.connect() as c: a=self.asset_access(c,p,r,aid,True)
        require(len(content)==a["size_bytes"] and hashlib.sha256(content).hexdigest()==a["sha256"],"CHECKSUM_INVALID","Kích thước hoặc checksum sai",422)
        mime=a["mime_type"]
        valid=(mime=="image/png" and content.startswith(b"\x89PNG\r\n\x1a\n")) or (mime=="image/jpeg" and content.startswith(b"\xff\xd8\xff")) or (mime=="image/webp" and content[:4]==b"RIFF" and content[8:12]==b"WEBP") or (mime=="video/mp4" and content[4:8]==b"ftyp") or (mime=="application/pdf" and content.startswith(b"%PDF-"))
        if mime=="text/markdown":
            try: content.decode("utf-8");valid=b"\x00" not in content
            except UnicodeDecodeError: valid=False
        require(valid,"MIME_INVALID","Nội dung file không khớp loại đã khai",422)
        path=self.object_path(a["object_key"]);path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix(".pending");temp.write_bytes(content);temp.replace(path)
        return {"asset_id":aid,"stored":True}

    def complete_upload(self,c,p,r,aid,checksum):
        a=self.asset_access(c,p,r,aid)
        require(a["upload_owner"]==p.principal_id,"FORBIDDEN","Không phải chủ upload",403)
        path=self.object_path(a["object_key"])
        require(path.is_file() and path.stat().st_size==a["size_bytes"] and hashlib.sha256(path.read_bytes()).hexdigest()==checksum==a["sha256"],"CHECKSUM_INVALID","File chưa đầy đủ hoặc checksum sai",422)
        c.execute("UPDATE assets SET upload_status='ready' WHERE run_id=? AND asset_id=?",(r,aid))
        return {"asset_id":aid,"upload_status":"ready"}

    def content_create(self,c,p,r,s,body,force_local=False):
        run=self.scope(c,p,r,s,{"orchestrator","seller"})
        b=M.ContentCreate.model_validate(body)
        prop=self.entity(c,"proposals",r,"proposal_id",b.proposal_id)
        require(prop["shop_id"]==s and prop["product_id"]==b.product_id and prop["status"]=="applied" and prop["package"]["content_refresh"],"APPROVAL_REQUIRED","Cần gói làm nội dung đã duyệt")
        prior=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND proposal_id=? ORDER BY attempt DESC LIMIT 1",(r,b.proposal_id))
        attempt=prior["attempt"]+1 if prior else 1
        require(attempt<=3,"MAX_VERSIONS","Tối đa ba bản nội dung")
        if prior: require(b.expected_current_attempt==prior["attempt"])
        worker=self.content_mode=="worker" and not force_local
        for aid in b.input_asset_ids:
            a=self.asset_access(c,p,r,aid)
            require(a["product_id"]==b.product_id and a["upload_status"]=="ready","ASSET_INVALID","Ảnh nguồn không hợp lệ",422)
        prod=self.product(c,r,s)
        source=self.entity(c,"content_versions",r,"content_id",prod["active_content_id"])
        asset=source["cover_asset_id"]
        notes=self.rules(c,r,s)[0]["content_style_notes"]
        feedback=(prior["feedback_history"] if prior else [])+([b.feedback_vi] if b.feedback_vi else [])
        version=c.execute("SELECT MAX(content_version)+1 FROM content_versions WHERE run_id=? AND product_id=?",(r,b.product_id)).fetchone()[0]
        cid,jid=uid("content"),uid("job")
        covers=[{"option":opt,"status":"cached","asset_id":asset,"path":f"/api/v1/runs/{r}/assets/{asset}/download","prompt":"Local fallback: dùng ảnh nguồn, không tạo ảnh mới"} for opt in "ABC"]
        video={"status":"failed","asset_id":None,"path":None,"job_id":None,"prompt":"","error":"Offline: chưa nối video provider"}
        title="Quạt mini cầm tay sạc USB, 3 tốc độ gió, pin 2000mAh, 3 màu"
        insert(c,"content_versions",run_id=r,content_id=cid,product_id=b.product_id,content_version=version,parent_content_id=source["content_id"],title=title,description="Quạt mini cầm tay\n"+"\n".join("• "+v for v in ATTRIBUTES),cover_options_json=covers,video_job_json=video,feedback_history_json=feedback,style_notes_json=notes+feedback,cover_asset_id=asset,video_asset_id=None,quality_gain=.25,published_day=None,validation_json=["Không thêm thông số","Ảnh placeholder/fallback; không gọi model"],status="validated",**timestamps())
        if prior:
            c.execute("UPDATE content_versions SET status='superseded' WHERE run_id=? AND content_id IN (SELECT value FROM json_each(?)) AND status IN ('draft','validated')",(r,dumps(prior["output_content_ids"])))
            c.execute("UPDATE content_jobs SET status='failed',error_code='SUPERSEDED',lease_until=NULL,version=version+1 WHERE run_id=? AND job_id=? AND status IN ('queued','running')",(r,prior["job_id"]))
        if worker:c.execute("UPDATE content_versions SET status='draft' WHERE run_id=? AND content_id=?",(r,cid))
        insert(c,"content_jobs",run_id=r,job_id=jid,shop_id=s,product_id=b.product_id,proposal_id=b.proposal_id,attempt=attempt,brief_json={"attributes":ATTRIBUTES},feedback_history_json=feedback,style_notes_json=notes+feedback,input_asset_ids_json=b.input_asset_ids,provider="assigned_worker" if worker else "local_fallback",provider_job_id=None,cache_key=fingerprint({"r":r,"s":s,"attempt":attempt,"feedback":feedback}),status="queued" if worker else "succeeded",output_content_ids_json=[cid],fallback_used=not worker,error_code=None,lease_until=self.expires(120) if worker else None,**timestamps())
        self.event(c,r,run["current_day"],"content_job","content_worker",s,{"job_id":jid,"attempt":attempt,"feedback_vi":b.feedback_vi,"fallback_used":True},visibility="shop_private",text="Nội dung chữ sẵn sàng; ảnh nguồn và video fallback")
        if s=="D": c.execute("UPDATE runs SET phase='content_review' WHERE run_id=?",(r,))
        return self.entity(c,"content_jobs",r,"job_id",jid)

    def publish(self,c,p,r,cid,body):
        content=self.entity(c,"content_versions",r,"content_id",cid)
        prod=self.entity(c,"products",r,"product_id",content["product_id"])
        run=self.scope(c,p,r,prod["shop_id"],{"orchestrator"})
        b=M.Publish.model_validate(body)
        decision=self.entity(c,"decisions",r,"decision_id",b.approval_decision_id)
        require(decision["target_type"]=="content" and decision["target_id"]==cid and decision["action"]=="approve","APPROVAL_REQUIRED","Cần duyệt đúng nội dung")
        if prod["active_content_id"]==cid: return self.public(c,r,prod["shop_id"])
        require(decision["target_version"]==content["version"])
        require(prod["active_content_id"]==b.expected_active_content_id and content["status"] in {"validated","superseded"})
        option=next((x for x in content["cover_options"] if x["option"]==decision["cover_option"]),None)
        require(option and option["status"] in {"done","cached"},"ASSET_PENDING","Ảnh chưa sẵn sàng")
        asset=self.entity(c,"assets",r,"asset_id",option["asset_id"])
        require(asset["product_id"]==prod["product_id"] and asset["upload_status"]=="ready")
        c.execute("UPDATE content_versions SET status='superseded',version=version+1 WHERE run_id=? AND content_id=?",(r,prod["active_content_id"]))
        c.execute("UPDATE content_versions SET status='published',cover_asset_id=?,published_day=?,version=version+1 WHERE run_id=? AND content_id=?",(asset["asset_id"],run["current_day"],r,cid))
        c.execute("UPDATE products SET active_content_id=?,version=version+1 WHERE run_id=? AND product_id=?",(cid,r,prod["product_id"]))
        c.execute("UPDATE assets SET visibility='published' WHERE run_id=? AND asset_id=?",(r,asset["asset_id"]))
        self.event(c,r,run["current_day"],"content_applied","orchestrator",prod["shop_id"],{"content_id":cid,"cover_option":decision["cover_option"]},text="Xuất bản đúng nội dung người bán đã chọn")
        if prod["shop_id"]=="D": c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
        return self.public(c,r,prod["shop_id"])

    def content_result(self,c,p,r,jid,body):
        job=self.entity(c,"content_jobs",r,"job_id",jid)
        self.scope(c,p,r,job["shop_id"],{"content_worker"})
        require("*" in p.allowed_job_ids or jid in p.allowed_job_ids,"NOT_FOUND","Job không được giao cho worker",404)
        b=M.ContentResult.model_validate(body)
        require(job["version"]==b.expected_job_version)
        require(job["status"] in {"queued","running"},"JOB_TERMINAL","Job đã có kết quả cuối")
        if b.content_candidates:
            require(b.status=="succeeded")
            candidate=b.content_candidates
            allowed={"content_id","content_version","title","description","images","video","feedback_history","style_notes","checks"}
            require(set(candidate)<=allowed and {"title","description","images","video"}<=set(candidate),"CONTENT_SCHEMA","Bản nháp sai schema",422)
            text=candidate["title"]+" "+candidate["description"]
            require(len(candidate["title"])<=120 and len(candidate["description"])<=5000 and set(re.findall(r"\d+",text))<= {"3","2000"},"CLAIM_INVALID","Thông số ngoài listing",422)
            require(not any(term in text.casefold() for term in ("bảo hành","chống nước","không ồn","5000mah")),"CLAIM_INVALID","Chưa xác minh tuyên bố này",422)
            # This local MVP uses a constrained vocabulary rather than pretending
            # a number-only check can verify arbitrary generated factual prose.
            vocabulary=set(re.findall(r"\w+",("Quạt mini cầm tay sạc USB "+" ".join(ATTRIBUTES)+" với và có sản phẩm tính năng chi tiết").casefold()))
            require(set(re.findall(r"\w+",text.casefold()))<=vocabulary,"CLAIM_INVALID","Chữ ngoài bộ thuộc tính đã kiểm chứng",422)
            for value in re.findall(r"pin\s+(\d+)\s*mah",text.casefold()):require(value=="2000","CLAIM_INVALID","Sai dung lượng pin",422)
            require(len(candidate["images"])==3 and {v["option"] for v in candidate["images"]}==set("ABC"),"CONTENT_SCHEMA","Cần đúng ba phương án",422)
            for image in candidate["images"]:
                a=self.entity(c,"assets",r,"asset_id",image["asset_id"])
                require(a["product_id"]==job["product_id"] and a["upload_status"]=="ready")
                require(image.get("status") in {"done","cached"},"ASSET_PENDING","Ảnh kết quả chưa sẵn sàng",422)
                require(set(image)<={"option","status","asset_id","path","prompt"},"CONTENT_SCHEMA","Ảnh sai schema",422)
                image["path"]=f"/api/v1/runs/{r}/assets/{a['asset_id']}/download"
            require(not one(c,"SELECT * FROM content_jobs WHERE run_id=? AND proposal_id=? AND attempt>?",(r,job["proposal_id"],job["attempt"])),"SUPERSEDED_JOB","Job đã bị thay thế")
            video=candidate["video"]
            require(isinstance(video,dict) and video.get("status") in {"pending","running","done","failed","cached"},"CONTENT_SCHEMA","Video sai schema",422)
            require(set(video)<={"status","asset_id","path","job_id","prompt","error"},"CONTENT_SCHEMA","Video có trường không hợp lệ",422)
            video_id=video.get("asset_id")
            if video_id:
                a=self.entity(c,"assets",r,"asset_id",video_id);require(a["product_id"]==job["product_id"] and a["kind"]=="video" and a["upload_status"]=="ready")
                video["path"]=f"/api/v1/runs/{r}/assets/{a['asset_id']}/download"
            else:video["path"]=None
            content=self.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
            require(content["status"]=="draft")
            c.execute("UPDATE content_versions SET title=?,description=?,cover_options_json=?,video_job_json=?,video_asset_id=?,validation_json=?,status='validated',version=version+1,updated_at=? WHERE run_id=? AND content_id=?",(candidate["title"],candidate["description"],dumps(candidate["images"]),dumps(video),video_id,dumps(candidate.get("checks",["Kiểm tra thông số bằng code"])),now(),r,content["content_id"]))
        elif b.status=="succeeded":
            raise Fault("CONTENT_REQUIRED","Job thành công cần bản nháp hợp lệ",422)
        elif b.status in {"failed","timed_out"}:
            # Keep the explicitly labeled source fallback; seller must still approve it.
            c.execute("UPDATE content_versions SET status='validated',version=version+1 WHERE run_id=? AND content_id=?",(r,job["output_content_ids"][0]))
        c.execute("UPDATE content_jobs SET status=?,provider_job_id=COALESCE(?,provider_job_id),fallback_used=?,error_code=?,lease_until=?,version=version+1,updated_at=? WHERE run_id=? AND job_id=?",(b.status,b.provider_job_id,b.fallback_used or b.status in {"failed","timed_out"},b.error_code,self.expires(120) if b.status=="running" else None,now(),r,jid))
        return self.entity(c,"content_jobs",r,"job_id",jid)

    def knowledge_search(self,c,p,r,body):
        run=self.scope(c,p,r,roles={"platform_agent","shop_agent","seller","content_worker","orchestrator","learning_worker"})
        b=M.KnowledgeSearch.model_validate(body)
        if b.product_id:
            prod=self.entity(c,"products",r,"product_id",b.product_id);self.scope(c,p,r,prod["shop_id"])
        def normalize(text):
            return "".join(ch for ch in unicodedata.normalize("NFD",text.casefold()) if not unicodedata.combining(ch))
        terms=set(normalize(b.query).split())
        out=[]
        for doc in many(c,"SELECT * FROM knowledge_documents WHERE index_status='ready' AND knowledge_release='knowledge-v1' ORDER BY document_id"):
            if doc["effective_from"]>business_date(run["current_day"]): continue
            if doc["effective_to"] and doc["effective_to"]<business_date(run["current_day"]):continue
            if doc["collection_scope"]=="shop_private":
                if p.role=="platform_agent" or doc["owner_run_id"]!=r or (doc["owner_shop_id"] not in p.allowed_shop_ids and "*" not in p.allowed_shop_ids):continue
            if b.document_types and doc["type"] not in b.document_types:continue
            if b.product_id and doc["document_id"].startswith("product_") and doc["document_id"]!=f"product_{b.product_id}":continue
            path=self.object_path(doc["source_object_key"])
            if not path.is_file():continue
            text=path.read_text(encoding="utf-8")
            score=len(terms&set(normalize(text).split()))
            if score:out.append({"document_id":doc["document_id"],"document_version":doc["document_version"],"title":doc["title"],"score":score,"excerpt":text[:1800],"source_reference":doc["document_id"],"backend":"local_keyword","is_simulated":True})
        return sorted(out,key=lambda v:(-v["score"],v["document_id"]))[:b.top_k]
