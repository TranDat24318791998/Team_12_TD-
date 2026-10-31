"""Compose checked-in role guidance with its fixed base prompt."""
from pathlib import Path

_ALLOWED = {'platform_offer', 'platform_renew', 'shop_negotiate', 'content_brief'}


def compose_base_text(skill_id, core_text):
    if skill_id not in _ALLOWED:
        raise ValueError('UNKNOWN_BASE_SKILL')
    text = (Path(__file__).with_name('base_skills') / f'{skill_id}.md').read_text(encoding='utf-8').strip()
    return f'{core_text}\n\n{text}'
