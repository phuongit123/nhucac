"""Registry adapter: tra cứu nền tảng theo URL, mở rộng dễ dàng.

Để thêm nền tảng mới: tạo class kế thừa BaseAdapter trong platforms.py
(hoặc file riêng) rồi gọi registry.register(MyAdapter()).
"""
from __future__ import annotations

from backend.adapters.base import BaseAdapter
from backend.adapters.platforms import ADAPTERS
from backend.models.schemas import PlatformInfo


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, BaseAdapter] = {}
        self._generic: BaseAdapter | None = None

    def register(self, adapter: BaseAdapter, *, replace: bool = False) -> None:
        if not adapter.key:
            raise ValueError("Adapter phải có key")
        if adapter.key in self._adapters and not replace:
            raise ValueError(f"Trùng lặp adapter key: {adapter.key}")
        self._adapters[adapter.key] = adapter
        if getattr(adapter, "relies_on_generic", False):
            self._generic = adapter

    def find(self, url: str) -> BaseAdapter | None:
        """Trả về adapter đặc thù đầu tiên khớp host; KHÔNG trả generic ở đây."""
        for ad in self._adapters.values():
            if ad is self._generic:
                continue
            if ad.can_handle(url):
                return ad
        return None

    def resolve(self, url: str) -> tuple[BaseAdapter | None, bool]:
        """Trả (adapter, is_generic). Nếu không có adapter đặc thù → generic fallback."""
        specific = self.find(url)
        if specific is not None:
            return specific, False
        if self._generic is not None:
            return self._generic, True
        return None, False

    def get(self, key: str) -> BaseAdapter | None:
        return self._adapters.get(key)

    def all(self) -> list[BaseAdapter]:
        return list(self._adapters.values())

    def platform_infos(self) -> list[PlatformInfo]:
        return [a.get_capabilities() for a in self._adapters.values()]


registry = AdapterRegistry()
for _a in ADAPTERS:
    registry.register(_a)
