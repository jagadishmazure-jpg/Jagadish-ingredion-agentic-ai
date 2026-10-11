"""End-to-end reformulation workflow on Microsoft Agent Framework 1.0.

Topology: the R&D formulation agent runs first (sequential 6-step tool
phase), then fans out concurrently to the supply-chain, ESG, and customer
advisor agents. All agents share one blackboard dict through their tools,
so the fan-out is deterministic (disjoint blackboard keys).
"""

from __future__ import annotations

from typing import Dict

from agent_framework import Agent, Workflow, WorkflowBuilder


def build_reformulation_workflow(agents: Dict[str, Agent]) -> Workflow:
    """Build the reformulation workflow from framework agents."""
    rd_agent = agents["rd_formulation"]
    supporters = [
        agents["supply_chain"],
        agents["esg"],
        agents["customer_advisor"],
    ]
    builder = WorkflowBuilder(start_executor=rd_agent)
    builder.add_fan_out_edges(rd_agent, supporters)
    return builder.build()
