# tests/test_tracer.py
import sys

from tracer import trace_context


def test_trace_context_captures_lines():
    """trace_context yields a CallTree that records executed lines."""

    def sample():
        x = 1
        y = 2
        return x + y

    with trace_context() as tree:
        sample()

    assert len(tree.roots) > 0
    assert any(root["func"] == "sample" for root in tree.roots)


def test_trace_context_stops_tracing_after_exit():
    """After exiting the context, tracing is off."""

    with trace_context() as tree:
        pass

    assert sys.gettrace() is None


def test_trace_context_stops_on_exception():
    """Tracing is stopped even if the body raises."""

    try:
        with trace_context() as tree:
            raise ValueError("boom")
    except ValueError:
        pass

    assert sys.gettrace() is None
