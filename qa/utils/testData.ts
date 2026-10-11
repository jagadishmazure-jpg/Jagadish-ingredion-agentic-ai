/**
 * Static test data lives outside test logic.
 * Secrets are NEVER here — tokens come from env (QA_TOKEN, ...).
 */
export const DEFAULT_SCENARIO = 'sweet_bakery_cake';
export const UNKNOWN_SCENARIO = 'does_not_exist_xyz';

export const AGENTS = [
  'rd_formulation',
  'supply_chain',
  'esg',
  'customer_advisor',
] as const;

export const REQUIRED_SCOPES: Record<string, string> = {
  rd_formulation: 'formulation:write',
  supply_chain: 'supply:read',
  esg: 'esg:read',
  customer_advisor: 'proposal:read',
};

export const EXPECTED_HEALTH_FIELDS = ['status', 'service', 'version'] as const;
