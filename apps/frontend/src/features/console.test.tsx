import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { replyBlocker, replyBasis } from '../components/reply-rules'
import { Status } from '../components/ui'

describe('Console Reply Rules and Blocker Workflow', () => {
  it('blocks empty reply bodies', () => {
    expect(replyBlocker('', [], [], false)).toBe('Write a reply before continuing.')
    expect(replyBlocker('   ', [], [], false)).toBe('Write a reply before continuing.')
  })

  it('blocks replies while AI analysis is pending', () => {
    expect(replyBlocker('Some draft answer', [], [], true)).toBe('The AI is still working on this ticket.')
  })

  it('blocks unresolved customer PII placeholders', () => {
    expect(replyBlocker('Hello [NAME], your order [ORDER_ID] is delayed.', [], [], false)).toBe(
      'Replace personal data placeholders before sending.'
    )
    expect(replyBlocker('Please verify card [CARD_1].', [], [], false)).toBe(
      'Replace personal data placeholders before sending.'
    )
    expect(replyBlocker('Contact at [PHONE] or [ADDRESS].', [], [], false)).toBe(
      'Replace personal data placeholders before sending.'
    )
  })

  it('blocks replies exceeding 4000 characters', () => {
    const longText = 'a'.repeat(4001)
    expect(replyBlocker(longText, [], [], false)).toBe('Keep the reply within 4,000 characters.')
  })

  it('blocks reply when required warnings are unacknowledged', () => {
    const warnings = ['WARN-01', 'WARN-02']
    const acknowledged = ['WARN-01']
    expect(replyBlocker('Valid reply text', warnings, acknowledged, false)).toBe(
      'Check every warning before sending.'
    )
  })

  it('allows reply when all warnings are acknowledged and text is valid', () => {
    const warnings = ['WARN-01', 'WARN-02']
    const acknowledged = ['WARN-01', 'WARN-02']
    expect(replyBlocker('Dear Customer, your item has shipped.', warnings, acknowledged, false)).toBeNull()
  })

  it('derives correct basis for review actions', () => {
    // Normal AI draft approved
    expect(replyBasis('ready', false, false)).toBe('ai_draft')
    // AI draft rejected by agent with manual reply
    expect(replyBasis('ready', true, false)).toBe('rejected_ai_draft')
    // No AI draft available (manual handling)
    expect(replyBasis('unavailable', false, false)).toBe('no_ai_draft')
    // Manager proposal submitted
    expect(replyBasis('ready', false, true)).toBe('reply_proposal')
    expect(replyBasis('unavailable', false, true)).toBe('reply_proposal')
  })

  it('renders critical workflow statuses accurately', () => {
    const { container: c1 } = render(<Status value="escalated" />)
    expect(c1.textContent).toContain('Escalated')

    const { container: c2 } = render(<Status value="draft_ready" />)
    expect(c2.textContent).toContain('Draft ready')

    const { container: c3 } = render(<Status value="abstained" />)
    expect(c3.textContent).toContain('AI abstained')

    const { container: c4 } = render(<Status value="escalation_recommended" />)
    expect(c4.textContent).toContain('Escalation recommended')
  })
})

