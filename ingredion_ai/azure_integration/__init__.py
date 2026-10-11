"""Azure integration services for the agentic platform (demo).

Wraps the Azure messaging/eventing/integration surface the platform can
run against in production — Service Bus, Event Grid, Event Hubs, Azure
Functions triggers, and Logic Apps callbacks — behind small abstractions
with **offline in-memory fakes** so every test runs without credentials.

Production swap (one line each, documented per module):

- ``servicebus``  → ``azure-servicebus.ServiceBusClient`` (connection string
  or ``DefaultAzureCredential`` from Key Vault / managed identity)
- ``eventgrid``   → ``azure-eventgrid.EventGridPublisherClient``
- ``eventhub``    → ``azure-eventhub.EventHubProducerClient``
- ``functions``   → deploy the handlers in this module as an Azure
  Functions app (see ``function.json`` samples in docstrings)
- ``logicapps``   → import ``infra/logicapps/reformulation-approval.json``

Lifecycle events flow through :mod:`ingredion_ai.azure_integration.events`
(CloudEvents v1.0 shapes); the service pipeline emits them best-effort in
stage 8. All demo data is synthetic and fictional. Stdlib only.
"""

from ingredion_ai.azure_integration.events import (
    ANOMALY_FLAGGED,
    APPROVAL_GRANTED,
    APPROVAL_REQUESTED,
    CLAIM_VALIDATED,
    RUN_COMPLETED,
    RUN_FAILED,
    RUN_STARTED,
    CloudEvent,
    emit_lifecycle_event,
    get_lifecycle_publisher,
    make_event,
    set_lifecycle_publisher,
    validate_event,
)

__all__ = [
    "ANOMALY_FLAGGED",
    "APPROVAL_GRANTED",
    "APPROVAL_REQUESTED",
    "CLAIM_VALIDATED",
    "RUN_COMPLETED",
    "RUN_FAILED",
    "RUN_STARTED",
    "CloudEvent",
    "emit_lifecycle_event",
    "get_lifecycle_publisher",
    "make_event",
    "set_lifecycle_publisher",
    "validate_event",
]
