"""Evidence locker: tamper-proof store of captured tool outputs."""

import hashlib
import json
import os
import time


class EvidenceLocker:
    """Per-session key-value store of captured tool outputs.

    Populated by PostToolUse hook. Read by gates during transition validation.
    The agent receives keys via additionalContext but cannot modify entries.
    """

    def __init__(self, state_dir: str, session_id: str):
        self._state_dir = state_dir
        self._session_id = session_id
        self._entries: dict[str, dict] = self._load()

    def _file_path(self) -> str:
        return os.path.join(self._state_dir, f"{self._session_id}_evidence.json")

    def _load(self) -> dict:
        path = self._file_path()
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        return {}

    def _save(self):
        dir_path = os.path.dirname(self._file_path()) or "."
        os.makedirs(dir_path, exist_ok=True)
        with open(self._file_path(), "w") as f:
            json.dump(self._entries, f)

    def _generate_key(self, command: str) -> str:
        raw = f"{time.time()}:{command}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:6]
        return f"evt_{h}"

    def store(
        self,
        evidence_type: str,
        tool_name: str,
        command: str,
        output: str,
        exit_code: int | None = None,
    ) -> str:
        """Store a captured tool output. Returns the evidence key."""
        key = self._generate_key(command)
        self._entries[key] = {
            "type": evidence_type,
            "tool_name": tool_name,
            "command": command,
            "output": output,
            "exit_code": exit_code,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._save()
        return key

    def retrieve(self, key: str) -> dict | None:
        """Retrieve an evidence entry by key. Returns None if not found."""
        return self._entries.get(key)

    def keys(self) -> list[str]:
        """List all stored evidence keys."""
        return list(self._entries.keys())
