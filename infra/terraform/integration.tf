# Azure integration services for the agentic platform (demo).
#
# Provisions: Service Bus (job queue + topic), Event Grid topic,
# Event Hubs (telemetry), Storage account + Consumption-plan Function App,
# and a Consumption Logic App for the approval workflow.
#
# Demo-cheap SKUs throughout (Basic/Consumption); production notes inline.
# No secrets in code — the Function App uses managed identity; connection
# strings are NOT stored here. `terraform` is not installed in this sandbox,
# so this HCL is carefully written but NOT `terraform validate`d — run a
# validate before the first apply.

# ---------------------------------------------------------------------------
# Service Bus: reformulation job queue + results topic (+DLQ on the queue)
# ---------------------------------------------------------------------------

resource "azurerm_servicebus_namespace" "jobs" {
  name                = "${local.name_prefix}-sb-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic" # demo: queues+topics; production -> Premium (VNet, sessions)
  tags                = local.common_tags
}

resource "azurerm_servicebus_queue" "reformulation_jobs" {
  name                                 = "reformulation-jobs"
  namespace_id                         = azurerm_servicebus_namespace.jobs.id
  max_delivery_count                   = 3 # poison -> DLQ after 3 deliveries
  dead_lettering_on_message_expiration = true
}

resource "azurerm_servicebus_topic" "job_results" {
  name         = "job-results"
  namespace_id = azurerm_servicebus_namespace.jobs.id
}

resource "azurerm_servicebus_subscription" "ui_updates" {
  name               = "ui-updates"
  topic_id           = azurerm_servicebus_topic.job_results.id
  max_delivery_count = 3
}

resource "azurerm_servicebus_subscription" "analytics_sink" {
  name               = "analytics-sink"
  topic_id           = azurerm_servicebus_topic.job_results.id
  max_delivery_count = 3
}

# ---------------------------------------------------------------------------
# Event Grid: domain-event fan-out (reformulation.completed, claim.validated)
# ---------------------------------------------------------------------------

resource "azurerm_eventgrid_topic" "domain_events" {
  name                = "${local.name_prefix}-egt-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags
  # production: input_schema = "CloudEventSchemaV1_0" + managed-identity
  # delivery; the platform already emits CloudEvents-shaped payloads.
}

# ---------------------------------------------------------------------------
# Event Hubs: high-volume run telemetry for dashboards
# ---------------------------------------------------------------------------

resource "azurerm_eventhub_namespace" "telemetry" {
  name                = "${local.name_prefix}-eh-${random_string.suffix.result}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic" # demo; production -> Standard (capture, longer retention)
  capacity            = 1
  tags                = local.common_tags
}

resource "azurerm_eventhub" "run_telemetry" {
  name                = "run-telemetry"
  namespace_name      = azurerm_eventhub_namespace.telemetry.name
  resource_group_name = azurerm_resource_group.main.name
  partition_count     = 2
  message_retention   = 1
}

# ---------------------------------------------------------------------------
# Functions: HTTP trigger (enqueue), Service Bus trigger (process),
# timer trigger (weekly ESG report). Consumption plan + storage.
# ---------------------------------------------------------------------------

resource "azurerm_storage_account" "functions" {
  name                     = "${var.prefix}${var.environment}func${random_string.suffix.result}"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  tags                     = local.common_tags
}

resource "azurerm_service_plan" "functions" {
  name                = "${local.name_prefix}-funcplan"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "Y1" # Consumption: pay-per-execution
  tags                = local.common_tags
}

resource "azurerm_linux_function_app" "agents" {
  name                       = "${local.name_prefix}-func-${random_string.suffix.result}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  service_plan_id            = azurerm_service_plan.functions.id
  storage_account_name       = azurerm_storage_account.functions.name
  storage_account_access_key = azurerm_storage_account.functions.primary_access_key
  tags                       = local.common_tags

  identity {
    type = "SystemAssigned" # -> RBAC to Service Bus / Event Hubs / Key Vault
  }

  site_config {
    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = {
    # Connection via managed identity in production (no secrets here):
    # SERVICEBUS_FQDN = azurerm_servicebus_namespace.jobs.name + ".servicebus.windows.net"
    SERVICEBUS_QUEUE                      = azurerm_servicebus_queue.reformulation_jobs.name
    EVENTGRID_TOPIC                       = azurerm_eventgrid_topic.domain_events.name
    EVENTHUB_NAME                         = azurerm_eventhub.run_telemetry.name
    AZURE_OPENAI_ENDPOINT                 = "@Microsoft.KeyVault(VaultName=${azurerm_key_vault.main.name};SecretName=azure-openai-endpoint)"
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
  }
}

# RBAC: Function App -> Service Bus data receiver/sender (no connection strings).
resource "azurerm_role_assignment" "func_sb_receiver" {
  scope                = azurerm_servicebus_namespace.jobs.id
  role_definition_name = "Azure Service Bus Data Receiver"
  principal_id         = azurerm_linux_function_app.agents.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_sb_sender" {
  scope                = azurerm_servicebus_namespace.jobs.id
  role_definition_name = "Azure Service Bus Data Sender"
  principal_id         = azurerm_linux_function_app.agents.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_eh_sender" {
  scope                = azurerm_eventhub_namespace.telemetry.id
  role_definition_name = "Azure Event Hubs Data Sender"
  principal_id         = azurerm_linux_function_app.agents.identity[0].principal_id
}

# ---------------------------------------------------------------------------
# Logic App (Consumption): human-approval workflow for reformulations.
# Definition checked in at infra/logicapps/reformulation-approval.json.
# ---------------------------------------------------------------------------

resource "azurerm_logic_app_workflow" "reformulation_approval" {
  name                = "${local.name_prefix}-approval"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.common_tags

  identity {
    type = "SystemAssigned"
  }

  # The workflow definition lives in infra/logicapps/reformulation-approval.json;
  # import it with the CLI after apply, or inline it here for a single-file deploy:
  #
  #   az logic workflow update -g <rg> -n <name> \
  #     --definition @infra/logicapps/reformulation-approval.json

  # Parameter definitions are JSON strings; values are plain strings.
  workflow_parameters = {
    agentApiBaseUrl = jsonencode({
      type         = "String"
      defaultValue = "https://<apim-gateway-host>/food-ingredients"
    })
  }

  parameters = {
    agentApiBaseUrl = "https://<apim-gateway-host>/food-ingredients"
  }
}
