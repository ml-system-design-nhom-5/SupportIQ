import {afterEach, describe, expect, it, vi} from 'vitest'
import {cleanup, render, screen} from '@testing-library/react'
import {QueryClient, QueryClientProvider} from '@tanstack/react-query'
import {MemoryRouter} from 'react-router-dom'
import App from '../App'
import {api, post} from '../api'
import {roleHome, useSession} from '../session'
import type {Role, Workspace} from '../types'

vi.mock('../api', async importOriginal => ({...await importOriginal<typeof import('../api')>(), api: vi.fn(), post: vi.fn()}))
vi.mock('../session', async importOriginal => {
  const actual = await importOriginal<typeof import('../session')>()
  return {...actual, useSession: vi.fn()}
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function mockSession(role: Role, displayName = 'Test User', accountId = 'acc-self') {
  vi.mocked(useSession).mockReturnValue({
    session: {account_id: accountId, display_name: displayName, role},
    loading: false,
    error: null,
    signIn: vi.fn(),
    signOut: vi.fn(),
  })
}

function renderAt(path: string) {
  const client = new QueryClient({defaultOptions: {queries: {retry: false, gcTime: 0}}})
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('Unified Staff + Admin Console permissions and routing', () => {
  it('routes admin home to /console and removes manager from SignIn demo note', async () => {
    expect(roleHome.admin).toBe('/console')
    expect(roleHome.staff).toBe('/console')
    vi.mocked(useSession).mockReturnValue({
      session: null, loading: false, error: null, signIn: vi.fn(), signOut: vi.fn(),
    })
    renderAt('/sign-in')
    expect(await screen.findByText('Demo accounts: staff-1, admin-1, customer-1')).toBeInTheDocument()
  })

  it('shows Tickets, Reports, Accounts, Versions to admin in unified console shell', async () => {
    mockSession('admin', 'Minh Le', 'acc-admin')
    vi.mocked(api).mockResolvedValue({items: [], next_cursor: null})
    renderAt('/console')
    expect(await screen.findByRole('link', {name: 'Tickets'})).toHaveAttribute('href', '/console')
    expect(screen.getByRole('link', {name: 'Reports'})).toHaveAttribute('href', '/console/reports')
    expect(screen.getByRole('link', {name: 'Accounts'})).toHaveAttribute('href', '/console/accounts')
    expect(screen.getByRole('link', {name: 'Versions'})).toHaveAttribute('href', '/console/versions')
    expect(screen.getByLabelText('Filter tickets by status')).toBeInTheDocument()
  })

  it('lets admin send authority replies directly without Submit for approval', async () => {
    mockSession('admin', 'Minh Le', 'acc-admin')
    const authorityTicket: Workspace = {
      ticket_id: 'TCK-AUTH', created_at: '2026-11-12T09:00:00Z', status: 'open',
      handling_mode: 'assisted', is_authority_required: true, customer: {display_name: 'Customer'},
      excerpt: 'Refund please', message: {body: 'Refund please', created_at: '2026-11-12T09:00:00Z'},
      order: null, other_orders: [], proposal: null, escalation: null, reply: null,
      allowed_actions: ['correct_intent', 'escalate', 'send_reply'],
      suggestion: {
        suggestion_id: 'SG-AUTH', created_at: '2026-11-12T09:00:00Z', trigger: 'ticket_created',
        analysis_status: 'ready', draft_status: 'draft_ready',
        analysis: {intent: {label: 'request_refund', probability: .8, confidence_band: 'high'}, alternatives: [], documents: [], routing: {recommendation: 'draft', reason_codes: []}},
        draft: {text: 'Approved refund draft.', segments: [], citations: []},
        warnings: [], reason_codes: [], step_latency_ms: {}, trace_id: 't-auth',
      },
    }
    vi.mocked(api).mockImplementation(async path => path.includes('?') ? {items: [], next_cursor: null} : authorityTicket)
    vi.mocked(post).mockResolvedValue({})
    renderAt('/console/tickets/TCK-AUTH')
    expect(await screen.findByRole('button', {name: 'Send reply'})).toBeEnabled()
    expect(screen.queryByRole('button', {name: 'Submit for approval'})).not.toBeInTheDocument()
  })

  it('hides admin/reports nav from staff and denies /console/accounts, /console/versions, /console/reports', async () => {
    mockSession('staff', 'Mai Nguyen', 'acc-staff')
    vi.mocked(api).mockResolvedValue({items: [], next_cursor: null})
    renderAt('/console')
    expect(await screen.findByRole('link', {name: 'Tickets'})).toBeInTheDocument()
    expect(screen.queryByRole('link', {name: 'Reports'})).not.toBeInTheDocument()
    expect(screen.queryByRole('link', {name: 'Accounts'})).not.toBeInTheDocument()
    expect(screen.queryByRole('link', {name: 'Versions'})).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Filter tickets by status')).not.toBeInTheDocument()

    for (const restricted of ['/console/accounts', '/console/versions', '/console/reports', '/admin/accounts']) {
      cleanup()
      renderAt(restricted)
      expect(await screen.findByText('Permission denied')).toBeInTheDocument()
    }
  })

  it('redirects legacy /admin/accounts and /admin/versions to /console/* and omits Make manager button', async () => {
    mockSession('admin', 'Minh Le', 'acc-admin')
    vi.mocked(api).mockResolvedValue({
      items: [
        {account_id: 'acc-admin', login_name: 'admin-1', display_name: 'Minh Le', role: 'admin', is_active: true},
        {account_id: 'acc-staff', login_name: 'staff-1', display_name: 'Mai Nguyen', role: 'staff', is_active: true},
        {account_id: 'acc-mgr', login_name: 'manager-1', display_name: 'Hoa Pham', role: 'manager', is_active: true},
      ],
      next_cursor: null,
    })
    renderAt('/admin/accounts')
    expect(await screen.findByRole('heading', {name: 'Internal accounts'})).toBeInTheDocument()
    expect(await screen.findByRole('button', {name: 'Make staff'})).toBeInTheDocument()
    expect(screen.queryByRole('button', {name: 'Make manager'})).not.toBeInTheDocument()
  })
})
