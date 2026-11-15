import {afterEach, describe, expect, it, vi} from 'vitest'
import {cleanup, render, screen, within} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {QueryClient, QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter, Route, Routes} from 'react-router-dom'
import {Console} from './console'
import {api, post} from '../api'
import type {Role, Workspace} from '../types'

let mockRole: Role = 'staff'

vi.mock('../api', async importOriginal => ({...await importOriginal<typeof import('../api')>(), api: vi.fn(), post: vi.fn()}))
vi.mock('../session', () => ({
  useSession: () => ({session: {account_id: 'acc-1', display_name: 'Reviewer', role: mockRole}}),
}))

afterEach(() => {
  mockRole = 'staff'
  cleanup()
  vi.clearAllMocks()
})

interface TicketOptions {
  actions?: string[] | undefined
  pending?: boolean
  authority?: boolean
  status?: string
  handling_mode?: string
  withDraft?: boolean
  proposal?: Workspace['proposal']
  reply?: Workspace['reply']
}

function buildTicket(options: TicketOptions = {}): Workspace {
  const {
    pending = false,
    authority = false,
    status = 'open',
    handling_mode = 'assisted',
    withDraft = true,
    proposal = null,
    reply = null,
  } = options
  const actions = 'actions' in options ? options.actions : ['send_reply']
  return {
    ticket_id: 'TCK-REVIEW',
    created_at: '2026-11-12T09:00:00Z',
    status,
    handling_mode,
    is_authority_required: authority,
    customer: {display_name: 'Synthetic customer'},
    excerpt: 'What is the return window?',
    message: {body: 'What is the return window?', created_at: '2026-11-12T09:00:00Z'},
    order: null,
    other_orders: [],
    proposal,
    escalation: null,
    reply,
    allowed_actions: actions as string[],
    suggestion: {
      suggestion_id: 'SG-REVIEW',
      created_at: '2026-11-12T09:00:00Z',
      trigger: 'ticket_created',
      analysis_status: 'ready',
      draft_status: pending ? 'pending' : withDraft ? 'draft_ready' : 'unavailable',
      analysis: {
        intent: {
          label: 'return_policy',
          probability: 0.3139837682247162,
          confidence_band: 'low',
          score_kind: 'uncalibrated_softmax',
        },
        alternatives: [{label: 'return_product', probability: 0.2840874493122101, confidence_band: 'low'}],
        documents: [],
        routing: {recommendation: 'draft', reason_codes: []},
      },
      draft: withDraft
        ? {text: 'Please review the return conditions for your item.', segments: [], citations: []}
        : undefined,
      warnings: [],
      reason_codes: [],
      step_latency_ms: {},
      trace_id: 'trace-review',
    },
  }
}

async function openTicket(optionsOrActions: TicketOptions | string[] = {}, pending = false, authority = false) {
  const options: TicketOptions = Array.isArray(optionsOrActions)
    ? {actions: optionsOrActions, pending, authority}
    : optionsOrActions
  const ticket = buildTicket(options)
  vi.mocked(api).mockImplementation(async path => (path.includes('?') ? {items: [], next_cursor: null} : ticket))
  vi.mocked(post).mockResolvedValue({})
  const client = new QueryClient({defaultOptions: {queries: {retry: false, gcTime: 0}}})
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/console/tickets/TCK-REVIEW']}>
        <Routes>
          <Route path="/console/*" element={<Console />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await screen.findByRole('heading', {name: /Ticket TCK-REVIEW/})
  return {client, ticket}
}

describe('Console Reply Permissions', () => {
  it('hides Send reply when the server omits send_reply on a ready ticket regardless of role', async () => {
    await openTicket(['correct_intent'])
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.getByText('You cannot send a reply on this ticket.')).toBeInTheDocument()
    expect(screen.queryByRole('button', {name: 'Edit draft'})).not.toBeInTheDocument()
    expect(screen.queryByRole('button', {name: 'Reject draft'})).not.toBeInTheDocument()
    expect(screen.queryByText('Review complete. Your reply is ready to send.')).not.toBeInTheDocument()
  })

  it('ignores admin and manager role fallbacks when allowed_actions excludes send_reply', async () => {
    mockRole = 'admin'
    await openTicket({actions: ['escalate'], authority: false, status: 'open'})
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.getByRole('button', {name: 'Escalate ticket'})).toBeEnabled()

    cleanup()
    mockRole = 'manager'
    await openTicket({actions: ['correct_intent'], authority: true, status: 'escalated'})
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.queryByRole('button', {name: 'Submit for approval'})).not.toBeInTheDocument()
  })

  it('fails closed when allowed_actions is empty, undefined, or malformed', async () => {
    await openTicket({actions: []})
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.getByText('This ticket is waiting on an administrator.')).toBeInTheDocument()

    cleanup()
    mockRole = 'admin'
    await openTicket({actions: undefined})
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.getByText('This ticket is waiting on an administrator.')).toBeInTheDocument()

    cleanup()
    mockRole = 'admin'
    await openTicket({actions: null as unknown as string[]})
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.getByText('This ticket is waiting on an administrator.')).toBeInTheDocument()
  })

  it('blocks sending while suggestion is pending whether send_reply is omitted or temporarily present', async () => {
    await openTicket(['correct_intent'], true)
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.getByText('The AI is still working on this ticket.')).toBeInTheDocument()

    cleanup()
    await openTicket(['correct_intent', 'send_reply'], true)
    expect(screen.getByRole('button', {name: 'Send reply'})).toBeDisabled()
    expect(screen.getByText('The AI is still working on this ticket.')).toBeInTheDocument()
  })

  it('fails closed on closed tickets and own pending proposals', async () => {
    mockRole = 'admin'
    await openTicket({
      actions: [],
      status: 'closed',
      reply: {body: 'Sent answer.', by: 'Admin', sent_at: '2026-11-12T09:10:00Z'},
    })
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.getByText('This reply has been sent and cannot be changed.')).toBeInTheDocument()

    cleanup()
    mockRole = 'admin'
    await openTicket({
      actions: [],
      status: 'awaiting_approval',
      authority: true,
      proposal: {
        proposal_id: 'PR-OWN',
        basis: 'ai_draft',
        body: 'My own proposed reply.',
        by: 'Reviewer',
        created_at: '2026-11-12T09:05:00Z',
      },
    })
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    expect(screen.queryByRole('button', {name: 'Edit proposal'})).not.toBeInTheDocument()
    expect(screen.getByText('My own proposed reply.')).toBeInTheDocument()
    expect(screen.getByText('This ticket is waiting on an administrator.')).toBeInTheDocument()
  })

  it('allows direct send when server grants send_reply and closes stale confirm modal if permission is revoked', async () => {
    const user = userEvent.setup()
    const {client} = await openTicket(['send_reply'])
    const sendButton = screen.getByRole('button', {name: 'Send reply'})
    expect(sendButton).toBeEnabled()

    await user.click(sendButton)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()

    // Simulate background refetch revoking send_reply while confirm modal is open
    const revokedTicket = buildTicket({actions: ['correct_intent']})
    vi.mocked(api).mockImplementation(async path => (path.includes('?') ? {items: [], next_cursor: null} : revokedTicket))
    await client.invalidateQueries({queryKey: ['workspace', 'TCK-REVIEW']})

    expect(await screen.findByText('You cannot send a reply on this ticket.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(post).not.toHaveBeenCalledWith(expect.stringContaining('/replies'), expect.anything(), expect.anything())
  })

  it('preserves staff Submit for approval flow and admin approval send with reply_proposal basis', async () => {
    const user = userEvent.setup()
    await openTicket(['correct_intent', 'submit_reply_proposal'], false, true)
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    const proposeButton = screen.getByRole('button', {name: 'Submit for approval'})
    expect(proposeButton).toBeEnabled()

    await user.click(proposeButton)
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Submit for approval'}))
    expect(post).toHaveBeenCalledWith(
      '/v1/console/tickets/TCK-REVIEW/reply-proposals',
      expect.objectContaining({basis: 'ai_draft', suggestion_id: 'SG-REVIEW'}),
      expect.any(String),
    )

    cleanup()
    vi.clearAllMocks()
    mockRole = 'admin'
    await openTicket({
      actions: ['send_reply'],
      status: 'awaiting_approval',
      authority: true,
      proposal: {
        proposal_id: 'PR-OTHER',
        basis: 'ai_draft',
        body: 'Proposed answer.',
        by: 'Staff One',
        created_at: '2026-11-12T09:05:00Z',
      },
    })
    await user.click(screen.getByRole('button', {name: 'Send reply'}))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Send reply'}))
    expect(post).toHaveBeenCalledWith(
      '/v1/console/tickets/TCK-REVIEW/replies',
      expect.objectContaining({basis: 'reply_proposal', body: 'Proposed answer.', proposal_id: 'PR-OTHER'}),
      expect.any(String),
    )
  })

  it('preserves manual no_ai_draft, rejected_ai_draft, escalation flows, and raw score display', async () => {
    const user = userEvent.setup()
    await openTicket({actions: ['send_reply', 'escalate'], handling_mode: 'manual', withDraft: false})
    const textarea = screen.getByLabelText('Reply to customer')
    await user.type(textarea, 'Hello [[NAME]')
    expect(screen.getByRole('button', {name: 'Send reply'})).toBeDisabled()
    await user.clear(textarea)
    await user.type(textarea, 'Your manual refund confirmation is complete.')
    await user.click(screen.getByRole('button', {name: 'Send reply'}))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Send reply'}))
    expect(post).toHaveBeenCalledWith(
      '/v1/console/tickets/TCK-REVIEW/replies',
      expect.objectContaining({basis: 'no_ai_draft', body: 'Your manual refund confirmation is complete.'}),
      expect.any(String),
    )

    cleanup()
    vi.clearAllMocks()
    await openTicket({actions: ['correct_intent', 'send_reply', 'escalate']})
    expect(screen.getByText('Raw score · 0.314')).toBeInTheDocument()
    expect(screen.getByRole('button', {name: 'Return product 0.284'})).toBeInTheDocument()
    expect(screen.queryByText(/31\.4%/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', {name: 'Reject draft'}))
    await user.click(screen.getByRole('button', {name: 'Wrong intent'}))
    await user.type(screen.getByLabelText('Reply to customer'), 'Manual replacement reply.')
    await user.click(screen.getByRole('button', {name: 'Send reply'}))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Send reply'}))
    expect(post).toHaveBeenCalledWith(
      '/v1/console/tickets/TCK-REVIEW/replies',
      expect.objectContaining({
        basis: 'rejected_ai_draft',
        body: 'Manual replacement reply.',
        staff_reason_codes: ['wrong_intent'],
      }),
      expect.any(String),
    )

    cleanup()
    vi.clearAllMocks()
    await openTicket({actions: ['escalate']})
    expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', {name: 'Escalate ticket'}))
    await user.click(screen.getByRole('button', {name: 'Case exception'}))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', {name: 'Escalate ticket'}))
    expect(post).toHaveBeenCalledWith(
      '/v1/console/tickets/TCK-REVIEW/escalations',
      expect.objectContaining({staff_reason_codes: ['case_exception'], suggestion_id: 'SG-REVIEW'}),
      expect.any(String),
    )
  })
})
