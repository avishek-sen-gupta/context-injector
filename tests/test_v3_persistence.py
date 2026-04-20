import os
import pytest
from governor_v3.engine import GovernorV3
from governor_v3.loader import load_machine_from_json

TDD_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "machines", "tdd.json")


class TestMemoryPersistence:
    def test_state_survives_new_instance_same_store(self, tmp_path):
        """State persists when a new GovernorV3 is created with the same state_dir."""
        config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
        state_dir = str(tmp_path)

        gov1 = GovernorV3(config=config, session_id="s1", state_dir=state_dir)
        assert gov1.current_phase == "writing_tests"
        gov1.trigger("pytest_fail")
        assert gov1.current_phase == "fixing_tests"

        # New instance, same state_dir and session_id
        gov2 = GovernorV3(config=config, session_id="s1", state_dir=state_dir)
        assert gov2.current_phase == "fixing_tests"

    def test_different_sessions_are_isolated(self, tmp_path):
        """Different session_ids have independent state."""
        config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
        state_dir = str(tmp_path)

        gov1 = GovernorV3(config=config, session_id="s1", state_dir=state_dir)
        gov1.trigger("pytest_fail")

        gov2 = GovernorV3(config=config, session_id="s2", state_dir=state_dir)
        assert gov2.current_phase == "writing_tests"  # fresh session

    def test_state_file_created(self, tmp_path):
        """A state file is written to state_dir."""
        config = load_machine_from_json(TDD_JSON_PATH, from_file=True)
        state_dir = str(tmp_path)

        gov = GovernorV3(config=config, session_id="s1", state_dir=state_dir)
        gov.trigger("pytest_fail")

        # Should have created a state file
        files = os.listdir(state_dir)
        assert len(files) > 0
