"""Load machines from JSON."""

import json
from pathlib import Path
from governor_v3.config import NodeConfig, EdgeConfig, GateConfig, MachineConfig


def load_machine_from_json(source: str, from_file: bool = False) -> MachineConfig:
    """Parse JSON string or file into MachineConfig. Validates structure."""
    if from_file:
        with open(source) as f:
            data = json.load(f)
    else:
        data = json.loads(source)

    nodes = _parse_nodes(data.get("nodes", []))
    node_names = {n.name for n in nodes}
    edges = _parse_edges(data.get("edges", []), node_names)
    gates = _parse_gates(data.get("gates", []))

    return MachineConfig(
        name=data["name"],
        description=data.get("description", ""),
        nodes=nodes,
        edges=edges,
        gates=gates,
    )


def _parse_nodes(raw: list[dict]) -> list[NodeConfig]:
    nodes = []
    seen = set()
    for d in raw:
        name = d["name"]
        if name in seen:
            raise ValueError(f"duplicate node: {name}")
        seen.add(name)
        nodes.append(NodeConfig(
            name=name,
            initial=d.get("initial", False),
            action=d.get("action"),
            action_params=d.get("action_params", {}),
            blocked_tools=d.get("blocked_tools", []),
            allowed_exceptions=d.get("allowed_exceptions", []),
            auto_transition=d.get("auto_transition"),
        ))
    return nodes


def _parse_edges(raw: list[dict], node_names: set[str]) -> list[EdgeConfig]:
    edges = []
    for d in raw:
        from_s, to_s = d["from"], d["to"]
        if from_s not in node_names:
            raise ValueError(f"edge references nonexistent node: from {from_s}")
        if to_s not in node_names:
            raise ValueError(f"edge references nonexistent node: to {to_s}")
        edges.append(EdgeConfig(from_state=from_s, to_state=to_s, trigger=d["trigger"]))
    return edges


def _parse_gates(raw: list[dict]) -> list[GateConfig]:
    return [
        GateConfig(
            name=d["name"],
            applies_to=d.get("applies_to", []),
            trigger=d.get("trigger", "on_exit"),
            gate_names=d.get("gate_names", []),
            policy=d.get("policy", "strict"),
            routes=d.get("routes"),
            params=d.get("params", {}),
        )
        for d in raw
    ]
