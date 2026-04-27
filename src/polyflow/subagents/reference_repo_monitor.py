"""Reference repo monitor subagent.

Checks whether configured upstream repositories are present, pinned, and ready
for deterministic automation use. It never imports or executes upstream code.
"""

from __future__ import annotations

from pathlib import Path

from ..automation_sources import check_sources
from ..config import Policy
from ..logger import ImmutableLogger
from ..persistence import SQLiteStore


class ReferenceRepoMonitor:
    def __init__(
        self,
        *,
        policy: Policy,
        logger: ImmutableLogger,
        store: SQLiteStore | None = None,
        root: str | Path = ".",
    ) -> None:
        self.policy = policy
        self.logger = logger
        self.store = store
        self.root = Path(root)

    async def tick(self) -> None:
        statuses = check_sources(
            self.policy.automation.sources,
            root=self.root,
            require_pinned_commit=self.policy.automation.require_pinned_commits,
        )
        ready = sum(1 for status in statuses if status.ok)
        if self.store is not None:
            for status in statuses:
                self.store.upsert_automation_source(status.as_dict())

        self.logger.log(
            actor="reference_repo_monitor",
            action="check",
            payload={
                "ready": ready,
                "total": len(statuses),
                "sources": [status.as_dict() for status in statuses],
            },
        )
