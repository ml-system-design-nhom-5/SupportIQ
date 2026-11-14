import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Reports } from './reports'
import { api } from '../api'
import type { Report } from '../types'

vi.mock('../api', async importOriginal => ({
  ...await importOriginal<typeof import('../api')>(),
  api: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function makeReport(cost: Report['llm_cost_micro_usd']): Report {
  return {
    period: { start_at: '2026-11-10T00:00:00Z', end_at: '2026-11-11T00:00:00Z' },
    ticket_counts: { assisted: { created: 1, closed: 1 }, manual: { created: 0, closed: 0 } },
    draft_decisions: { approve: { count: 1, share: 1 }, edit: { count: 0, share: 0 }, reject: { count: 0, share: 0 } },
    escalations: {},
    ai_outcomes: { draft_ready: 1 },
    ai_error_rate: 0,
    end_to_end_latency_ms: { p50: 1000, p95: 1000 },
    suggestion_latency_ms: { analysis: { p50: 100, p95: 100 }, draft: { p50: 200, p95: 200 } },
    llm_cost_micro_usd: cost,
    handling_time_ms: { assisted: { p50: 5000 }, manual: { p50: null } },
  }
}

async function renderReport(cost: Report['llm_cost_micro_usd']) {
  vi.mocked(api).mockResolvedValue(makeReport(cost))
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  render(
    <QueryClientProvider client={client}>
      <Reports />
    </QueryClientProvider>,
  )
  await screen.findByText('Total LLM cost')
}

it('shows Unknown instead of $0.0000 when cost metadata is missing', async () => {
  await renderReport({
    total: null,
    known_total: 0,
    average: null,
    known_average: null,
    known_count: 0,
    unknown_count: 2,
  })
  const totalCard = screen.getByText('Total LLM cost').closest('div')!
  expect(totalCard).toHaveTextContent('Unknown')
  expect(totalCard).not.toHaveTextContent('$0.0000')
  expect(screen.getByText('Unmeasured LLM suggestions')).toBeInTheDocument()
})

it('shows partial known subtotal alongside Unknown when costs are mixed', async () => {
  await renderReport({
    total: null,
    known_total: 4000,
    average: null,
    known_average: 2000,
    known_count: 2,
    unknown_count: 1,
  })
  expect(screen.getByText('Total LLM cost').closest('div')).toHaveTextContent('Unknown')
  expect(screen.getByText('Known cost subtotal (2 measured)').closest('div')).toHaveTextContent('$0.0040')
  expect(screen.getByText('Average across measured suggestions').closest('div')).toHaveTextContent('$0.0020')
  expect(screen.getByText('Unmeasured LLM suggestions').closest('div')).toHaveTextContent('1')
})

it('renders verified $0.0000 when all LLM calls report real 0 cost', async () => {
  await renderReport({
    total: 0,
    known_total: 0,
    average: 0,
    known_average: 0,
    known_count: 2,
    unknown_count: 0,
  })
  expect(screen.getByText('Total LLM cost').closest('div')).toHaveTextContent('$0.0000')
  expect(screen.getByText('Average per suggestion with an LLM call').closest('div')).toHaveTextContent('$0.0000')
})
