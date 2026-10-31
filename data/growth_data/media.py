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
from .text_validation import content_matches_facts


class MediaMixin:
    @staticmethod
    def duration_matches(requested, actual):
        if requested is None or actual is None:return None
        return abs(actual-requested)<=max(.5,requested*.05)

    def wizard_input_asset(self,c,r,job):
        """Choose a verified active cover, or the supplied original if unavailable."""
        product=self.product(c,r,job['shop_id'])
        content=self.entity(c,'content_versions',r,'content_id',product['active_content_id'])
        candidates=[]
        if content['status']=='published' and content.get('cover_asset_id'):
            candidates.append(content['cover_asset_id'])
        candidates.extend(row['asset_id'] for row in many(c,"SELECT asset_id FROM assets WHERE run_id=? AND product_id=? AND kind='image' AND origin='supplied' AND source_reference LIKE 'local_import:sha256:%' AND upload_status='ready' ORDER BY created_at",(r,job['product_id'])))
        for aid in dict.fromkeys(candidates):
            asset=one(c,"SELECT * FROM assets WHERE run_id=? AND asset_id=? AND product_id=? AND kind='image' AND upload_status='ready'",(r,aid,job['product_id']))
            if not asset:continue
            if asset.get('source_reference') in {'generated_geometric_placeholder_not_product_photo','geometric_fallback_not_product_photo'}:continue
            try:
                path=self.object_path(asset['object_key'])
                if path.is_file() and path.stat().st_size==asset['size_bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==asset['sha256']:
                    return asset
            except (Fault,OSError):pass
        return None

    def content_approval(self,c,r,job):
        """Resolve the card named by the exact approval event for this job's proposal."""
        prop=one(c,"SELECT * FROM proposals WHERE run_id=? AND proposal_id=?",(r,job['proposal_id']))
        if not prop or prop['shop_id']!=job['shop_id'] or prop['product_id']!=job['product_id']:
            return None,None
        approvals=many(c,"SELECT * FROM decisions WHERE run_id=? AND shop_id=? AND target_type='proposal' AND target_id=? AND action='approve'",(r,job['shop_id'],prop['proposal_id']))
        if len(approvals)!=1:return None,None
        approval=approvals[0]
        events=many(c,"SELECT * FROM events WHERE run_id=? AND shop_id=? AND type='seller_decision' AND json_extract(payload_json,'$.decision_id')=?",(r,job['shop_id'],approval['decision_id']))
        if len(events)!=1:return None,None
        payload=events[0]['payload']
        if (payload.get('target_type')!='proposal' or payload.get('target_id')!=prop['proposal_id']
                or payload.get('negotiation_id')!=prop['negotiation_id'] or events[0]['actor_role']!=approval['actor_type']
                or payload.get('action')!=('edit' if approval['edited_package'] is not None else 'accept')):
            return None,None
        card=one(c,"SELECT * FROM cards WHERE run_id=? AND shop_id=? AND card_id=? AND status='resolved' AND kind='offer'",(r,job['shop_id'],payload.get('card_id')))
        negotiation=one(c,"SELECT * FROM negotiations WHERE run_id=? AND shop_id=? AND negotiation_id=?",(r,job['shop_id'],prop['negotiation_id']))
        if not card or not negotiation or card['day']!=negotiation['day'] or events[0]['day']!=negotiation['day']:
            return None,None
        if card['proposal_id']!=prop['proposal_id']:
            parent=one(c,"SELECT * FROM proposals WHERE run_id=? AND proposal_id=?",(r,prop['parent_proposal_id']))
            if not (parent and parent['proposal_id']==card['proposal_id'] and parent['shop_id']==prop['shop_id']
                    and parent['product_id']==prop['product_id'] and parent['negotiation_id']==prop['negotiation_id']
                    and approval['edited_package']==prop['package'] and prop['author_role']==approval['actor_type']):
                return None,None
        elif approval['edited_package'] is not None:
            return None,None
        return card,approval

    def object_path(self,key):
        path=(self.objects/key).resolve()
        require(path.is_relative_to(self.objects.resolve()),"PATH_INVALID","Đường dẫn không hợp lệ",422)
        return path

    def upload_create(self,c,p,r,body):
        b=M.UploadCreate.model_validate(body)
        self.scope(c,p,r,roles={"seller","content_worker","learning_worker","orchestrator","knowledge_admin"})
        s=None
        if b.product_id:
            prod=self.entity(c,"products",r,"product_id",b.product_id);s=prod["shop_id"]
            self.scope(c,p,r,s)
        replay=p.role=="orchestrator" and b.purpose=="replay_recording" and b.kind=="document" and b.product_id is None
        require(b.product_id is not None or (b.kind=="document" and p.role in {"learning_worker","knowledge_admin"}) or replay,"PRODUCT_REQUIRED","Cần sản phẩm cho media",422)
        if p.role=="learning_worker": require(b.kind=="document" and b.product_id is None,"FORBIDDEN","Chỉ được gửi báo cáo học",403)
        if p.role=="knowledge_admin":require(b.kind=="document" and b.product_id is None,"FORBIDDEN","Chỉ gửi nguồn knowledge",403)
        if p.role=="content_worker":
            require(b.job_id,"JOB_REQUIRED","Media worker phải gắn job",422)
        if b.job_id:
            job=self.job_access(c,p,r,b.job_id)
            require(job["product_id"]==b.product_id and job["status"] in {"queued","running"},"JOB_TERMINAL","Job/sản phẩm không còn nhận media")
        purpose="replay_recording" if replay else "learning_report" if p.role=="learning_worker" else "knowledge_source" if p.role=="knowledge_admin" else "product_media"
        require(b.purpose in {purpose,"product_media"},"FORBIDDEN","Sai mục đích upload",403)
        require((b.kind=="image" and b.mime_type.startswith("image/")) or (b.kind=="video" and b.mime_type=="video/mp4") or (b.kind=="document" and b.mime_type in {"text/markdown","application/pdf"}),"MIME_INVALID","Loại file không khớp",422)
        require(b.size_bytes<=(50 if b.kind=="video" else 10)*1024*1024,"FILE_TOO_LARGE","File vượt giới hạn",422)
        aid=uid("asset")
        insert(c,"assets",run_id=r,asset_id=aid,shop_id=s,product_id=b.product_id,kind=b.kind,object_key=f"uploads/{r}/{aid}",mime_type=b.mime_type,size_bytes=b.size_bytes,sha256=b.sha256,width=None,height=None,duration_seconds=None,origin="generated",source_reference="worker_upload",visibility="shop_private" if s else "internal",upload_status="pending",upload_owner=p.principal_id,job_id=b.job_id,purpose=purpose,created_at=now())
        if b.job_id:insert(c,"asset_jobs",run_id=r,asset_id=aid,job_id=b.job_id)
        return {"asset_id":aid,"upload":{"method":"PUT","url":f"/api/v1/runs/{r}/assets/{aid}/bytes","headers":{"Content-Type":b.mime_type},"expires_at":self.expires(300)}}

    def expires(self,seconds):
        from datetime import timedelta
        return (datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat()

    def asset_access(self,c,p,r,aid,write=False):
        asset=self.entity(c,"assets",r,"asset_id",aid)
        self.scope(c,p,r,asset["shop_id"])
        if asset["visibility"]=="internal": require(p.role in ({"knowledge_admin","data_admin"} if asset["purpose"]=="knowledge_source" else {"orchestrator","evaluator","data_admin"} if asset["purpose"]=="replay_recording" else {"learning_worker","evaluator","orchestrator","data_admin"}),"NOT_FOUND","Không tìm thấy file",404)
        if asset["purpose"]=="seller_report":require(p.role in {"seller","shop_agent","orchestrator","evaluator","data_admin","learning_worker"},"NOT_FOUND","Không tìm thấy file",404)
        if p.role=="content_worker":
            links=many(c,"SELECT job_id FROM asset_jobs WHERE run_id=? AND asset_id=?",(r,aid))
            require(any("*" in p.allowed_job_ids or x["job_id"] in p.allowed_job_ids for x in links),"NOT_FOUND","Asset không thuộc job được giao",404)
        elif p.role not in {"shop_agent","seller","simulated_seller","orchestrator","simulator","learning_worker","evaluator","data_admin","knowledge_admin"}:
            require(asset["visibility"]=="published","NOT_FOUND","Không tìm thấy file",404)
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
        if a["upload_status"]!="ready":self.asset_access(c,p,r,aid,True)
        path=self.object_path(a["object_key"])
        require(path.is_file() and path.stat().st_size==a["size_bytes"] and hashlib.sha256(path.read_bytes()).hexdigest()==checksum==a["sha256"],"CHECKSUM_INVALID","File chưa đầy đủ hoặc checksum sai",422)
        c.execute("UPDATE assets SET upload_status='ready' WHERE run_id=? AND asset_id=?",(r,aid))
        return {"asset_id":aid,"upload_status":"ready"}

    def content_create(self,c,p,r,s,body,force_local=False):
        run=self.scope(c,p,r,s,{"orchestrator","seller"})
        b=M.ContentCreate.model_validate(body)
        prop=self.entity(c,"proposals",r,"proposal_id",b.proposal_id)
        require(prop["shop_id"]==s and prop["product_id"]==b.product_id and (prop["status"]=="accepted" or (prop["status"]=="applied" and run["created_by"] is None)) and prop["package"]["content_refresh"],"APPROVAL_REQUIRED","Cần gói làm nội dung đã duyệt, chưa kích hoạt")
        prior=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND proposal_id=? ORDER BY attempt DESC LIMIT 1",(r,b.proposal_id))
        attempt=prior["attempt"]+1 if prior else 1
        require(attempt<=3,"MAX_VERSIONS","Tối đa ba bản nội dung")
        if prior: require(b.expected_current_attempt==prior["attempt"])
        if prior:
            require(not any(slot.get('status') in {'reserved','unknown','outcome_unknown','running'} for slot in prior['provider_state'].values()), 'PROVIDER_OUTCOME_UNKNOWN', 'Cần xử lý kết quả media chưa rõ trước khi làm lại')
        worker=run["content_mode"]=="worker" and not force_local
        staged=(worker and s==run['demo_shop_id'] and run['config'].get('driver',{}).get('agent_version')=='native'
                and run['config'].get('driver',{}).get('media_wizard')=='staged')
        if staged and prior:require(b.retry_scope=='all','RETRY_SCOPE','Tạo lại nội dung cần chọn lại ảnh và video',422)
        for aid in b.input_asset_ids:
            a=self.asset_access(c,p,r,aid)
            require(a["product_id"]==b.product_id and a["upload_status"]=="ready","ASSET_INVALID","Ảnh nguồn không hợp lệ",422)
        prod=self.product(c,r,s)
        source=self.entity(c,"content_versions",r,"content_id",prior["output_content_ids"][0] if prior else prod["active_content_id"])
        asset=source["cover_asset_id"]
        notes=self.rules(c,r,s)[0]["content_style_notes"]
        feedback=(prior["feedback_history"] if prior else [])+([b.feedback_vi] if b.feedback_vi else [])
        version=c.execute("SELECT MAX(content_version)+1 FROM content_versions WHERE run_id=? AND product_id=?",(r,b.product_id)).fetchone()[0]
        cid,jid=uid("content"),uid("job")
        covers=[]
        from .seed import placeholder_png
        for index,opt in enumerate("ABC",1):
            aid=uid("asset");raw=placeholder_png(index+attempt);key=f"fallback/{r}/{aid}.png"
            path=self.object_path(key);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            insert(c,"assets",run_id=r,asset_id=aid,shop_id=s,product_id=b.product_id,kind="image",object_key=key,mime_type="image/png",size_bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),width=64,height=64,duration_seconds=None,origin="generated",source_reference="geometric_fallback_not_product_photo",visibility="shop_private",upload_status="ready",upload_owner="local_fallback",purpose="product_media",job_id=None,created_at=now())
            covers.append({"option":opt,"status":"cached","asset_id":aid,"path":f"/api/v1/runs/{r}/assets/{aid}/download","prompt":"Ảnh hình học fallback, không phải ảnh sản phẩm do model tạo"})
        video=source["video_job"] if prior and b.retry_scope in {"images","text"} else {"status":"failed","asset_id":None,"path":None,"job_id":None,"prompt":"","error":"Offline: chưa nối video provider"}
        if prior and b.retry_scope=="text":covers=source["cover_options"]
        title=source['title']
        description=source['description']
        insert(c,"content_versions",run_id=r,content_id=cid,product_id=b.product_id,content_version=version,parent_content_id=source["content_id"],title=title,description=description,cover_options_json=covers,video_job_json=video,feedback_history_json=feedback,style_notes_json=notes+feedback,cover_asset_id=asset,video_asset_id=video.get("asset_id"),quality_gain=.25,published_day=None,validation_json=["Không thêm thông số","Ảnh placeholder/fallback; không gọi model"],status="validated",**timestamps())
        if prior:
            c.execute("UPDATE content_versions SET status='superseded' WHERE run_id=? AND content_id IN (SELECT value FROM json_each(?)) AND status IN ('draft','validated')",(r,dumps(prior["output_content_ids"])))
            c.execute("UPDATE content_jobs SET status='failed',error_code='SUPERSEDED',lease_until=NULL,version=version+1 WHERE run_id=? AND job_id=? AND status IN ('queued','running')",(r,prior["job_id"]))
        if worker:c.execute("UPDATE content_versions SET status='draft' WHERE run_id=? AND content_id=?",(r,cid))
        original=one(c,"SELECT asset_id FROM assets WHERE run_id=? AND product_id=? AND origin='supplied' AND source_reference LIKE 'local_import:sha256:%' ORDER BY created_at LIMIT 1",(r,b.product_id))
        source_assets=list(dict.fromkeys(b.input_asset_ids+([original['asset_id']] if original else [])+[asset]+[v["asset_id"] for v in source["cover_options"] if v.get('asset_id')]+([source["video_asset_id"]] if source["video_asset_id"] else [])))
        brief={"facts":prod["facts"],"attributes":[v['text_vi'] for v in prod['facts']['verified_claims']],"confirmed_style":notes,"previous_content":{"title":source["title"],"description":source["description"],"images":source["cover_options"],"video":source["video_job"]},"retry_scope":b.retry_scope if prior else "all"}
        if staged:brief['wizard']={'stage':'choose_image','background':None,'wishes':'','output_type':None,'duration':None}
        insert(c,"content_jobs",run_id=r,job_id=jid,shop_id=s,product_id=b.product_id,proposal_id=b.proposal_id,attempt=attempt,brief_json=brief,feedback_history_json=feedback,style_notes_json=notes+feedback,input_asset_ids_json=source_assets,provider="assigned_worker" if worker else "local_fallback",provider_job_id=None,cache_key=fingerprint({"r":r,"s":s,"attempt":attempt,"feedback":feedback}),status="awaiting_image" if staged else "queued" if worker else "succeeded",output_content_ids_json=[cid],fallback_used=not worker,error_code=None,lease_until=self.expires(120) if worker and not staged else None,retry_scope=b.retry_scope if prior else "all",source_content_id=source["content_id"],**timestamps())
        for aid in set(source_assets+[x["asset_id"] for x in covers]):
            c.execute("INSERT OR IGNORE INTO asset_jobs VALUES(?,?,?)",(r,aid,jid))
        self.event(c,r,run["current_day"],"content_job","content_worker",s,{"job_id":jid,"attempt":attempt,"feedback_vi":b.feedback_vi,"fallback_used":not worker,"kind":"draft","status":"awaiting_image" if staged else "running" if worker else "cached","version":attempt},visibility="shop_private",text="Chờ người bán chọn nền ảnh" if staged else "Đã giao content worker" if worker else "Nội dung local và ảnh fallback có nhãn")
        if s==run['demo_shop_id']: c.execute("UPDATE runs SET phase='content_review' WHERE run_id=?",(r,))
        return self.entity(c,"content_jobs",r,"job_id",jid)

    def staged_text(self,job,content):
        text=job['provider_state'].get('text',{})
        return text if (text.get('status')=='done' and text.get('content_id')==content['content_id']
                        and text.get('content_version')==content['version']) else None

    def prepare_running_skip(self,c,r,job,content,cover_option):
        wizard=job['brief'].get('wizard')
        if wizard:
            require(wizard.get('stage')=='video' and cover_option=='A','CONTENT_PENDING','Nội dung chưa được kiểm tra')
            image=next((item for item in content['cover_options'] if item['option']=='A'),None)
            slot=job['provider_state'].get('A',{})
            require(image and image.get('status')=='done' and image.get('asset_id')==slot.get('asset_id')
                    and slot.get('status')=='done' and slot.get('source')=='live' and slot.get('source_asset_id'),
                    'ASSET_PENDING','Ảnh chưa sẵn sàng')
            asset=self.checked_job_asset(c,r,job,image['asset_id'],'image')
            require(asset['job_id']==job['job_id'],'ASSET_SCOPE','File không thuộc lượt hiện tại',404)
            self.validate_content_text(c,r,job,content['title'],content['description'])
            c.execute("UPDATE content_versions SET status='validated',version=version+1,updated_at=? WHERE run_id=? AND content_id=? AND status='draft'",(now(),r,content['content_id']))
            return
        text=self.staged_text(job,content)
        require(text,'CONTENT_PENDING','Nội dung chưa được kiểm tra')
        self.validate_content_text(c,r,job,text['title'],text['description'])
        entry=job['provider_state'].get(cover_option,{})
        require(entry.get('status')=='done' and entry.get('source')=='live' and entry.get('asset_id'),
                'ASSET_PENDING','Ảnh chưa sẵn sàng')
        asset=self.checked_job_asset(c,r,job,entry['asset_id'],'image')
        require(asset['job_id']==job['job_id'],'ASSET_SCOPE','File không thuộc lượt hiện tại',404)
        images=[{'option':slot,'status':'done' if slot==cover_option else 'pending',
                 'asset_id':asset['asset_id'] if slot==cover_option else None,
                 'path':f"/api/v1/runs/{r}/assets/{asset['asset_id']}/download" if slot==cover_option else None,
                 'source':'live' if slot==cover_option else 'unavailable'} for slot in 'ABC']
        c.execute("UPDATE content_versions SET title=?,description=?,cover_options_json=?,validation_json=?,status='validated',version=version+1,updated_at=? WHERE run_id=? AND content_id=? AND status='draft'",
                  (text['title'],text['description'],dumps(images),dumps(text['checks']),now(),r,content['content_id']))

    def publish(self,c,p,r,cid,body):
        content=self.entity(c,"content_versions",r,"content_id",cid)
        prod=self.entity(c,"products",r,"product_id",content["product_id"])
        run=self.scope(c,p,r,prod["shop_id"],{"orchestrator"})
        b=M.Publish.model_validate(body)
        decision=self.entity(c,"decisions",r,"decision_id",b.approval_decision_id)
        require(decision["target_type"]=="content" and decision["target_id"]==cid and decision["action"]=="approve","APPROVAL_REQUIRED","Cần duyệt đúng nội dung")
        if prod["active_content_id"]==cid: return self.public(c,r,prod["shop_id"])
        require(decision["target_version"]==content["version"])
        require(prod["active_content_id"]==b.expected_active_content_id and content["status"]=="validated")
        job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND product_id=? ORDER BY rowid DESC LIMIT 1",(r,prod["product_id"]))
        early=bool(job and run['config'].get('driver',{}).get('agent_version')=='native'
                   and job['provider']=='assigned_worker' and job['status'] in {'queued','running'} and b.skip_video)
        require(job and cid in job["output_content_ids"] and (job["status"] in {"succeeded","failed","timed_out"} or early),"STALE_DRAFT","Chỉ xuất bản draft mới nhất đã sẵn sàng")
        option=next((x for x in content["cover_options"] if x["option"]==decision["cover_option"]),None)
        require(option and option["status"] in {"done","cached"} and option.get('asset_id'),"ASSET_PENDING","Ảnh chưa sẵn sàng")
        asset=self.checked_job_asset(c,r,job,option['asset_id'],'image')
        if early:
            entry=job['provider_state'].get(decision['cover_option'],{})
            require(option['status']=='done' and entry.get('status')=='done' and entry.get('source')=='live'
                    and entry.get('asset_id')==asset['asset_id'] and asset['job_id']==job['job_id'],
                    'ASSET_SCOPE','Ảnh không thuộc lượt hiện tại',404)
        video=content['video_job']
        video_id=video.get('asset_id')
        if wizard:=job['brief'].get('wizard'):
            slot=job['provider_state'].get('A',{})
            require(wizard.get('stage') in {'image','video'} and decision['cover_option']=='A' and option['status']=='done'
                    and slot.get('status')=='done' and slot.get('source')=='live' and slot.get('source_asset_id')
                    and slot.get('asset_id')==asset['asset_id'] and asset['job_id']==job['job_id'],
                    'IMAGE_REFERENCE_INVALID','Ảnh phải thuộc lượt tạo hiện tại')
            if not b.skip_video:
                require(wizard.get('stage')=='video' and video.get('status')=='done'
                        and video.get('reference_asset_id')==asset['asset_id'],
                        'VIDEO_REQUIRED','Cần ảnh và video đã tạo từ ảnh được chọn')
                require(video.get('duration_matches_requested') is True or b.video_review_ack,
                        'VIDEO_DURATION_ACK_REQUIRED','Cần xác nhận thời lượng video thực tế')
        if not b.skip_video and video.get('status') in {'done','cached'}:
            require(video_id is not None,'ASSET_PENDING','Video chưa sẵn sàng')
            self.checked_job_asset(c,r,job,video_id,'video')
            if run['config'].get('driver',{}).get('agent_version')=='native': require(video.get('review_passed') is True or b.video_review_ack,'VIDEO_REVIEW_REQUIRED','Cần xác nhận video chưa được kiểm duyệt')
        elif not b.skip_video and run['config'].get('driver',{}).get('agent_version')=='native':
            raise Fault('VIDEO_SKIP_REQUIRED','Chọn bỏ video chưa sẵn sàng',409)
        if b.skip_video:
            video={**video,'asset_id':None,'path':None,'status':'skipped'}
            video_id=None
        c.execute("UPDATE content_versions SET status='superseded',version=version+1 WHERE run_id=? AND content_id=?",(r,prod["active_content_id"]))
        c.execute("UPDATE content_versions SET status='published',cover_asset_id=?,video_asset_id=?,video_job_json=?,published_day=?,version=version+1 WHERE run_id=? AND content_id=?",(asset["asset_id"],video_id,dumps(video),run["current_day"],r,cid))
        c.execute("UPDATE products SET active_content_id=?,version=version+1 WHERE run_id=? AND product_id=?",(cid,r,prod["product_id"]))
        c.execute("UPDATE assets SET visibility='published' WHERE run_id=? AND asset_id=?",(r,asset["asset_id"]))
        if video_id:c.execute("UPDATE assets SET visibility='published' WHERE run_id=? AND asset_id=?",(r,video_id))
        self.event(c,r,run["current_day"],"content_applied","orchestrator",prod["shop_id"],{"content_id":cid,"job_id":job['job_id'],"attempt":job['attempt'],"cover_option":decision["cover_option"],"skip_video":b.skip_video,"video_review_ack":b.video_review_ack},text="Xuất bản đúng nội dung người bán đã chọn")
        proposal=self.entity(c,"proposals",r,"proposal_id",job["proposal_id"])
        approval=one(c,"SELECT * FROM decisions WHERE run_id=? AND target_type='proposal' AND target_id=? AND action='approve'",(r,job["proposal_id"]))
        require(approval,"APPROVAL_REQUIRED","Chưa có approval gói")
        _,versions=self.evaluation(c,r,prod["shop_id"],proposal["package"])
        self.apply(c,p,r,{"proposal_id":proposal["proposal_id"],"approval_decision_id":approval["decision_id"],"expected_inventory_version":versions["inventory_version"],"expected_rules_version":versions["rules_version"]})
        if prod["shop_id"]==run['demo_shop_id']: c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
        return self.public(c,r,prod["shop_id"])

    def checked_job_asset(self,c,r,job,aid,kind):
        asset=self.entity(c,'assets',r,'asset_id',aid)
        require(asset['kind']==kind and asset['product_id']==job['product_id'] and asset['upload_status']=='ready' and one(c,'SELECT job_id FROM asset_jobs WHERE run_id=? AND job_id=? AND asset_id=?',(r,job['job_id'],aid)),'ASSET_SCOPE','File không thuộc job hiện tại',404)
        path=self.object_path(asset['object_key'])
        require(path.is_file() and path.stat().st_size==asset['size_bytes'],'ASSET_INVALID','File thiếu hoặc checksum không khớp',422)
        data=path.read_bytes()
        require(hashlib.sha256(data).hexdigest()==asset['sha256'],'ASSET_INVALID','File thiếu hoặc checksum không khớp',422)
        mime=asset['mime_type']
        valid=(kind=='image' and ((mime=='image/png' and data.startswith(b'\x89PNG\r\n\x1a\n')) or
               (mime=='image/jpeg' and data.startswith(b'\xff\xd8\xff')) or
               (mime=='image/webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP'))) or (kind=='video' and mime=='video/mp4' and data[4:8]==b'ftyp')
        require(valid,'MIME_INVALID','Nội dung file không khớp loại đã khai',422)
        return asset

    def validate_content_text(self,c,r,job,title,description):
        source=self.entity(c,'content_versions',r,'content_id',job['source_content_id'])
        product=self.product(c,r,job['shop_id'])
        styles=self.rules(c,r,job['shop_id'])[0]['content_style_notes']
        facts=[source['title'],source['description'],*[v['text_vi'] for v in product['facts']['verified_claims']],*styles]
        text=title+'. '+description
        require(bool(title.strip()) and len(title)<=120 and 0<len(description)<=5000 and not any(term in text.casefold() for term in ('bảo hành','chống nước','không ồn','5000mah')) and content_matches_facts(text,facts),'CLAIM_INVALID','Nội dung không khớp thuộc tính đã kiểm chứng',422)
        return True

    def content_result(self,c,p,r,jid,body):
        job=self.entity(c,"content_jobs",r,"job_id",jid)
        self.scope(c,p,r,job["shop_id"],{"content_worker"})
        require("*" in p.allowed_job_ids or jid in p.allowed_job_ids,"NOT_FOUND","Job không được giao cho worker",404)
        b=M.ContentResult.model_validate(body)
        require(job["version"]==b.expected_job_version)
        require(job["status"] in {"queued","running"},"JOB_TERMINAL","Job đã có kết quả cuối")
        require(b.status in {"failed","timed_out"} or (job["lease_until"] and job["lease_until"]>=now()),"LEASE_EXPIRED","Lease content đã hết hạn")
        content=self.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
        frozen=content['status']=='published' or (content['status']=='superseded' and content['published_day'] is not None)
        require(content['status']=='draft' or frozen,'STALE_DRAFT','Nội dung không còn nhận kết quả')
        if frozen:
            require(b.status!='succeeded' or b.content_candidates,'CONTENT_REQUIRED','Job thành công cần bản nháp hợp lệ',422)
            require(not b.content_candidates or b.status=='succeeded')
        elif b.content_candidates:
            require(b.status=="succeeded")
            candidate=b.content_candidates
            allowed={"content_id","content_version","title","description","images","video","feedback_history","style_notes","checks"}
            require(set(candidate)<=allowed and {"title","description","images","video"}<=set(candidate),"CONTENT_SCHEMA","Bản nháp sai schema",422)
            self.validate_content_text(c,r,job,candidate['title'],candidate['description'])
            require(len(candidate["images"])==3 and {v["option"] for v in candidate["images"]}==set("ABC"),"CONTENT_SCHEMA","Cần đúng ba phương án",422)
            for image in candidate["images"]:
                if image['status'] not in {'done','cached'}:
                    require(image.get('asset_id') is None,'CONTENT_SCHEMA','Ảnh chưa sẵn sàng không có asset',422)
                    image['path']=None
                    continue
                require(image.get('asset_id') is not None,'ASSET_PENDING','Ảnh chưa sẵn sàng',422)
                a=self.asset_access(c,p,r,image["asset_id"])
                require(a["kind"]=="image" and a["product_id"]==job["product_id"] and a["upload_status"]=="ready")
                require(one(c,"SELECT job_id FROM asset_jobs WHERE run_id=? AND job_id=? AND asset_id=?",(r,jid,image["asset_id"])),"ASSET_SCOPE","Ảnh không thuộc job hiện tại",404)
                require(image.get("status") in {"done","cached"},"ASSET_PENDING","Ảnh kết quả chưa sẵn sàng",422)
                require(set(image)<={"option","status","asset_id","path","prompt","source","error"},"CONTENT_SCHEMA","Ảnh sai schema",422)
                image["path"]=f"/api/v1/runs/{r}/assets/{a['asset_id']}/download"
            if not b.fallback_used and all(x["status"]=="done" for x in candidate["images"]):
                hashes={self.entity(c,"assets",r,"asset_id",x["asset_id"])["sha256"] for x in candidate["images"]}
                require(len(hashes)==3,"DUPLICATE_COVERS","Ba ảnh hoàn tất phải là ba file khác nhau",422)
            require(not one(c,"SELECT * FROM content_jobs WHERE run_id=? AND proposal_id=? AND attempt>?",(r,job["proposal_id"],job["attempt"])),"SUPERSEDED_JOB","Job đã bị thay thế")
            video=candidate["video"]
            require(isinstance(video,dict) and video.get("status") in {"pending","running","done","failed","cached"},"CONTENT_SCHEMA","Video sai schema",422)
            require(set(video)<={"status","asset_id","path","job_id","prompt","error","source","reference_asset_id","reference_job_id","reference_attempt","review_passed","review_notes","duration_seconds","requested_duration_seconds","duration_matches_requested","short_description"},"CONTENT_SCHEMA","Video có trường không hợp lệ",422)
            video_id=video.get("asset_id")
            if video_id:
                a=self.asset_access(c,p,r,video_id);require(a["product_id"]==job["product_id"] and a["kind"]=="video" and a["upload_status"]=="ready")
                require(one(c,"SELECT job_id FROM asset_jobs WHERE run_id=? AND job_id=? AND asset_id=?",(r,jid,video_id)),"ASSET_SCOPE","Video không thuộc job",404)
                run=self.entity(c,'runs',r,'run_id',r)
                if run['config'].get('driver',{}).get('agent_version')=='native' and job['retry_scope']=='all':
                    first=next((image for image in candidate['images'] if image['option']=='A'),None)
                    require(first and first.get('asset_id') and video.get('reference_asset_id')==first['asset_id'] and video.get('reference_job_id')==jid and video.get('reference_attempt')==job['attempt'],'VIDEO_REFERENCE_INVALID','Video phải dùng ảnh A của lần tạo hiện tại',422)
                video["path"]=f"/api/v1/runs/{r}/assets/{a['asset_id']}/download"
            else:video["path"]=None
            content=self.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
            require(content["status"]=="draft")
            wizard=job['brief'].get('wizard')
            if wizard:
                first=next((image for image in candidate['images'] if image['option']=='A'),None)
                image_slot=job['provider_state'].get('A',{})
                require(first and first.get('status')=='done' and first.get('asset_id')==image_slot.get('asset_id')
                        and image_slot.get('status')=='done' and image_slot.get('source_asset_id'),
                        'IMAGE_REFERENCE_INVALID','Ảnh phải thuộc lượt tạo hiện tại',422)
                if wizard.get('stage')=='image':
                    require(video_id is None and video.get('status')=='pending', 'VIDEO_NOT_REQUESTED','Chưa yêu cầu tạo video',422)
                else:
                    require(wizard.get('stage')=='video' and candidate['images']==content['cover_options']
                            and video_id and job['provider_state'].get('video',{}).get('asset_id')==video_id
                            and job['provider_state']['video'].get('status')=='done',
                            'VIDEO_REFERENCE_INVALID','Video phải thuộc lượt tạo hiện tại',422)
                    video['requested_duration_seconds']=wizard['duration']
                    video['duration_matches_requested']=self.duration_matches(wizard['duration'],video.get('duration_seconds'))
            prior=self.entity(c,"content_versions",r,"content_id",job["source_content_id"])
            if job["attempt"]>1 and job["retry_scope"]=="images":
                require((candidate["title"],candidate["description"],video)==(prior["title"],prior["description"],prior["video_job"]),"RETRY_SCOPE","Retry ảnh không được đổi text/video",422)
            if job["attempt"]>1 and job["retry_scope"]=="text":
                require(candidate["images"]==prior["cover_options"] and video==prior["video_job"],"RETRY_SCOPE","Retry text không được đổi media",422)
            c.execute("UPDATE content_versions SET title=?,description=?,cover_options_json=?,video_job_json=?,video_asset_id=?,validation_json=?,status='validated',version=version+1,updated_at=? WHERE run_id=? AND content_id=?",(candidate["title"],candidate["description"],dumps(candidate["images"]),dumps(video),video_id,dumps(candidate.get("checks",["Kiểm tra thông số bằng code"])),now(),r,content["content_id"]))
        elif b.status=="succeeded":
            raise Fault("CONTENT_REQUIRED","Job thành công cần bản nháp hợp lệ",422)
        elif b.status in {"failed","timed_out"}:
            run=self.entity(c,'runs',r,'run_id',r)
            if job['brief'].get('wizard',{}).get('stage')=='video':
                video={'status':'failed','asset_id':None,'path':None,'error':b.error_code or 'MEDIA_UNAVAILABLE'}
                c.execute("UPDATE content_versions SET video_job_json=?,video_asset_id=NULL,status='validated',version=version+1 WHERE run_id=? AND content_id=?",(dumps(video),r,job['output_content_ids'][0]))
            elif run['config'].get('driver',{}).get('agent_version')=='native':
                unavailable=[{'option':option,'status':'failed','asset_id':None,'path':None,'error':b.error_code or 'MEDIA_UNAVAILABLE'} for option in 'ABC']
                video={'status':'failed','asset_id':None,'path':None,'error':b.error_code or 'MEDIA_UNAVAILABLE'}
                c.execute("UPDATE content_versions SET cover_options_json=?,video_job_json=?,video_asset_id=NULL,status='validated',version=version+1 WHERE run_id=? AND content_id=?",(dumps(unavailable),dumps(video),r,job['output_content_ids'][0]))
            else:
                c.execute("UPDATE content_versions SET status='validated',version=version+1 WHERE run_id=? AND content_id=?",(r,job["output_content_ids"][0]))
        c.execute("UPDATE content_jobs SET status=?,provider_job_id=COALESCE(?,provider_job_id),fallback_used=?,error_code=?,lease_until=?,version=version+1,updated_at=? WHERE run_id=? AND job_id=?",(b.status,b.provider_job_id,b.fallback_used or b.status in {"failed","timed_out"},b.error_code,self.expires(120) if b.status=="running" else None,now(),r,jid))
        return self.entity(c,"content_jobs",r,"job_id",jid)

    def knowledge_search(self,c,p,r,body):
        run=self.scope(c,p,r,roles={"platform_agent","shop_agent","seller","content_worker","orchestrator","learning_worker"})
        b=M.KnowledgeSearch.model_validate(body)
        worker_products=None
        if p.role=="content_worker":
            jobs=many(c,"SELECT * FROM content_jobs WHERE run_id=?",(r,))
            worker_products={job["product_id"] for job in jobs if ("*" in p.allowed_job_ids or job["job_id"] in p.allowed_job_ids) and ("*" in p.allowed_shop_ids or job["shop_id"] in p.allowed_shop_ids)}
            require(not b.product_id or b.product_id in worker_products,"NOT_FOUND","Sản phẩm không thuộc job",404)
        if b.product_id:
            prod=self.entity(c,"products",r,"product_id",b.product_id);self.scope(c,p,r,prod["shop_id"])
        def normalize(text):
            return "".join(ch for ch in unicodedata.normalize("NFD",text.casefold()) if not unicodedata.combining(ch))
        terms=set(normalize(b.query).split())
        out=[]
        for doc in many(c,"SELECT * FROM knowledge_documents WHERE index_status='ready' AND knowledge_release='knowledge-v1' ORDER BY document_id"):
            if worker_products is not None and doc["document_id"].startswith("product_") and doc["document_id"][8:] not in worker_products:continue
            if doc["effective_from"]>business_date(run["current_day"]): continue
            if doc["effective_to"] and doc["effective_to"]<business_date(run["current_day"]):continue
            if doc["collection_scope"]=="shop_private":
                if p.role not in {"shop_agent","seller","orchestrator","learning_worker"} or doc["owner_run_id"]!=r or (doc["owner_shop_id"] not in p.allowed_shop_ids and "*" not in p.allowed_shop_ids):continue
            if b.document_types and doc["type"] not in b.document_types:continue
            if b.product_id and doc["document_id"].startswith("product_") and doc["document_id"]!=f"product_{b.product_id}":continue
            path=self.object_path(doc["source_object_key"])
            if not path.is_file():continue
            text=path.read_text(encoding="utf-8")
            score=len(terms&set(normalize(text).split()))
            if score:out.append({"document_id":doc["document_id"],"document_version":doc["document_version"],"title":doc["title"],"score":score,"excerpt":text[:1800],"source_reference":doc["document_id"],"backend":"local_keyword","is_simulated":True})
        return sorted(out,key=lambda v:(-v["score"],v["document_id"]))[:b.top_k]
