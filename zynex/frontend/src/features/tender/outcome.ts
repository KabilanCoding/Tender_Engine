/**
 * One wording for a finished eligibility run, used everywhere a verdict is shown:
 *   Eligible            every must-have met
 *   Not eligible        at least one must-have not met
 *   Partially eligible  some requirements met, the rest need company data or a person to check
 *   Cannot confirm yet  nothing could be confirmed yet (or the run did not finish)
 */
export type Outcome = 'eligible' | 'not_eligible' | 'partial' | 'unconfirmed'

export const OUTCOME: Record<Outcome, { label: string; chip: string; color: string }> = {
  eligible: { label: 'Eligible', chip: 'is-ok', color: 'var(--s-ok)' },
  not_eligible: { label: 'Not eligible', chip: 'is-bad', color: 'var(--s-bad)' },
  partial: { label: 'Partially eligible', chip: 'is-warn', color: 'var(--s-warn)' },
  unconfirmed: { label: 'Cannot confirm yet', chip: 'is-review', color: 'var(--s-review)' },
}

export function outcomeOf(verdict?: string | null, met?: number | null): Outcome {
  if (verdict === 'PASS') return 'eligible'
  if (verdict === 'FAIL') return 'not_eligible'
  if (verdict === 'PARTIAL') return met && met > 0 ? 'partial' : 'unconfirmed'
  return 'unconfirmed'
}
