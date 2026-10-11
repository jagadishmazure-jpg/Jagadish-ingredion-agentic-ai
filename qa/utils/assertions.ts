import { expect as baseExpect } from '@playwright/test';

/**
 * Custom assertion matchers via expect.extend().
 * Example: toBeValidReformulationResponse() validates the business shape
 * of a POST /api/reformulate response body in one readable assertion.
 */

interface ReformulationLike {
  session_id?: unknown;
  elapsed_ms?: unknown;
  blackboard?: unknown;
  scenario?: unknown;
}

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace PlaywrightTest {
    interface Matchers<R> {
      toBeValidReformulationResponse(): R;
    }
  }
}

export {};

export const expect = baseExpect.extend({
  toBeValidReformulationResponse(received: unknown) {
    const body = received as ReformulationLike;
    const pass =
      typeof body === 'object' &&
      body !== null &&
      typeof body.session_id === 'string' &&
      body.session_id.length > 0 &&
      typeof body.elapsed_ms === 'number' &&
      typeof body.blackboard === 'object' &&
      body.blackboard !== null;

    if (pass) {
      return {
        message: () => 'expected body not to be a valid reformulation response',
        pass: true,
      };
    }
    return {
      message: () =>
        `expected a valid reformulation response (session_id: string, elapsed_ms: number, blackboard: object), ` +
        `received: ${JSON.stringify(received)?.slice(0, 300)}`,
      pass: false,
    };
  },
});
