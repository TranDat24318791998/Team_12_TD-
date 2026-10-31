import json
from pathlib import Path
from app.domain.models.tools import PublicContext, ShopContext
from app.domain.models.learning import PlatformMemoryView, ShopMemoryView, ContentMemoryView, LearningEvidence, MemoryUpdateBatch, KnowledgeCommit


def test_handoff_fixtures_are_valid_and_honestly_labelled():
    cases={'contracts/agents/public_context.json':PublicContext,'contracts/agents/shop_context.json':ShopContext,
           'contracts/knowledge/platform_view.json':PlatformMemoryView,'contracts/knowledge/shop_view.json':ShopMemoryView,
           'contracts/knowledge/content_view.json':ContentMemoryView,'contracts/knowledge/learning_evidence.json':LearningEvidence,
           'contracts/knowledge/night_batch.json':MemoryUpdateBatch,'contracts/knowledge/knowledge_commit.json':KnowledgeCommit}
    for path,model in cases.items():
        raw=json.loads(Path(path).read_text())
        assert raw['source']=='fixture'
        model.model_validate(raw['payload'])
    public=json.loads(Path('contracts/agents/public_context.json').read_text())
    assert 'unit_cost' not in json.dumps(public) and 'persona' not in json.dumps(public)
