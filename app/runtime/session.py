"""Trạng thái một phiên, không chia sẻ rules giữa các run."""

from dataclasses import dataclass, field
from threading import RLock
from uuid import uuid4
from app.core.paths import RUNS_DIR
from app.domain.models.events import Event
from app.domain.models.shops import ShopPrivate, ShopPublic, SellerPersona
from app.domain.models.packages import ActivePackage
from app.infrastructure.eventlog import EventLog
from app.infrastructure.store import MemoryStore
from app.simulation.world import load_world


@dataclass
class ShopState:
    public: ShopPublic
    private: ShopPrivate
    persona: SellerPersona
    active: ActivePackage | None = None
    cooldown_until: int = 0
    metrics: dict = field(default_factory=dict)


@dataclass
class Session:
    run_id: str
    settings: object
    world: object
    states: dict[str, ShopState]
    store: MemoryStore
    log: EventLog
    llm: object = None
    memory: object = None
    content: object = None
    market: object = None
    day: int = 1
    step: str = 'idle'
    interactive: bool = True
    brief: object = None
    pending_card: object = None
    approved_card_id: str | None = None
    content_draft: object = None
    last_night: object = None
    negotiation_attempt: int = 0
    seller_negotiations: dict = field(default_factory=dict)
    active_negotiations: dict = field(default_factory=dict)
    last_agent_source: str = "offline"
    rules_version: int = 1
    forecast_snapshots: dict = field(default_factory=dict)
    settled_days: set = field(default_factory=set)
    night_receipts: dict = field(default_factory=dict)
    night_summaries: dict = field(default_factory=dict)
    apply_receipts: dict = field(default_factory=dict)
    phase_busy: bool = False
    lock: RLock = field(default_factory=RLock)
    original_public: dict = field(default_factory=dict)
    knowledge_receipts: dict = field(default_factory=dict)

    @property
    def knowledge_revision(self):
        return self.store.metadata(self.run_id)[0]

    @property
    def memory_cursor(self):
        return self.store.metadata(self.run_id)[1]

    @property
    def live_calls_left(self):
        return self.llm.remaining_calls if self.llm else 0

    @classmethod
    def new(cls, settings, memory_enabled=True, *, seed=None, content=None, market=None,
            llm=None, store=None, log=None):
        from app.infrastructure.llm import LLMClient
        from app.memory.gateway import MemoryGateway
        run_id = uuid4().hex
        world = load_world()
        states = {sid: ShopState(item.public.model_copy(deep=True), item.private.model_copy(deep=True),
                                 item.persona.model_copy(deep=True)) for sid, item in world.shops.items()}
        if seed is not None:
            settings = settings.model_copy(update={'seed': seed}, deep=True)
        session = cls(run_id=run_id, settings=settings, world=world, states=states,
                      store=store or MemoryStore(), log=log or EventLog(RUNS_DIR / run_id / 'events.jsonl'),
                      llm=llm or LLMClient(settings), content=content, market=market,
                      original_public={sid: state.public.model_copy(deep=True) for sid, state in states.items()})
        session.memory = MemoryGateway(session.store, memory_enabled, log=session.log, run_id=run_id, session=session)
        return session
