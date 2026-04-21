"""Tests for shared CLI dispatch helpers in __main__.py."""

import json
import pytest
from unittest.mock import patch
from io import StringIO

from governor_v4.__main__ import parse_session, read_stdin


class TestParseSession:
    def test_extracts_session_id(self):
        assert parse_session(["--session", "abc123"]) == "abc123"

    def test_session_in_middle(self):
        assert parse_session(["--foo", "--session", "xyz", "--bar"]) == "xyz"

    def test_missing_session_exits(self):
        with pytest.raises(SystemExit):
            parse_session(["--other", "value"])

    def test_session_at_end_without_value_exits(self):
        with pytest.raises(SystemExit):
            parse_session(["--session"])


class TestReadStdin:
    def test_reads_valid_json(self):
        with patch("sys.stdin", StringIO('{"tool_name": "Bash"}')):
            result = read_stdin()
        assert result == {"tool_name": "Bash"}

    def test_returns_none_on_invalid_json(self):
        with patch("sys.stdin", StringIO("not json")):
            assert read_stdin() is None

    def test_returns_none_on_empty(self):
        with patch("sys.stdin", StringIO("")):
            assert read_stdin() is None
