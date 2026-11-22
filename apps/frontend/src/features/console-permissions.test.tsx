import {afterEach, expect, it, vi} from 'vitest'
import {cleanup, render, screen} from '@testing-library/react'
import {QueryClient, QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter, Route, Routes} from 'react-router-dom'
import {Console} from './console'
import {api, post} from '../api'
import type {Workspace} from '../types'

vi.mock('../api', async importOriginal => ({...await importOriginal<typeof import('../api')>(), api: vi.fn(), post: vi.fn()}))
vi.mock('../session', () => ({useSession: () => ({session: {role: 'staff'}})}))

afterEach(() => {cleanup(); vi.clearAllMocks()})

async function openTicket(actions: string[], pending = false, authority = false) {
  const ticket: Workspace = {
    ticket_id: 'TCK-REVIEW', created_at: '2026-11-12T09:00:00Z', status: 'open',
    handling_mode: 'assisted', is_authority_required: authority, customer: {display_name: 'Synthetic customer'},
    excerpt: 'What is the return window?', message: {body: 'What is the return window?', created_at: '2026-11-12T09:00:00Z'},
    order: null, other_orders: [], proposal: null, escalation: null, reply: null, allowed_actions: actions,
    suggestion: {
      suggestion_id: 'SG-REVIEW', created_at: '2026-11-12T09:00:00Z', trigger: 'ticket_created',
      analysis_status: 'ready', draft_status: pending ? 'pending' : 'draft_ready',
      analysis: {
        intent: {label: 'return_policy', probability: .3139837682247162, confidence_band: 'low', score_kind: 'uncalibrated_softmax'},
        alternatives: [{label: 'return_product', probability: .2840874493122101, confidence_band: 'low'}],
        documents: [], routing: {recommendation: 'draft', reason_codes: []},
      },
      draft: {text: 'Please review the return conditions for your item.', segments: [], citations: []},
      warnings: [], reason_codes: [], step_latency_ms: {}, trace_id: 'trace-review',
    },
  }
  vi.mocked(api).mockImplementation(async path => path.includes('?') ? {items: [], next_cursor: null} : ticket)
  vi.mocked(post).mockResolvedValue({})
  const client = new QueryClient({defaultOptions: {queries: {retry: false, gcTime: 0}}})
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/console/tickets/TCK-REVIEW']}>
    <Routes><Route path="/console/*" element={<Console/>}/></Routes>
  </MemoryRouter></QueryClientProvider>)
  await screen.findByRole('heading', {name: /Ticket TCK-REVIEW/})
}

it('does not enable send when the server omits send_reply on a ready ticket', async () => {
  await openTicket(['correct_intent'])
  const send = screen.queryByRole('button', {name: 'Send reply'})
  if (send) expect(send).toBeDisabled()
})

it('keeps send disabled while a suggestion is pending', async () => {
  await openTicket(['correct_intent'], true)
  expect(screen.getByRole('button', {name: 'Send reply'})).toBeDisabled()
})

it('does not offer direct send to staff for an authority ticket', async () => {
  await openTicket(['correct_intent', 'submit_reply_proposal'], false, true)
  expect(screen.queryByRole('button', {name: 'Send reply'})).not.toBeInTheDocument()
  expect(screen.getByRole('button', {name: 'Submit for approval'})).toBeEnabled()
})

it('allows a ready reply when the server grants send_reply', async () => {
  await openTicket(['send_reply'])
  expect(screen.getByRole('button', {name: 'Send reply'})).toBeEnabled()
})

it('shows readable raw scores without presenting calibrated percentages', async () => {
  await openTicket(['correct_intent', 'send_reply'])
  expect(screen.getByText('Raw score · 0.314')).toBeInTheDocument()
  expect(screen.getByRole('button', {name: 'Return product 0.284'})).toBeInTheDocument()
  expect(screen.queryByText(/31\.4%/)).not.toBeInTheDocument()
})
