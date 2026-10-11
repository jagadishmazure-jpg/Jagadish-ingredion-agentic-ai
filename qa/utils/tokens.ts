import { execFileSync } from 'child_process';
import { join } from 'path';

/**
 * Demo token minting. Tokens are synthetic JWTs minted by the service's own
 * CLI (`python -m ingredion_ai.service.mint_token`) — no secrets involved.
 * Each call uses a unique subject, which also gives every test its own
 * rate-limit budget (the limiter is keyed by token subject).
 */

const REPO_ROOT = join(__dirname, '..', '..');

export function mintToken(subject: string, scopes: string): string {
  const python = process.env.QA_PYTHON ?? 'python3';
  const out = execFileSync(
    python,
    ['-m', 'ingredion_ai.service.mint_token', '--subject', subject, '--scopes', scopes],
    { cwd: REPO_ROOT, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] },
  );
  const token = out.trim().split('\n').pop() ?? '';
  if (!token) throw new Error(`mint_token produced no token for subject ${subject}`);
  return token;
}

let counter = 0;

/** Unique subject prefix per test — isolates rate-limit budgets. */
export function uniqueSubject(prefix: string): string {
  return `${prefix}-${process.pid}-${Date.now()}-${counter++}`;
}

export const FULL_SCOPES = 'formulation:write,supply:read,esg:read,proposal:read';
export const READONLY_SCOPES = 'supply:read';
