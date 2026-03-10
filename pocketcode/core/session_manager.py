from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from pocketcode.core.resource_roots import primary_resource_root

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_title() -> str:
    return datetime.now(timezone.utc).strftime("Session %Y-%m-%d %H:%M UTC")


@dataclass
class SessionTranscriptEntry:
    entry_id: str
    timestamp: str
    role: str
    content: str
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "role": self.role,
            "content": self.content,
            "run_id": self.run_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "SessionTranscriptEntry":
        return cls(
            entry_id=str(raw.get("entry_id") or uuid4().hex),
            timestamp=str(raw.get("timestamp") or _utc_now_iso()),
            role=str(raw.get("role") or "system"),
            content=str(raw.get("content") or ""),
            run_id=str(raw.get("run_id")) if raw.get("run_id") is not None else None,
            metadata=dict(raw.get("metadata") or {}),
        )


@dataclass
class SavedSession:
    session_id: str
    title: str
    created_at: str
    updated_at: str
    workspace_root: str
    active_agent: str | None = None
    active_profile: str | None = None
    active_mode: str | None = None
    enabled_skills: list[str] = field(default_factory=list)
    global_llm_profile: str | None = None
    session_global_skills_override: list[str] = field(default_factory=list)
    session_profile_overrides: dict[str, Any] = field(default_factory=dict)
    session_confirmation_overrides: dict[str, Any] = field(default_factory=dict)
    debugger_breakpoints: list[str] = field(default_factory=list)
    transcript: list[SessionTranscriptEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "workspace_root": self.workspace_root,
            "active_agent": self.active_agent,
            "active_profile": self.active_profile,
            "active_mode": self.active_mode,
            "enabled_skills": list(self.enabled_skills),
            "global_llm_profile": self.global_llm_profile,
            "session_global_skills_override": list(self.session_global_skills_override),
            "session_profile_overrides": dict(self.session_profile_overrides),
            "session_confirmation_overrides": dict(self.session_confirmation_overrides),
            "debugger_breakpoints": list(self.debugger_breakpoints),
            "transcript": [entry.as_dict() for entry in self.transcript],
        }

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "SavedSession":
        transcript_items = raw.get("transcript") or []
        transcript = [
            SessionTranscriptEntry.from_raw(item)
            for item in transcript_items
            if isinstance(item, dict)
        ]
        return cls(
            session_id=str(raw.get("session_id") or uuid4().hex),
            title=str(raw.get("title") or _default_title()),
            created_at=str(raw.get("created_at") or _utc_now_iso()),
            updated_at=str(raw.get("updated_at") or _utc_now_iso()),
            workspace_root=str(raw.get("workspace_root") or ""),
            active_agent=str(raw.get("active_agent")) if raw.get("active_agent") else None,
            active_profile=str(raw.get("active_profile")) if raw.get("active_profile") else None,
            active_mode=str(raw.get("active_mode")) if raw.get("active_mode") else None,
            enabled_skills=[str(item) for item in raw.get("enabled_skills") or []],
            global_llm_profile=(
                str(raw.get("global_llm_profile"))
                if raw.get("global_llm_profile")
                else None
            ),
            session_global_skills_override=[str(item) for item in raw.get("session_global_skills_override") or []],
            session_profile_overrides=dict(raw.get("session_profile_overrides") or {}),
            session_confirmation_overrides=dict(raw.get("session_confirmation_overrides") or {}),
            debugger_breakpoints=[str(item) for item in raw.get("debugger_breakpoints") or []],
            transcript=transcript,
        )


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    title: str
    updated_at: str
    created_at: str
    transcript_entries: int
    debugger_breakpoint_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "updated_at": self.updated_at,
            "created_at": self.created_at,
            "transcript_entries": self.transcript_entries,
            "debugger_breakpoint_count": self.debugger_breakpoint_count,
        }


class SessionManager:
    def __init__(self, workspace_root: str | Path):
        self._workspace_root = Path(workspace_root).resolve()
        self._storage_dir = primary_resource_root(self._workspace_root).path / "state" / "sessions"

    @property
    def storage_dir(self) -> Path:
        return self._storage_dir

    def create_session(self, *, title: str | None = None, state: dict[str, Any] | None = None) -> SavedSession:
        payload = dict(state or {})
        timestamp = _utc_now_iso()
        record = SavedSession(
            session_id=uuid4().hex,
            title=str(title or payload.pop("title", "") or _default_title()),
            created_at=timestamp,
            updated_at=timestamp,
            workspace_root=str(self._workspace_root),
            active_agent=payload.get("active_agent"),
            active_profile=payload.get("active_profile"),
            active_mode=payload.get("active_mode"),
            enabled_skills=[str(item) for item in payload.get("enabled_skills") or []],
            global_llm_profile=payload.get("global_llm_profile"),
            session_global_skills_override=[str(item) for item in payload.get("session_global_skills_override") or []],
            session_profile_overrides=dict(payload.get("session_profile_overrides") or {}),
            session_confirmation_overrides=dict(payload.get("session_confirmation_overrides") or {}),
            debugger_breakpoints=[str(item) for item in payload.get("debugger_breakpoints") or []],
            transcript=[
                SessionTranscriptEntry.from_raw(item)
                for item in payload.get("transcript") or []
                if isinstance(item, dict)
            ],
        )
        return self.save_session(record)

    def save_session(self, record: SavedSession) -> SavedSession:
        record.updated_at = _utc_now_iso()
        path = self._session_file_path(record.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record.as_dict(), indent=2, sort_keys=False), encoding="utf-8")
        return record

    def load_session(self, session_id: str) -> SavedSession:
        path = self._session_file_path(session_id)
        raw = json.loads(path.read_text(encoding="utf-8"))
        record = SavedSession.from_raw(raw)
        if Path(record.workspace_root).resolve() != self._workspace_root:
            raise ValueError(f"Session '{session_id}' does not belong to this workspace.")
        return record

    def session_exists(self, session_id: str) -> bool:
        return self._session_file_path(session_id).exists()

    def list_sessions(self) -> list[SavedSession]:
        records: list[SavedSession] = []
        if not self._storage_dir.exists():
            return records
        for path in sorted(self._storage_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                record = SavedSession.from_raw(raw)
            except Exception as exc:
                logger.warning("Skipping unreadable session file '%s': %s", path, exc)
                continue
            if Path(record.workspace_root).resolve() != self._workspace_root:
                continue
            records.append(record)
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return records

    def list_session_summaries(self) -> list[SessionSummary]:
        return [self._build_summary(record) for record in self.list_sessions()]

    def update_session(self, session_id: str, **updates: Any) -> SavedSession:
        record = self.load_session(session_id)
        for field_name, value in updates.items():
            if not hasattr(record, field_name):
                continue
            setattr(record, field_name, value)
        return self.save_session(record)

    def append_transcript_entry(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SavedSession:
        record = self.load_session(session_id)
        text = str(content or "").strip()
        if not text:
            return record
        record.transcript.append(
            SessionTranscriptEntry(
                entry_id=uuid4().hex,
                timestamp=_utc_now_iso(),
                role=str(role or "system"),
                content=text,
                run_id=str(run_id) if run_id else None,
                metadata=dict(metadata or {}),
            )
        )
        return self.save_session(record)

    def delete_session(self, session_id: str) -> bool:
        path = self._session_file_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def clear_sessions(self, *, exclude_ids: Iterable[str] | None = None) -> int:
        excluded = {str(item) for item in (exclude_ids or [])}
        removed = 0
        for record in self.list_sessions():
            if record.session_id in excluded:
                continue
            if self.delete_session(record.session_id):
                removed += 1
        return removed

    def _session_file_path(self, session_id: str) -> Path:
        clean_id = str(session_id).strip()
        if not clean_id:
            raise ValueError("Session id cannot be empty.")
        return self._storage_dir / f"{clean_id}.json"

    def _build_summary(self, record: SavedSession) -> SessionSummary:
        return SessionSummary(
            session_id=record.session_id,
            title=record.title,
            updated_at=record.updated_at,
            created_at=record.created_at,
            transcript_entries=len(record.transcript),
            debugger_breakpoint_count=len(record.debugger_breakpoints),
        )
