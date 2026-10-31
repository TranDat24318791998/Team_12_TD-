"""Gắn dependency theo phiên; member API có thể dùng cùng interface."""

from app.runtime.session import Session


class SessionManager:
    def __init__(self, settings, *, content_factory=None, market=None, llm_factory=None, simulation_days=2):
        self.settings = settings
        self.content_factory = content_factory
        self.market = market
        self.llm_factory = llm_factory
        self.simulation_days = simulation_days
        self.current = None

    def reset(self, memory_enabled=True, seed=42):
        llm = self.llm_factory(self.settings) if self.llm_factory else None
        self.current = Session.new(self.settings, memory_enabled=memory_enabled, seed=seed, market=self.market, llm=llm, simulation_days=self.simulation_days)
        if self.content_factory:
            self.current.content = self.content_factory(self.current)
        return self.current
