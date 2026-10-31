"""Tool definitions bound to a server-selected role, run, shop and day."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from pydantic import BaseModel, Field
from app.core.paths import DATA_DIR
from app.domain.finance import breakeven_roas, loss_warning, max_voucher_for, profit_per_unit, stop_threshold
from app.domain.models.shops import StrictModel
from app.domain.models.packages import Package
from app.domain.models.metrics import Forecast
from app.domain.models.tools import (CampaignCatalogResult, CampaignRecord, ContentContext, FinancialResult,
    PackageCheck, PublicContext, RefereeContext, ShopContext, ShopPackageCheck)
from app.domain.validators import brief_side_check, clamp_to_platform, clamp_to_rules, platform_side_check, shop_side_check


ROLE_TOOLS = {
    'platform': {'get_public_context', 'read_memory', 'validate_platform_package', 'forecast_package', 'search_campaign_catalog'},
    'shop': {'get_public_context', 'get_shop_private_context', 'read_memory', 'evaluate_shop_package'},
    'referee': {'get_referee_context'},
    'content': {'get_content_context'},
    'learning': {'read_learning_evidence'},
}


class EmptyArgs(StrictModel):
    pass


class PackageArgs(StrictModel):
    package: Package


class CatalogArgs(StrictModel):
    query: str = Field(max_length=200)


@dataclass(frozen=True)
class BoundTool:
    args_schema: type[BaseModel]
    execute: Callable[[BaseModel], BaseModel]
    output_schema: type[BaseModel]
    visibility: Literal['public', 'shop_private'] = 'public'
    expected_package: Package | None = None
    required: bool = False


def bind_role_tools(session, role, shop_id, *, turns=(), proposal=None, brief=None,
                    public_check_codes=(), feedback_history=(), card_id=None,
                    draft_version=1, initial_propose=False, invocation_id=None):
    """Values captured here are never accepted from model tool arguments."""
    if role not in ROLE_TOOLS or shop_id not in session.states:
        raise ValueError('invalid role or shop')
    state = session.states[shop_id]
    scoped_brief = brief or session.brief
    if scoped_brief is None or scoped_brief.shop_id != shop_id:
        raise ValueError('missing scoped brief')
    fees = session.world.fees

    def public_context(_):
        active = state.active.package if state.active else None
        trend = session.world.trend
        return PublicContext(day=session.day, shop=state.public.model_copy(deep=True),
            brief=scoped_brief.model_copy(deep=True),
            trend_multiplier=round((1 + trend.get('daily_growth', .12)) ** min(session.day - 1, 6), 6),
            calendar_notes=[item['name'] for item in session.world.calendar], active_package=active)

    def private_context(_):
        return ShopContext(private=state.private.model_copy(deep=True), rules_version=session.rules_version)

    def memory(_):
        if role == 'platform':
            return session.memory.platform_view(shop_id, state.public.category, invocation_id=invocation_id)
        return session.memory.shop_view(shop_id, invocation_id=invocation_id)

    def validate_platform(args):
        pkg = args.package
        errors = platform_side_check(pkg, state.public) + brief_side_check(pkg, scoped_brief)
        values = pkg.model_dump()
        values['content_refresh'] = scoped_brief.content_refresh
        values['duration_days'] = scoped_brief.duration_days
        if not scoped_brief.allow_ads:
            values['ads_daily_budget'] = 0
        if scoped_brief.ads_daily_cap is not None:
            values['ads_daily_budget'] = min(values['ads_daily_budget'], scoped_brief.ads_daily_cap)
        if values['ads_daily_budget'] < 10000:
            values['ads_daily_budget'] = 0
            values['stop_roas_below'] = None
        corrected = clamp_to_platform(Package.model_validate(values), state.public, scoped_brief.duration_days)
        after = (platform_side_check(corrected, state.public) + brief_side_check(corrected, scoped_brief)) if corrected else errors
        changes = [field for field in Package.model_fields if corrected and getattr(corrected, field) != getattr(pkg, field)]
        return PackageCheck(input_package=pkg, corrected_package=corrected, violations_before=errors,
                            violations_after=after, ok=not errors, warnings=[], changes=changes)

    def evaluate_shop(args):
        pkg = args.package
        before = shop_side_check(pkg, state.public, state.private, fees)
        corrected = clamp_to_rules(pkg, state.public, state.private, fees)
        after = shop_side_check(corrected, state.public, state.private, fees) if corrected else before
        values = corrected or pkg
        be = breakeven_roas(state.public, state.private, values.voucher_pct, fees)
        threshold = stop_threshold(be)
        financials = FinancialResult(profit_per_unit=profit_per_unit(state.public, state.private, values.voucher_pct, fees),
            breakeven_roas=be if math.isfinite(be) else None,
            min_stop_threshold=threshold if math.isfinite(threshold) else None,
            max_voucher_pct=max_voucher_for(state.public, state.private, bool(values.ads_daily_budget), fees),
            reason=loss_warning(state.public, state.private, fees))
        changes = [field for field in Package.model_fields if corrected and getattr(corrected, field) != getattr(pkg, field)]
        return ShopPackageCheck(input_package=pkg, corrected_package=corrected, violations_before=before,
            violations_after=after, ok=not before, warnings=[financials.reason] if financials.reason else [],
            changes=changes, financials=financials)

    def forecast(args):
        if session.market is None:
            raise RuntimeError('forecast adapter unavailable')
        calibration = session.memory.get_calibration(state.public.category)
        return Forecast.model_validate(session.market.forecast_package(state.public, args.package, session.day,
                                                                        session.settings.seed, calibration))

    def search(args):
        raw = json.loads((DATA_DIR / 'campaigns.json').read_text(encoding='utf-8'))
        query = args.query.strip().casefold()
        items = [CampaignRecord.model_validate(item) for item in raw]
        items = [item for item in items if item.category == state.public.category and
                 item.valid_from_day <= session.day <= item.valid_to_day and state.public.stock >= item.min_stock and
                 (not query or query in (item.title_vi + ' ' + item.description_vi).casefold())]
        return CampaignCatalogResult(items=sorted(items, key=lambda item: item.campaign_id)[:5])

    def referee_context(_):
        return RefereeContext(brief=scoped_brief.model_copy(deep=True), turns=list(turns),
                              public_check_codes=list(public_check_codes))

    def content_context(_):
        card = session.pending_card
        selected_card_id = card_id or (card.card_id if card else '')
        if (not card or card.card_id != selected_card_id or card.shop_id != shop_id or
            card.brief_version != scoped_brief.version or session.approved_card_id != selected_card_id or
            type(draft_version) is not int or not 1 <= draft_version <= 3):
            raise ValueError('content requires approved card')
        return ContentContext(shop_id=shop_id, title=state.public.title, description=state.public.description,
            attributes=state.public.attributes, images=state.public.images, fact_source_id=f'seed:shop:{shop_id}',
            memory=session.memory.content_view(shop_id, invocation_id=invocation_id), feedback_history=list(feedback_history),
            card_id=selected_card_id, brief_version=scoped_brief.version, draft_version=draft_version)

    from app.domain.models.learning import LearningEvidence, PlatformMemoryView, ShopMemoryView
    memory_schema = PlatformMemoryView if role == 'platform' else ShopMemoryView
    all_tools = {
        'get_public_context': BoundTool(EmptyArgs, public_context, PublicContext),
        'get_shop_private_context': BoundTool(EmptyArgs, private_context, ShopContext, 'shop_private'),
        'read_memory': BoundTool(EmptyArgs, memory, memory_schema, 'shop_private' if role == 'shop' else 'public'),
        'validate_platform_package': BoundTool(PackageArgs, validate_platform, PackageCheck),
        'evaluate_shop_package': BoundTool(PackageArgs, evaluate_shop, ShopPackageCheck, 'shop_private', expected_package=proposal),
        'forecast_package': BoundTool(PackageArgs, forecast, Forecast),
        'search_campaign_catalog': BoundTool(CatalogArgs, search, CampaignCatalogResult, required=initial_propose),
        'get_referee_context': BoundTool(EmptyArgs, referee_context, RefereeContext),
        'get_content_context': BoundTool(EmptyArgs, content_context, ContentContext),
        'read_learning_evidence': BoundTool(EmptyArgs, lambda _: session.memory.read_learning_evidence(session.day), LearningEvidence),
    }
    return {name: tool for name, tool in all_tools.items() if name in ROLE_TOOLS[role]}
