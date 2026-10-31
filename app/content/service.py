"""Data-bound native content worker; provider IO never holds a Data transaction."""

import asyncio

from app.agents.content import generate_content_from_context
from app.domain.models.learning import ContentMemoryView
from app.domain.models.tools import ContentContext
from app.infrastructure.media_gateway import MediaError, MediaGateway


class ContentService:
    def __init__(self, bridge, settings, llm, *, media_client=None):
        self.bridge, self.settings, self.llm = bridge, settings, llm
        self.media = media_client or MediaGateway(settings)
        self.closed = False
        self.tasks = set()

    async def close(self):
        self.closed = True
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.media.close()

    async def process_job(self, run_id, job_id):
        task = asyncio.current_task()
        self.tasks.add(task)
        heartbeat = None
        try:
            snapshot = self.bridge.snapshot(run_id, job_id)
            job = snapshot['job']
            # A previous process may have invoked a paid provider before it died.
            # Its persisted bindings do not prove whether the native call finished.
            if snapshot['provider_state']:
                self.bridge.update_slot(run_id, job_id, 'inputs', {'status':'unknown','error':'CONTENT_RESTART_UNKNOWN'})
                raise MediaError('CONTENT_RESTART_UNKNOWN', unknown=True)
            async def pulse():
                while True:
                    await asyncio.sleep(20)
                    current = self.bridge.snapshot(run_id, job_id)['job']
                    self.bridge.heartbeat(run_id, job_id, current['version'])
            self.bridge.heartbeat(run_id, job_id, job['version'])
            heartbeat = asyncio.create_task(pulse())
            # Reject an absent or invalid original before any native or media provider call.
            input_asset = self.bridge.input_asset(run_id, job_id)
            if not input_asset:
                raise MediaError('MEDIA_INPUT_MISSING')
            product_bytes = input_asset['bytes']
            product = snapshot['product']
            product_kind = product['facts'].get('product_kind')
            if product_kind not in {'handheld_fan', 'desktop_fan'}:
                raise MediaError('MEDIA_PRODUCT_KIND_MISSING')
            offline = self.settings.media_mode == 'offline'
            if not offline:
                logo_bytes = self.media.read_input(self.settings.demo_logo_image_path) if self.settings.demo_logo_image_path else None
                await self.media.preflight(product_kind)
                product_id = await self.media.upload(run_id, product_bytes)
                logo_id = await self.media.upload(run_id, logo_bytes) if logo_bytes else None
                self.bridge.update_slot(run_id, job_id, 'inputs', {'source_asset_id': product_id, 'logo_asset_id': logo_id})
            previous = job['brief']['previous_content']
            facts = [item['text_vi'] for item in product['facts']['verified_claims']]
            styles = snapshot['rules']['content_style_notes']
            feedback = job['feedback_history']
            fact_source = product['facts']['verified_claims'][0].get('source_reference', 'product:facts') if facts else 'product:facts'
            context = ContentContext(shop_id=job['shop_id'], title=snapshot['content']['title'], description=snapshot['content']['description'],
                attributes=facts, images=[], fact_source_id=fact_source,
                memory=ContentMemoryView(confirmed_style_notes=styles, rules_version=snapshot['rules_version'], preference_ids=snapshot.get('preference_ids', [])),
                feedback_history=feedback, card_id=snapshot['card']['card_id'], brief_version=snapshot['brief_version'], draft_version=job['attempt'],
                references=snapshot.get('references', []))
            emit = lambda kind, data: self.bridge.emit(run_id, job_id, kind, data)
            llm = self.llm(run_id) if callable(self.llm) else self.llm
            text = await asyncio.to_thread(generate_content_from_context, context, llm, emit,
                                           f'{run_id}:content:{job_id}:{job["attempt"]}')
            if self.closed:
                return
            title, description = ((previous['title'], previous['description']) if job['retry_scope'] == 'images'
                                  else (text.value.title, text.value.description))
            if offline:
                self.bridge.validate_text(run_id, job_id, title, description)
            else:
                self.bridge.stage_text(run_id, job_id, title, description, text.value.checks)
            if offline:
                images = [{'option':option, 'status':'cached', 'asset_id':input_asset['asset_id'], 'source':'cache',
                           'prompt':'Ảnh gốc sản phẩm; chế độ ngoại tuyến không tạo ảnh mới.'} for option in 'ABC']
                video = {'status':'failed', 'asset_id':None, 'source':'unavailable',
                         'error':'Chế độ ngoại tuyến không tạo video; chọn bỏ qua video.'}
                if job['attempt'] > 1 and job['retry_scope'] == 'images':
                    video = previous['video']
                elif job['attempt'] > 1 and job['retry_scope'] == 'text':
                    images, video = previous['images'], previous['video']
                candidate = {'title':title, 'description':description, 'images':images, 'video':video,
                             'feedback_history':feedback, 'style_notes':styles,
                             'checks':[*text.value.checks, 'Ngoại tuyến: A, B, C dùng cùng ảnh gốc, không tạo ảnh hoặc video mới.']}
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                heartbeat = None
                current = self.bridge.snapshot(run_id, job_id)['job']
                self.bridge.complete(run_id, job_id, {'expected_job_version':current['version'], 'status':'succeeded',
                    'content_candidates':candidate, 'fallback_used':True})
                return
            bright = any('sáng' in item.casefold() or 'bright' in item.casefold() for item in [*styles, *feedback])
            preference = 'bright' if bright else 'default'
            image_bodies = {slot: {'job_type':'image','logo_asset_id':logo_id,'product_asset_id':product_id,
                'style_asset_id':None,'style':style,'product_kind':product_kind,'product_name':product['name'],
                'background_preference':preference} for slot, style in zip('ABC',
                    ['clean_white','pastel_lifestyle','summer_fresh' if bright else 'premium_studio'])}
            deadline = asyncio.get_running_loop().time() + self.settings.media_draft_timeout_seconds

            async def start(slot, body):
                reservation = self.bridge.reserve_slot(run_id, job_id, slot, body)
                if reservation['status'] == 'skipped':
                    return reservation
                if reservation['status'] in {'unknown', 'outcome_unknown'}:
                    raise MediaError('MEDIA_OUTCOME_UNKNOWN', unknown=True)
                if reservation['status'] == 'failed':
                    raise MediaError(reservation.get('error') or 'MEDIA_JOB_FAILED')
                if reservation['status'] == 'done':
                    return reservation
                if reservation.get('remote_id'):
                    try:
                        return await self.media.get_job(run_id, reservation['remote_id'])
                    except MediaError as exc:
                        self.bridge.update_slot(run_id, job_id, slot, {'status':'unknown','error':exc.code})
                        raise
                if not reservation['can_submit']:
                    self.bridge.update_slot(run_id, job_id, slot, {'status':'unknown','error':'MEDIA_SUBMIT_UNKNOWN'})
                    raise MediaError('MEDIA_SUBMIT_UNKNOWN', unknown=True)
                if slot == 'video':
                    self.bridge.update_slot(run_id, job_id, slot, {'media_text_vision_calls_reserved':3})
                try:
                    response = await self.media.submit(run_id, slot, reservation['request'], reservation['idempotency_key'])
                    self.bridge.update_slot(run_id, job_id, slot, {'status':'running','remote_id':response['job_id']})
                    return response
                except MediaError as exc:
                    self.bridge.update_slot(run_id, job_id, slot, {'status':'unknown' if exc.unknown else 'failed','error':exc.code})
                    raise

            async def finish(slot, remote):
                if remote.get('status') == 'done' and remote.get('asset_id') and not remote.get('job_id'):
                    return remote
                try:
                    result = await self.media.wait(run_id, remote, deadline)
                    data = await self.media.download(run_id, result, video=slot == 'video')
                    asset_id = self.bridge.import_asset(run_id, job_id, data=data,
                        mime_type='video/mp4' if slot == 'video' else 'image/jpeg', kind='video' if slot == 'video' else 'image')
                    metadata = result.get('result') or {}
                    updates = {'status':'done','asset_id':asset_id,'source':'live'}
                    if slot == 'video':
                        updates.update(review_passed=metadata.get('visual_review_passed'),
                            review_notes=(metadata.get('visual_review') or {}).get('notes_vi'), duration_seconds=metadata.get('duration_seconds'),
                            media_text_vision_calls_completed=metadata.get('media_text_vision_calls_completed', 0))
                    else:
                        updates['source_asset_id'] = metadata.get('asset_id')
                    return self.bridge.update_slot(run_id, job_id, slot, updates)
                except MediaError as exc:
                    return self.bridge.update_slot(run_id, job_id, slot, {'status':'unknown' if exc.unknown else 'failed','error':exc.code})

            async def launch(slot, body):
                try:
                    return await start(slot, body)
                except MediaError as exc:
                    return {'status':'unknown' if exc.unknown else 'failed','error':exc.code}

            async def generate(slot, body):
                remote = await launch(slot, body)
                return await finish(slot, remote) if remote.get('job_id') or remote.get('asset_id') else remote

            image_tasks = {slot: asyncio.create_task(generate(slot, image_bodies[slot])) for slot in 'ABC'}

            async def generate_video():
                a = await image_tasks['A']
                if a.get('status') != 'done' or not a.get('source_asset_id') or job['retry_scope'] == 'images':
                    return {'status':'failed','error':'REFERENCE_IMAGE_FAILED'}
                narration = ' '.join((product['name'] + ', ' + ', '.join(facts)).split()[:20])
                video_body = {'input_asset_id':a['source_asset_id'],'product_name':product['name'],'product_kind':product_kind,
                    'verified_facts':facts,'script':narration,'mode':'muse','output_type':'realistic_human','duration':5,
                    'aspect':'9:16','generate_script':True,'generate_image':False,'voice':'muse','music':'none',
                    'setting':'Bối cảnh sáng tự nhiên.' if bright else 'Bối cảnh tự nhiên.',
                    'motion_prompt':('One adult naturally holds the same handheld fan by its handle.' if product_kind == 'handheld_fan'
                                     else 'One adult naturally demonstrates the same desktop fan, preserving its base and controls.')}
                return await generate('video', video_body)

            tasks = {**image_tasks, 'video':asyncio.create_task(generate_video())}
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            outputs = dict(zip(tasks, results))
            if any(value.get('status') == 'unknown' for value in outputs.values()):
                raise MediaError('MEDIA_OUTCOME_UNKNOWN', unknown=True)
            a = outputs['A']
            images = [{'option':slot,'status':'done' if outputs[slot].get('status')=='done' else 'failed',
                       'asset_id':outputs[slot].get('asset_id'),'source':outputs[slot].get('source','unavailable'),
                       'error':outputs[slot].get('error')} for slot in 'ABC']
            if job['retry_scope'] == 'images':
                video = previous['video']
            else:
                v = outputs.get('video', {'status':'failed','error':'REFERENCE_IMAGE_FAILED'})
                video = {'status':'done' if v.get('status')=='done' else 'failed','asset_id':v.get('asset_id'),
                         'source':v.get('source','unavailable'),'error':v.get('error'),
                         'reference_asset_id':a.get('asset_id'),'reference_job_id':job_id,'reference_attempt':job['attempt'],
                         'review_passed':v.get('review_passed'),'review_notes':v.get('review_notes'),
                         'duration_seconds':v.get('duration_seconds')}
            candidate = {'title':title,'description':description,'images':images,'video':video,
                         'feedback_history':feedback,'style_notes':styles,'checks':text.value.checks}
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            heartbeat = None
            current = self.bridge.snapshot(run_id, job_id)['job']
            self.bridge.complete(run_id, job_id, {'expected_job_version':current['version'],'status':'succeeded','content_candidates':candidate})
        except Exception as exc:
            if not self.closed:
                try:
                    current = self.bridge.snapshot(run_id, job_id)['job']
                    slots = current['provider_state']
                    if any(value.get('status') in {'reserved','running','unknown','outcome_unknown'} for value in slots.values()):
                        inputs = slots.get('inputs', {})
                        if inputs.get('status') not in {'unknown','outcome_unknown'}:
                            self.bridge.update_slot(run_id, job_id, 'inputs', {'status':'unknown','error':'CONTENT_OUTCOME_UNKNOWN'})
                    safe_codes = {'MEDIA_INPUT_MISSING','MEDIA_INPUT_INVALID','MEDIA_OFFLINE','MEDIA_UNAVAILABLE','MEDIA_CAPABILITY_MISSING',
                                  'MEDIA_PRODUCT_KIND_MISSING','MEDIA_BUDGET_EXHAUSTED','REQUEST_CONFLICT','CONTENT_RESTART_UNKNOWN',
                                  'MEDIA_OUTCOME_UNKNOWN','MEDIA_SUBMIT_UNKNOWN','MEDIA_JOB_FAILED','CLAIM_INVALID'}
                    code = getattr(exc, 'code', None)
                    self.bridge.complete(run_id, job_id, {'expected_job_version':current['version'],'status':'failed',
                        'error_code':code if code in safe_codes else 'CONTENT_WORKER_FAILED'})
                except Exception:
                    # A stale/published job has lost authority to change the draft.
                    pass
        finally:
            if heartbeat:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
            self.tasks.discard(task)
