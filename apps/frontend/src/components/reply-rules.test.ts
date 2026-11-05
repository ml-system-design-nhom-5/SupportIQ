import { describe, expect, it } from 'vitest'
import { replyBlocker, replyBasis } from './reply-rules'

describe('review before sending', () => {
  it('blocks empty replies and unresolved placeholders', () => {
    expect(replyBlocker('', [], [], false)).toBeTruthy()
    expect(replyBlocker('Hello [NAME_12]', [], [], false)).toContain('personal data')
    expect(replyBlocker('Hello [LITERAL_1]', [], [], false)).toContain('personal data')
  })
  it('requires every warning acknowledgement and waits for AI', () => {
    expect(replyBlocker('Reply', ['w1', 'w2'], ['w1'], false)).toContain('warning')
    expect(replyBlocker('Reply', ['w1'], ['w1'], true)).toContain('working')
    expect(replyBlocker('Reply', ['w1'], ['w1'], false)).toBeNull()
  })
  it('derives the basis from the review action', () => {
    expect(replyBasis('ready', false, false)).toBe('ai_draft')
    expect(replyBasis('ready', true, false)).toBe('rejected_ai_draft')
    expect(replyBasis('unavailable', false, false)).toBe('no_ai_draft')
    expect(replyBasis('ready', false, true)).toBe('reply_proposal')
  })
})
