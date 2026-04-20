# governor_v4/loader.py
"""Load machines from JSON."""

import json

from governor_v4.config import (
    NodeConfig, EdgeConfig, EvidenceContract, CaptureRule, MachineConfig,
)


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

    return MachineConfig(
        name=data["name"],
        description=data.get("description", ""),
        nodes=nodes,
        edges=edges,
    )


def _parse_nodes(raw: list[dict]) -> list[NodeConfig]:
    nodes = []
    seen = set()
    for d in raw:
        name = d["name"]
        if name in seen:
            raise ValueError(f"duplicate node: {name}")
        seen.add(name)
        capture = [
            CaptureRule(tool_pattern=c["tool_pattern"], evidence_type=c["evidence_type"])
            for c in d.get("capture", [])
        ]
        nodes.append(NodeConfig(
            name=name,
            initial=d.get("initial", False),
            blocked_tools=d.get("blocked_tools", []),
            allowed_exceptions=d.get("allowed_exceptions", []),
            capture=capture,
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

        contract_raw = d.get("evidence_contract")
        contract = None
        if contract_raw:
            contract = EvidenceContract(
                required_type=contract_raw["required_type"],
                gate=contract_raw["gate"],
            )

        edges.append(EdgeConfig(from_state=from_s, to_state=to_s, evidence_contract=contract))
    return edges
