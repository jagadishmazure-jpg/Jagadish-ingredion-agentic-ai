import { APIRequestContext, APIResponse } from '@playwright/test';

/**
 * Typed API client for the agent service.
 * Keeps HTTP mechanics out of the specs; specs assert business outcomes.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface ScenarioSummary {
  id: string;
  formula_id: string;
  target_claims: string[];
  region: string;
}

export interface ReformulateBody {
  scenario?: string;
  formula_id?: string;
  target_claims?: string[];
  region?: string;
  live?: boolean;
}

export interface AgentRunBody {
  message?: string;
  formula_id?: string;
  target_claims?: string[];
  region?: string;
  live?: boolean;
}

async function json<T>(res: APIResponse): Promise<T> {
  return (await res.json()) as T;
}

export async function getHealth(ctx: APIRequestContext): Promise<APIResponse> {
  return ctx.get('/api/health');
}

export async function getScenarios(ctx: APIRequestContext): Promise<APIResponse> {
  return ctx.get('/api/scenarios');
}

export async function getAgentCards(ctx: APIRequestContext): Promise<APIResponse> {
  return ctx.get('/api/agent-cards');
}

export async function getWellKnownAgent(ctx: APIRequestContext): Promise<APIResponse> {
  return ctx.get('/.well-known/agent.json');
}

export async function postReformulate(
  ctx: APIRequestContext,
  body: ReformulateBody,
  headers: Record<string, string> = {},
): Promise<APIResponse> {
  return ctx.post('/api/reformulate', { data: body, headers });
}

export async function postAgentRun(
  ctx: APIRequestContext,
  agent: string,
  body: AgentRunBody,
  headers: Record<string, string> = {},
): Promise<APIResponse> {
  return ctx.post(`/api/agents/${agent}/run`, { data: body, headers });
}

export async function getOpenApi(ctx: APIRequestContext): Promise<APIResponse> {
  return ctx.get('/openapi.json');
}

/** Measure elapsed ms around an API call. */
export async function timed<T>(
  fn: () => Promise<APIResponse>,
): Promise<{ res: APIResponse; ms: number }> {
  const start = Date.now();
  const res = await fn();
  return { res, ms: Date.now() - start };
}
