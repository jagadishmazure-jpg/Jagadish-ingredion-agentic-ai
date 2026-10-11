# Hybrid Data Plane

Enterprise data no longer lives in one place. AI workloads now run across
public cloud, private cloud, on-premises, edge, and sovereign environments —
and 97% of enterprises move data between environments monthly (Cloudera,
*The Great AI Re-Architecture*, 2026). The same survey found 95% of
organizations delayed or canceled AI projects over governance, compliance,
or regulatory issues, and 66% moved AI workloads back from public cloud to
on-premises or private cloud in the last year.

The hybrid data plane implements the report's central thesis —
**bring AI to the data, wherever it lives** — as code:

1. **Environments** (`ingredion_ai/datalayer/hybrid/environments.py`):
   every place data can live or a workload can run has a kind
   (`public_cloud | private_cloud | on_prem | edge | sovereign`), a region,
   and a residency zone (`EU | US | APAC`).
2. **Placement** (`placement.py`): each dataset is tagged with the
   environments it physically lives in and a residency class
   (`PUBLIC | CONFIDENTIAL | RESTRICTED | SOVEREIGN`). SOVEREIGN datasets
   must live only in sovereign environments of a single zone; RESTRICTED
   datasets must stay in a single zone. Misplacement is rejected at
   registration — a misplaced dataset never enters the plane.
3. **Traveling policies** (`policies.py`): the policy is attached to the
   dataset and evaluated at query time against the *requesting*
   environment, never at registration. Wherever the dataset — or a request
   for it — goes, the same rules apply:
   - PUBLIC: anywhere.
   - CONFIDENTIAL: never from edge.
   - RESTRICTED: never outside its residency zone.
   - SOVEREIGN: only from a sovereign environment in the same zone.
4. **Workload routing** (`routing.py`): `route_workload()` picks where an
   AI workload runs. Policy-violating environments are eliminated first —
   a workload can never be routed somewhere its data is not allowed —
   survivors are scored by data locality, ties break toward the cheapest
   environment kind. Every rejection carries its reason.
5. **Movement log** (`movement.py`): every cross-environment data movement
   runs the policy check first; violations are denied and recorded.
   Approved and denied moves are hash-chained, so the full movement
   history is auditable.

## Worked example

EU customer data (`customers_eu`, RESTRICTED to zone EU, living in
`onprem-fra`) is requested by an agent running in `azure-use` (US):

```python
engine.check_access("customers_eu", "azure-use")
# (False, "'customers_eu' is RESTRICTED to zone EU: query denied
#          from 'azure-use' (zone US)")
```

Instead of moving the data to the workload, the workload is routed to the
data:

```python
route_workload(["customers_eu"], ["azure-use", "azure-weu", "onprem-fra"], ...)
# {"environment_id": "onprem-fra",
#  "rationale": ["routed to onprem-fra: holds 1/1 required datasets locally
#                 (bring AI to the data)"], ...}
```

And a denied movement is recorded, not silently dropped:

```python
log.request_move("customers_eu", "onprem-fra", "azure-use", actor="etl-nightly")
# {"approved": False, "reason": "'customers_eu' is RESTRICTED to zone EU: ..."}
```

## Production path

- Environments: back with real cloud/on-prem inventory (CMDB, Azure Arc).
- Placement: reconcile against actual storage (OneLake, Blob, on-prem NAS).
- Policies: enforce at the query gateway (MCP data server) so every agent
  request is checked, not just planned routes.
- Routing: feed the decision into the orchestrator's scheduler.
