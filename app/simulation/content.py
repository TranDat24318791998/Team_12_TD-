"""Offline content worker using the same Content Agent and supplied source image."""

from app.agents.content import generate_content_from_context
from app.domain.models.learning import ContentMemoryView
from app.domain.models.tools import ContentContext


class OfflineContent:
    def __init__(self, bridge, settings, llm):
        self.bridge, self.settings, self.llm = bridge, settings, llm

    async def close(self):
        pass

    async def process_job(self, run_id, job_id):
        snapshot = self.bridge.snapshot(run_id,job_id)
        job, product = snapshot['job'], snapshot['product']
        self.bridge.heartbeat(run_id,job_id,job['version'])
        source_asset = next((a for a in snapshot['assets'] if a['asset_id'] == snapshot['content']['cover_asset_id']),None)
        if source_asset is None:
            raise ValueError('OFFLINE_SOURCE_ASSET_MISSING')
        facts = [item['text_vi'] for item in product['facts']['verified_claims']]
        context = ContentContext(shop_id=job['shop_id'],title=snapshot['content']['title'],
            description=snapshot['content']['description'],attributes=facts,images=[],
            fact_source_id=product['facts']['verified_claims'][0].get('source_reference','product:facts') if facts else 'product:facts',
            memory=ContentMemoryView(confirmed_style_notes=snapshot['rules']['content_style_notes'],
                                     rules_version=snapshot['rules_version'],preference_ids=[]),
            feedback_history=job['feedback_history'],card_id=snapshot['card']['card_id'],
            brief_version=snapshot['brief_version'],draft_version=job['attempt'])
        emit = lambda kind,data: self.bridge.emit(run_id,job_id,kind,data)
        result = generate_content_from_context(context,self.llm,emit,f'{run_id}:content:{job_id}:{job["attempt"]}')
        source = 'offline_simulated_placeholder' if 'placeholder' in source_asset['source_reference'] else 'offline_original_asset'
        images = [{'option':option,'status':'cached','asset_id':source_asset['asset_id'],'source':source} for option in 'ABC']
        current = self.bridge.snapshot(run_id,job_id)['job']
        return self.bridge.complete(run_id,job_id,{'expected_job_version':current['version'],'status':'succeeded','fallback_used':True,
            'content_candidates':{'title':result.value.title,'description':result.value.description,'images':images,
                'video':{'status':'failed','asset_id':None,'source':'offline','error':'OFFLINE_NO_VIDEO'},
                'feedback_history':job['feedback_history'],'style_notes':snapshot['rules']['content_style_notes'],
                'checks':result.value.checks}})
