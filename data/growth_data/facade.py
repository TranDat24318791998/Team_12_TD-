"""Nine legacy demo endpoints share the same commands as the versioned API."""

from .service import Principal
from .storage import dumps, many, now, one
from .simulation import aggregate
from .errors import Fault, require


class Facade:
    def __init__(self, service): self.s=service

    def current(self,c,p):
        row=one(c,"SELECT r.* FROM active_runs a JOIN runs r ON r.run_id=a.run_id WHERE a.session_id=?",(p.session_id,))
        require(row,"RUN_REQUIRED","Cần đặt lại hoặc khởi tạo phiên",404)
        return row

    def internal(self,p,r,s="D"):
        return Principal("legacy_orchestrator","orchestrator",p.session_id,(r,),(s,))

    def forecast_view(self,c,r,fid):
        if not fid:return None
        f=self.s.entity(c,"forecasts",r,"forecast_id",fid)
        return {**{k:f[k] for k in ("low","point","high","factor_used")},"stock_warning":bool(f["stock_warning"])}

    def card(self,c,r,card):
        if not card:return None
        prop=self.s.entity(c,"proposals",r,"proposal_id",card["proposal_id"]) if card["proposal_id"] else None
        question=self.s.entity(c,"rule_questions",r,"question_id",card["question_id"]) if card["question_id"] else None
        ev=self.s.evaluation(c,r,card["shop_id"],prop["package"])[0] if prop else {}
        run=self.s.entity(c,'runs',r,'run_id',r)
        remaining=max(0,3-c.execute('SELECT COUNT(*) FROM negotiations WHERE run_id=? AND shop_id=? AND day=?',(r,card['shop_id'],card['day'])).fetchone()[0]) if prop else 0
        return {"card_id":card["card_id"],"version":card['version'],"brief_version":run['brief_version'],"negotiation_id":prop['negotiation_id'] if prop else None,"proposal_id":prop['proposal_id'] if prop else None,"proposal_version":prop['version'] if prop else None,"shop_id":card["shop_id"],"day":card["day"],"kind":card["kind"],
                "can_negotiate":bool(prop and remaining),"renegotiations_left":remaining,
                "package":prop["package"] if prop else None,"forecast":self.forecast_view(c,r,prop["forecast_id"]) if prop else None,
                "profit_after_fees_per_unit":ev.get("unit_contribution_vnd"),
                "breakeven_roas_display":ev.get("stop_threshold") if prop and prop["package"]["ads_daily_budget"] else None,
                "reasons_vi":card["reasons"],"warnings_vi":["Giá bán đang lỗ sau phí; chỉ làm mới nội dung"] if ev.get("unprofitable") else card["warnings"],"notices_vi":card["notices"],
                "rule_question":{"pref_id":question["question_id"],"field":question["field"],"value":str(question["value"]),"text_vi":question["text_vi"]} if question else None}

    def draft(self,c,r,s="D"):
        job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id=? ORDER BY rowid DESC LIMIT 1",(r,s))
        if not job:return None
        content=self.s.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
        if content["status"] in {"published","superseded","rejected"}:return None
        card,_=self.s.content_approval(c,r,job)
        run=self.s.entity(c,'runs',r,'run_id',r)
        images=[{k:v for k,v in x.items() if k!='asset_id'} for x in content['cover_options']]
        video={k:v for k,v in content['video_job'].items() if k!='asset_id'}
        wizard=job['brief'].get('wizard')
        if run['config'].get('driver',{}).get('agent_version')=='native' and job['provider']=='assigned_worker' and job['status'] in {'awaiting_image','queued','running'}:
            def slot_view(slot,kind):
                entry=job['provider_state'].get(slot,{})
                view={'status':entry.get('status','pending'),'path':None,'source':entry.get('source')}
                if entry.get('status')=='done':
                    try:
                        if not entry.get('asset_id'):raise Fault('ASSET_SCOPE','Chưa có file cho lượt hiện tại',404)
                        asset=self.s.checked_job_asset(c,r,job,entry['asset_id'],kind)
                        if asset['job_id']!=job['job_id']:raise Fault('ASSET_SCOPE','File không thuộc lượt hiện tại',404)
                        view['path']=f"/api/v1/runs/{r}/assets/{asset['asset_id']}/download"
                    except (Fault,OSError):view['status']='failed'
                if kind=='video':
                    view.update({key:entry[key] for key in ('review_passed','review_notes','duration_seconds','short_description') if key in entry})
                    if wizard and wizard.get('stage')=='video':
                        view['requested_duration_seconds']=wizard['duration']
                        view['duration_matches_requested']=self.s.duration_matches(wizard['duration'],entry.get('duration_seconds'))
                return view
            images=[{'option':slot,**slot_view(slot,'image')} for slot in 'ABC']
            video=slot_view('video','video')
        wizard_view=None
        if wizard:
            stage=wizard.get('stage')
            if job['status']=='awaiting_image':stage='choose_image'
            elif job['status'] in {'queued','running'}:stage=f'{stage}_queued'
            elif job['status']=='succeeded':stage=f'{stage}_ready'
            else:stage='failed'
            wizard_view={**wizard,'stage':stage}
        input_image=None
        if wizard:
            aid=job['brief'].get('wizard_input_asset_id')
            selected=one(c,"SELECT * FROM assets WHERE run_id=? AND asset_id=? AND product_id=? AND kind='image'",(r,aid,job['product_id'])) if aid else self.s.wizard_input_asset(c,r,job)
            if selected:input_image=f"/api/v1/runs/{r}/assets/{selected['asset_id']}/download"
        return {"shop_id":s,"version":job["attempt"],"card_id":card['card_id'] if card else None,"brief_version":run['brief_version'],"job_id":job['job_id'],"content_id":content['content_id'],"job_version":job['version'],"content_version":content['version'],"status":job['status'],"error_code":job['error_code'],"title":content["title"],"description":content["description"],"input_image":input_image,
                "images":images,"video":video,"wizard":wizard_view,"outcome_unknown":any(v.get('status') in {'unknown','outcome_unknown'} for v in job['provider_state'].values()),"feedback_history":content["feedback_history"],"style_notes":content["style_notes"],"checks":content["validation"]}

    def night_summary(self,c,r,run,handoff):
        if not handoff or not handoff['night_summary']:return None
        if run['demo_shop_id']!='D':return None
        summary=handoff['night_summary'].copy()
        if run['config'].get('driver',{}).get('agent_version')!='native':return summary
        history_ids=set(summary.get('history_updates',[]));preference_ids=set(summary.get('pref_candidates',[]))
        summary.update(history_updates=[],pref_candidates=[],history_refs=[],preference_refs=[])
        snapshot=one(c,'SELECT * FROM night_snapshots WHERE run_id=? AND day=? AND shop_id=?',(r,handoff['day'],run['demo_shop_id']))
        receipt=one(c,'SELECT * FROM night_commits WHERE run_id=? AND day=? AND shop_id=?',(r,handoff['day'],run['demo_shop_id']))
        if not snapshot or not receipt or handoff['status']!='completed':return summary
        if snapshot['snapshot_hash']!=receipt['snapshot_hash'] or handoff['receipt_hash']!=receipt['publication_hash']:return summary
        from app.domain.models.learning import NightCommit, NightSnapshot
        try:
            frozen=NightSnapshot.model_validate(snapshot['payload'])
            commit=NightCommit.model_validate(receipt['payload'])
        except ValueError:
            return summary
        if (frozen.run_id,frozen.shop_id,frozen.day,frozen.through_seq)!=(r,run['demo_shop_id'],handoff['day'],handoff['settlement_cursor']):return summary
        if (commit.run_id,commit.shop_id,commit.day,commit.snapshot_hash,commit.publication_hash)!=(r,run['demo_shop_id'],handoff['day'],snapshot['snapshot_hash'],receipt['publication_hash']):return summary
        applied=set(commit.knowledge.store.applied_ids)
        summary['source']=commit.source
        for item in frozen.derived.history:
            if item.negotiation_id not in history_ids or item.negotiation_id not in applied or item.shop_id!=run['demo_shop_id']:continue
            status={'agreed':'đã thống nhất','failed':'không đạt thỏa thuận','warning_only':'đã thống nhất với cảnh báo'}[item.status]
            parts=[f'Ngày {item.day}: {status} sau {item.rounds} vòng thương lượng']
            action={'accept':'người bán đã duyệt','edit':'người bán đã chỉnh sửa và duyệt','reject':'người bán đã từ chối','negotiate':'người bán yêu cầu thương lượng thêm'}.get(item.seller_action)
            if action:parts.append(action)
            if item.approved_package is not None:parts.append(f"gói đã áp dụng voucher {item.approved_package.voucher_pct}%")
            if item.outcome is not None:parts.append(f'ghi nhận {item.outcome.orders} đơn')
            summary['history_updates'].append('; '.join(parts)+'.')
            summary['history_refs'].append({'record_id':item.negotiation_id,'day':item.day,'version':item.version,'evidence_seqs':item.evidence_seqs})
        for item in frozen.derived.preferences:
            if item.pref_id not in preference_ids or item.pref_id not in applied or item.shop_id!=run['demo_shop_id']:continue
            value=self.s.safe_text(c,r,item.value)
            if value!=item.value:continue
            if item.field=='content_style':text=f'Ghi nhận phong cách nội dung: {value}.'
            elif item.value.isdigit() and 0<=int(item.value)<=30:text=f'Ghi nhận mức voucher người bán chọn: {item.value}%.'
            else:continue
            summary['pref_candidates'].append(text)
            summary['preference_refs'].append({'record_id':item.pref_id,'field':item.field,'evidence_seqs':item.evidence_seqs})
        return summary

    def state(self,c,p,run_id=None):
        run=self.s.run(c,p,run_id) if run_id else self.current(c,p);r=run["run_id"];self.s.scope(c,p,r,"D",{"seller"})
        card=one(c,"SELECT * FROM cards WHERE run_id=? AND shop_id='D' AND status='pending'",(r,))
        active=one(c,"SELECT * FROM campaigns WHERE run_id=? AND shop_id='D' AND status='active'",(r,))
        handoff=one(c,"SELECT * FROM learning_handoffs WHERE run_id=? AND summary_shop_id='D' ORDER BY day DESC LIMIT 1",(r,))
        original=self.s.public(c,r,"D").copy()
        from .seed import world
        original.update({k:v for k,v in world()["shops"]["D"]["public"].items() if k not in {"images"}})
        seed_content=one(c,"SELECT * FROM content_versions WHERE run_id=? AND product_id='SP004' AND content_version=1",(r,))
        original["images"]=[f"/api/v1/runs/{r}/assets/{seed_content['cover_asset_id']}/download"]
        phase=run["phase"]
        step={"ready":"idle","awaiting_seller":"awaiting_decision","negotiating":"day_done","content_review":"content_review","settling":"day_done","learning":"day_done","day_closed":"night_done","complete":"complete","failed":"day_done"}[phase]
        if card:step="awaiting_decision"
        operation=one(c,"SELECT * FROM operations WHERE run_id=? AND status IN ('queued','running','failed') ORDER BY rowid DESC LIMIT 1",(r,))
        busy=bool(operation and operation["status"] in {"queued","running"})
        if run['config'].get('driver',{}).get('agent_version')=='native':
            busy=busy or bool(one(c,"SELECT job_id FROM content_jobs WHERE run_id=? AND status IN ('queued','running') LIMIT 1",(r,)))
        if operation and operation['status'] in {'queued','running'} and (operation['kind']=='start_day' or operation['kind'].startswith('renegotiate:')):step="negotiating"
        negotiation=None
        attempt=one(c,"SELECT * FROM operations WHERE run_id=? AND day=? AND (kind='start_day' OR kind LIKE 'renegotiate:%') ORDER BY rowid DESC LIMIT 1",(r,run['current_day']))
        if attempt and run['config'].get('driver',{}).get('agent_version')=='native':
            receipt=one(c,"SELECT response_json FROM idempotency_records WHERE principal_id='native_orchestrator' AND run_scope=? AND path='native/negotiation' AND key=?",(r,attempt['operation_id']+':D'))
            nid=receipt['response'].get('negotiation_id') if receipt and receipt['response'] else None
            neg=one(c,"SELECT * FROM negotiations WHERE run_id=? AND negotiation_id=? AND shop_id='D' AND day=?",(r,nid,run['current_day'])) if nid else None
            terminal=neg['terminal_receipt'] if neg and neg['terminal_receipt'] else {}
            status=attempt['status'] if attempt['status'] in {'queued','running'} else (neg['status'] if neg and neg['status'] in {'agreed','failed'} else 'unknown')
            if not neg and attempt['status']=='failed' and attempt['error_code']=='NATIVE_OPERATION_FAILED':status='failed'
            if attempt['status']=='failed' and 'UNKNOWN' in (attempt['error_code'] or ''):status='unknown'
            reason=self.s.safe_text(c,r,terminal.get('reason_vi') or '')
            if status=='failed' and not reason:reason='Agent chưa đưa ra được gói phù hợp.'
            if status=='unknown':reason='Tác vụ thương lượng chưa hoàn tất hoặc chưa rõ kết quả.'
            negotiation={'negotiation_id':nid,'status':status,'reason_vi':reason,'referee_action':terminal.get('referee_action')}
            if not receipt and attempt['status']=='succeeded':negotiation=None
        retry=one(c,"SELECT * FROM operations WHERE run_id=? AND day=? AND kind LIKE 'renegotiate:%' ORDER BY rowid DESC LIMIT 1",(r,run['current_day']))
        renegotiation=None
        if retry and retry['result'] and run['config'].get('driver',{}).get('agent_version')=='native':
            source_id=retry['result'].get('source_card_id')
            source=one(c,"SELECT * FROM cards WHERE run_id=? AND card_id=? AND shop_id='D' AND day=?",(r,source_id,run['current_day']))
            if source:
                receipt=one(c,"SELECT response_json FROM idempotency_records WHERE principal_id='native_orchestrator' AND run_scope=? AND path='native/negotiation' AND key=?",(r,retry['operation_id']+':D'))
                nid=receipt['response'].get('negotiation_id') if receipt and receipt['response'] else None
                neg=one(c,"SELECT * FROM negotiations WHERE run_id=? AND negotiation_id=? AND shop_id='D' AND day=?",(r,nid,run['current_day'])) if nid else None
                terminal=neg['terminal_receipt'] if neg and neg['terminal_receipt'] else {}
                status=retry['status'] if retry['status'] in {'queued','running'} else (neg['status'] if neg and neg['status'] in {'agreed','failed'} else 'unknown')
                if not neg and retry['status']=='failed' and retry['error_code']=='NATIVE_OPERATION_FAILED':status='failed'
                if retry['status']=='failed' and 'UNKNOWN' in (retry['error_code'] or ''):status='unknown'
                reason=self.s.safe_text(c,r,terminal.get('reason_vi') or '')
                if status=='failed' and not reason:reason='Agent chưa đưa ra được gói điều chỉnh.'
                if status=='unknown':reason='Tác vụ thương lượng chưa hoàn tất hoặc chưa rõ kết quả.'
                changed=None
                if status=='agreed' and neg['final_proposal_id'] and source['proposal_id']:
                    previous=self.s.entity(c,'proposals',r,'proposal_id',source['proposal_id'])
                    final=self.s.entity(c,'proposals',r,'proposal_id',neg['final_proposal_id'])
                    changed=previous['package']!=final['package']
                    if not changed:reason='Các agent giữ nguyên gói trước, chưa đưa ra điều chỉnh theo góp ý.'
                renegotiation={'source_card_id':source_id,'negotiation_id':nid,'status':status,'reason_vi':reason,
                               'referee_action':terminal.get('referee_action'),'changed':changed,
                               'restoration_status':retry['result'].get('restoration_status'),
                               'restored_card_id':retry['result'].get('restored_card_id'),
                               'restoration_reason_vi':retry['result'].get('restoration_reason_vi','')}
                allowed=bool(self.s.pending_offer_restoration(c,r,run['current_day'],'D') and not card
                             and not one(c,"SELECT operation_id FROM operations WHERE run_id=? AND day=? AND status IN ('queued','running')",(r,run['current_day'])))
                renegotiation.update(operation_id=retry['operation_id'],operation_version=retry['version'],source_card_version=source['version'],restoration_allowed=allowed)
                if status=='failed' and not allowed and not renegotiation['restoration_status']:
                    renegotiation['restoration_reason_vi']='Đề xuất gốc không còn chờ lựa chọn hoặc có tác vụ chưa hoàn tất.'
        current=self.s.product(c,r,"D")
        trace=one(c,"SELECT result_json FROM operations WHERE run_id=? AND json_extract(result_json,'$.trace_shop_id')='D' AND json_extract(result_json,'$.trace_url') IS NOT NULL ORDER BY rowid DESC LIMIT 1",(r,))
        rules,rules_version=self.s.rules(c,r,'D')
        active_card=None
        if active:
            active_card,approval=self.s.content_approval(c,r,{'proposal_id':active['proposal_id'],'shop_id':active['shop_id'],'product_id':active['product_id']})
            if not approval or approval['decision_id']!=active['approval_decision_id']:active_card=None
        metadata=one(c,'SELECT llm_limit FROM knowledge_meta WHERE run_id=?',(r,))
        limit=metadata['llm_limit'] if metadata and metadata['llm_limit'] is not None else getattr(self.s,'live_call_limit',None)
        used=c.execute('SELECT COUNT(*) FROM llm_call_reservations WHERE run_id=?',(r,)).fetchone()[0]
        preset=self.s.brief_preset(run)
        return {"run_id":r,"day":run["current_day"],"mode":run["mode"],"memory_enabled":bool(run["memory_enabled"]),"step":step,"brief":run['brief'],"brief_preset":preset,"brief_editable":preset is None,"rules_version":rules_version,"confirmed_style_notes":rules['content_style_notes'],
                "simulation_days":run["simulation_days"],"execution_profile":run["execution_profile"],"data_source":run["config"].get("source","simulation"),"busy":busy,
                "active_operation":self.s.operation_view(operation,p.role) if operation else None,
                "negotiation":negotiation,
                "renegotiation":renegotiation,
                "learning_status":handoff["status"] if handoff else None,"learning_error":handoff["error_code"] if handoff else None,"learning_version":handoff['version'] if handoff else None,"learning_day":handoff['day'] if handoff else None,"learning_retry_allowed":self.s.learning_retry_allowed(c,run,handoff),
                "content_refs":{"active_content_id":current["active_content_id"],"original_content_id":seed_content["content_id"],"product_version":current["version"]},
                "capabilities":{"trace":bool(trace),"faithful_llm_replay":False,"content_undo":True,"comparison":True,"external_workers":True},
                "links":{"trace":trace["result"]["trace_url"] if trace else None},
                "demo_shop":self.s.public(c,r,"D"),"demo_shop_original":original,
                "active_package":{"package":active["package_snapshot"],"start_day":active["start_day"],"end_day":active["end_day"],"ads_paused":active["ads_status"]=="paused","card_id":active_card['card_id'] if active_card else None} if active else None,
                "pending_card":self.card(c,r,card),"content_draft":self.draft(c,r),"last_night":self.night_summary(c,r,run,handoff),"live_calls_left":max(0,limit-used) if limit is not None else None}

    def decide(self,c,p,r,body):
        self.s.scope(c,p,r,"D",{"seller"})
        from .models import LegacyDecision
        body=LegacyDecision.model_validate(body).model_dump(exclude_unset=True)
        require(set(body)<={"card_id","expected_card_version","expected_brief_version","action","note_vi","edited_package","rule_answer"},"INVALID_FIELDS","Trường không được hỗ trợ",422)
        card=self.s.entity(c,"cards",r,"card_id",body["card_id"])
        require(card["shop_id"]=="D" and card["status"]=="pending","NOT_FOUND","Không tìm thấy thẻ đang chờ",404)
        run=self.s.run(c,p,r)
        if run['config'].get('driver',{}).get('agent_version')=='native':
            require(body.get('expected_card_version')==card['version'] and body.get('expected_brief_version')==run['brief_version'],'STALE_CARD','Thẻ hoặc brief đã thay đổi')
        if card['kind']=='question':
            require((body.get('action'),body.get('rule_answer')) in {('accept',True),('reject',False)},'ANSWER_INVALID','Câu trả lời không khớp hành động',422)
        if card["question_id"] and body.get("rule_answer") is not None:
            q=self.s.entity(c,"rule_questions",r,"question_id",card["question_id"])
            self.s.decision(c,p,r,dict(target_type="rule_question",target_id=q["question_id"],target_version=1,action="approve" if body["rule_answer"] else "reject",rule_answer=body["rule_answer"]))
        if card["kind"]=="question":
            require(body.get("rule_answer") is not None,"ANSWER_REQUIRED","Cần trả lời câu hỏi",422)
            c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
        else:
            require(body.get("action") in {"accept","edit","reject","negotiate"},"ACTION_INVALID","Hành động không hợp lệ",422)
            if body.get('action')=='negotiate':
                count=c.execute("SELECT COUNT(*) FROM negotiations WHERE run_id=? AND shop_id='D' AND day=?",(r,run['current_day'])).fetchone()[0]
                require(count<3,'MAX_RENEGOTIATIONS','Đã đủ hai lần thương lượng thêm')
            prop=self.s.entity(c,"proposals",r,"proposal_id",card["proposal_id"])
            decision=self.s.decision(c,p,r,dict(target_type="proposal",target_id=prop["proposal_id"],target_version=prop["version"],action={"accept":"approve","edit":"approve","reject":"reject","negotiate":"request_changes"}[body["action"]],edited_package=body.get("edited_package"),feedback_private=body.get("note_vi",""),feedback_shared=body.get('note_vi','')))
            internal=self.internal(p,r)
            if body["action"] in {"accept","edit"}:
                prop=self.s.entity(c,"proposals",r,"proposal_id",decision["target_id"])
                _,ver=self.s.evaluation(c,r,"D",prop["package"])
                if prop["package"]["content_refresh"]:self.s.content_create(c,internal,r,"D",dict(proposal_id=prop["proposal_id"],product_id=prop["product_id"]))
                else:
                    self.s.apply(c,internal,r,dict(proposal_id=prop["proposal_id"],approval_decision_id=decision["decision_id"],expected_inventory_version=ver["inventory_version"],expected_rules_version=ver["rules_version"]))
                    c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
            elif body["action"]=="negotiate":
                # An authorized reference driver, not an agent model, handles the local branch.
                if self.s.run(c,p,r)["execution_profile"]=="reference":
                    self.s.reference_offer(c,internal,r,"D",source_card_id=card["card_id"],owner_note=body.get("note_vi"))
                else:
                    self.s.queue_renegotiation(c,p,r,card["card_id"],body.get("note_vi",""))
            else:c.execute("UPDATE runs SET phase='negotiating' WHERE run_id=?",(r,))
        state=self.state(c,p,r)
        result={"step":state["step"],"card":state["pending_card"]}
        if state['active_operation'] and state['active_operation']['status'] in {'queued','running'}:
            result.update(operation_id=state['active_operation']['operation_id'],status=state['active_operation']['status'])
        return result

    def retry(self,c,p,r,body):
        run=self.s.run(c,p,r)
        if run['config'].get('driver',{}).get('agent_version')=='native':
            from .models import LegacyContentRetry
            body=LegacyContentRetry.model_validate(body).model_dump()
        else: require("feedback_vi" in body and set(body)<={"feedback_vi","retry_scope"},"INVALID_FIELDS","Cần feedback_vi",422)
        job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D' ORDER BY rowid DESC LIMIT 1",(r,))
        require(job,"CONTENT_REQUIRED","Chưa có nội dung")
        if run['config'].get('driver',{}).get('agent_version')=='native': self._check_binding(c,r,job,body)
        self.s.content_create(c,p,r,"D",dict(proposal_id=job["proposal_id"],product_id=job["product_id"],feedback_vi=body["feedback_vi"],expected_current_attempt=job["attempt"],retry_scope=body.get("retry_scope","images")))
        return {"draft":self.draft(c,r)}

    def start_media(self,c,p,r,body,stage):
        from .models import LegacyContentImage, LegacyContentVideo
        model=LegacyContentImage if stage=='image' else LegacyContentVideo
        body=model.model_validate(body).model_dump()
        run=self.s.scope(c,p,r,'D',{'seller'})
        job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D' ORDER BY rowid DESC LIMIT 1",(r,))
        require(job,'CONTENT_REQUIRED','Chưa có nội dung')
        self._check_binding(c,r,job,body)
        wizard=job['brief'].get('wizard')
        require(wizard and run['phase']=='content_review','STAGED_MEDIA_REQUIRED','Bản nội dung không hỗ trợ luồng này')
        content=self.s.entity(c,'content_versions',r,'content_id',job['output_content_ids'][0])
        if stage=='image':
            require(job['status']=='awaiting_image' and wizard.get('stage')=='choose_image' and content['status']=='draft',
                    'STALE_DRAFT','Ảnh đã được yêu cầu hoặc bản nội dung đã thay đổi')
            source=self.s.wizard_input_asset(c,r,job)
            require(source,'MEDIA_INPUT_MISSING','Không tìm thấy ảnh sản phẩm hợp lệ')
            c.execute('INSERT OR IGNORE INTO asset_jobs(run_id,asset_id,job_id) VALUES(?,?,?)',(r,source['asset_id'],job['job_id']))
            self.s.checked_job_asset(c,r,job,source['asset_id'],'image')
            wizard={**wizard,'stage':'image','background':body['background'],'wishes':body['wishes'].strip()}
        else:
            require(job['status']=='succeeded' and wizard.get('stage')=='image' and content['status']=='validated',
                    'IMAGE_REQUIRED','Cần tạo ảnh trước khi chọn video')
            image=next((item for item in content['cover_options'] if item['option']=='A'),None)
            slot=job['provider_state'].get('A',{})
            require(image and image.get('status')=='done' and image.get('asset_id')==slot.get('asset_id')
                    and slot.get('status')=='done' and slot.get('source_asset_id') and 'video' not in job['provider_state'],
                    'IMAGE_REQUIRED','Ảnh tạo chưa sẵn sàng')
            self.s.checked_job_asset(c,r,job,image['asset_id'],'image')
            wizard={**wizard,'stage':'video','output_type':body['output_type'],'duration':body['duration']}
            c.execute("UPDATE content_versions SET status='draft',version=version+1,updated_at=? WHERE run_id=? AND content_id=?",(now(),r,content['content_id']))
        brief={**job['brief'],'wizard':wizard}
        if stage=='image':brief['wizard_input_asset_id']=source['asset_id']
        c.execute("UPDATE content_jobs SET brief_json=?,status='queued',error_code=NULL,lease_until=?,version=version+1,updated_at=? WHERE run_id=? AND job_id=?",(dumps(brief),self.s.expires(120),now(),r,job['job_id']))
        self.s.event(c,r,run['current_day'],'content_job','seller','D',{'job_id':job['job_id'],'attempt':job['attempt'],'kind':stage,'status':'queued'},visibility='shop_private',text='Người bán đã yêu cầu tạo ảnh' if stage=='image' else 'Người bán đã yêu cầu tạo video')
        return {'draft':self.draft(c,r)}

    def use_content(self,c,p,r,body):
        run=self.s.run(c,p,r)
        if run['config'].get('driver',{}).get('agent_version')=='native':
            from .models import LegacyContentApply
            body=LegacyContentApply.model_validate(body).model_dump()
        else: require(set(body)=={"cover_option"},"INVALID_FIELDS","Cần cover_option",422)
        job=one(c,"SELECT * FROM content_jobs WHERE run_id=? AND shop_id='D' ORDER BY rowid DESC LIMIT 1",(r,))
        require(job,"CONTENT_REQUIRED","Chưa có nội dung")
        if run['config'].get('driver',{}).get('agent_version')=='native': self._check_binding(c,r,job,body)
        content=self.s.entity(c,"content_versions",r,"content_id",job["output_content_ids"][0])
        d=self.s.decision(c,p,r,dict(target_type="content",target_id=content["content_id"],target_version=content["version"],action="approve",cover_option=body["cover_option"]))
        listing=self.s.publish(c,self.internal(p,r),r,content["content_id"],dict(approval_decision_id=d["decision_id"],expected_active_content_id=self.s.product(c,r,"D")["active_content_id"],skip_video=body.get('skip_video',False),video_review_ack=body.get('video_review_ack',False)))
        return {"listing":listing}

    def _check_binding(self,c,r,job,body):
        run=self.s.entity(c,'runs',r,'run_id',r)
        card,_=self.s.content_approval(c,r,job)
        require(card and body['card_id']==card['card_id'] and body['expected_brief_version']==run['brief_version'] and body['expected_draft_version']==job['attempt'] and body['expected_job_id']==job['job_id'] and body['expected_content_id']==job['output_content_ids'][0],'STALE_DRAFT','Bản nội dung đã thay đổi')

    def night(self,c,p,r):
        run=self.s.run(c,p,r)
        self.s.operation(c,p,r,"close_day",dict(expected_day=run["current_day"],expected_version=run["version"]))
        run=self.s.run(c,p,r)
        handoff=one(c,"SELECT * FROM learning_handoffs WHERE run_id=? AND day=?",(r,run["current_day"]))
        self.s.operation(c,p,r,"advance_day",dict(expected_day=run["current_day"],expected_version=run["version"]))
        run=self.s.run(c,p,r)
        return {"summary":handoff["night_summary"],"next_day":None if run["phase"]=="complete" else run["current_day"]}
