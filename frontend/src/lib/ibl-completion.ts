/** Shared envelope policy: execution, audit history and required duties are separate. */
export interface CompletionObligation {
  id: string;
  predicate: string;
  sources: { action: string; targets: Record<string, string> }[];
  required?: boolean;
  scope?: (string | number)[];
}
export type CompletionStatus = 'satisfied' | 'unsatisfied' | 'undetermined';
export { completionStatus, iblOutcomeError } from '../../../backend/static/app_render_core.js';
