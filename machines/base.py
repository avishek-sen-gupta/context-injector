"""Base class for state machines governed by the context-injector governor.

Subclasses define SOFTNESS, CONTEXT, and ALLOWED_TOOLS as class-level dicts.
The governor uses these to decide what action to take and which context to inject.
"""

from statemachine import StateMachine


class GovernedMachine(StateMachine):
    """Base class adding softness, context, and allowed-tools metadata."""

    SOFTNESS: dict[str, float] = {}
    CONTEXT: dict[str, list[str]] = {}
    ALLOWED_TOOLS: dict[str, list[str]] = {}
    BLOCKED_TOOLS: dict[str, list[str]] = {}
    PRECONDITIONS: dict[str, list[str]] = {}
    SESSION_INSTRUCTIONS: str = ""
    GUARDS: dict[str, list] = {}
    GATE_SOFTNESS: dict[str, float] = {}
    CHECK_STATES: dict[str, dict] = {}   # gate runs on entry, result picks transition

    def get_softness(self, transition_name: str) -> float:
        """Return the softness value for a transition. Defaults to 1.0."""
        return self.SOFTNESS.get(transition_name, 1.0)

    def get_context(self, state_name: str) -> list[str]:
        """Return context file patterns for a state. Defaults to []."""
        return self.CONTEXT.get(state_name, [])

    def get_allowed_tools(self, state_name: str) -> list[str] | None:
        """Return allowed tool patterns for a state. None if unconstrained."""
        return self.ALLOWED_TOOLS.get(state_name)

    def get_blocked_tools(self, state_name: str) -> list[str] | None:
        """Return blocked tool patterns for a state. None if nothing blocked."""
        return self.BLOCKED_TOOLS.get(state_name)

    def get_preconditions(self, transition_name: str) -> list[str]:
        """Return required tool patterns for a transition. Defaults to []."""
        return self.PRECONDITIONS.get(transition_name, [])

    def get_guards(self, transition_name: str) -> list:
        """Return gate classes registered for a transition. Defaults to []."""
        return self.GUARDS.get(transition_name, [])

    def get_gate_softness(self, gate_name: str) -> float:
        """Return the softness override for a gate. Defaults to 0.0 (strict)."""
        return self.GATE_SOFTNESS.get(gate_name, 0.0)

    @property
    def current_state_name(self) -> str:
        """Return the name of the current state."""
        return self.current_state_value

    @property
    def available_transition_names(self) -> list[str]:
        """Return names of transitions available from the current state."""
        state = self.states_map[self.current_state_value]
        return [t.event for t in state.transitions if t.source.id == state.id]
