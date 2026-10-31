"""Nạp seed độc lập với workflow và provider."""

import json
from dataclasses import dataclass
from pathlib import Path
from app.core.paths import DATA_DIR
from app.domain.models.shops import FeeConfig, SellerPersona, ShopPrivate, ShopPublic


@dataclass
class SeedShop:
    public: ShopPublic
    private: ShopPrivate
    persona: SellerPersona


@dataclass
class World:
    shops: dict[str, SeedShop]
    trend: dict
    calendar: list[dict]
    fees: FeeConfig
    start_date: str


def load_world(path: str | Path = DATA_DIR / "seed.json") -> World:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    shops = {}
    for row in raw["shops"]:
        item = SeedShop(ShopPublic.model_validate(row["public"]),
                        ShopPrivate.model_validate(row["private"]),
                        SellerPersona.model_validate(row["persona"]))
        shops[item.public.shop_id] = item
    return World(shops, raw["trend"], raw["calendar"], FeeConfig.model_validate(raw["fees"]), raw["start_date"])
