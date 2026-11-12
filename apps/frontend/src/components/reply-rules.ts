export function replyBlocker(body: string, warnings: string[], acknowledged: string[], pending: boolean): string | null {
  if (pending) return 'The AI is still working on this ticket.'
  if (!body.trim()) return 'Write a reply before continuing.'
  if (/\[(NAME|EMAIL|PHONE|CARD|ADDRESS|ORDER_ID|TRACKING_ID|TRANSACTION_ID|LITERAL)(_[1-9][0-9]{0,2})?\]/.test(body)) return 'Replace personal data placeholders before sending.'
  if (body.length > 4000) return 'Keep the reply within 4,000 characters.'
  if (warnings.some(id => !acknowledged.includes(id))) return 'Check every warning before sending.'
  return null
}

export function replyBasis(state: string, rejected: boolean, proposal: boolean) {
  return proposal ? 'reply_proposal' : state === 'ready' ? rejected ? 'rejected_ai_draft' : 'ai_draft' : 'no_ai_draft'
}
