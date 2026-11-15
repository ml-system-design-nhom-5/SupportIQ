import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { resolve, join } from 'node:path'

const repoRoot = resolve(process.cwd())
const require = createRequire(join(repoRoot, 'apps/frontend/package.json'))
const { chromium } = require('@playwright/test')
const AxeBuilder = require('@axe-core/playwright').default

const BASE_URL = 'http://127.0.0.1:8080'
const OUT_DIR = join(repoRoot, 'artifacts/browser/console_send_permission_c_20261115')
mkdirSync(OUT_DIR, { recursive: true })

const credentials = JSON.parse(readFileSync(join(repoRoot, '.local/application.json'), 'utf8'))

const results = []
function record(id, status, details) {
  results.push({ id, status, details })
}

async function checkVisualHealth(page, name) {
  await page.evaluate(() => document.fonts.ready)
  const layout = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    overflowX: document.documentElement.scrollWidth > window.innerWidth,
    bodyBg: getComputedStyle(document.body).backgroundColor,
  }))
  const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).analyze()
  const violations = axe.violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length }))
  if (layout.overflowX) throw new Error(`${name}: horizontal overflow (${layout.scrollWidth} > ${layout.innerWidth})`)
  if (violations.length > 0) throw new Error(`${name}: axe violations ${JSON.stringify(violations)}`)
  return { layout, axeViolations: violations }
}

function makeWorkspacePayload({
  ticketId = 'TCK-SYNTH-100',
  status = 'open',
  actor = { account_id: 'acc-admin-1', display_name: 'Minh Le', role: 'admin' },
  allowed_actions = ['send_reply'],
  is_authority_required = false,
  analysis_status = 'ready',
  draft_status = 'draft_ready',
  draftText = 'Your refund request is under review.',
  warnings = [],
  proposal = null,
  reply = null,
}) {
  const suggestion = {
    suggestion_id: 'SUG-1',
    created_at: '2026-11-15T09:00:00Z',
    trigger: 'ticket_created',
    analysis_status,
    draft_status,
    analysis: analysis_status === 'ready' ? {
      intent: {
        label: 'refund_status',
        probability: 0.98,
        confidence_band: 'high',
        source: 'model',
        score_kind: 'calibrated_probability',
        model_mode: 'trained',
        verified: true,
      },
      alternatives: [{ label: 'request_refund', probability: 0.01, confidence_band: 'low' }],
      documents: [
        {
          document_id: 'POL-REFUND-007',
          version: '1.0',
          title: 'Checking Refund History and Order Status',
          snippet: 'Customers can monitor refund progress in Return & Refund Management.',
          validity: 'valid',
          rank: 1,
        },
      ],
      routing: { recommendation: 'draft', reason_codes: [] },
    } : undefined,
    draft: draft_status === 'draft_ready' && draftText ? {
      text: draftText,
      segments: [{ segment_id: 'seg-1', paragraph_index: 0, text: draftText, citation_ids: ['cit-1'] }],
      citations: [{ citation_id: 'cit-1', source_type: 'kb_document', document_id: 'POL-REFUND-007', version: '1.0', snippet: 'Customers can monitor refund progress.' }],
    } : undefined,
    warnings,
    reason_codes: draft_status === 'llm_unavailable' ? ['llm_unavailable'] : [],
    staff_note: draft_status === 'llm_unavailable' ? 'Draft generation is unavailable. Review the retrieved sources and write a reply manually.' : undefined,
    step_latency_ms: { analysis: 50, llm: 0 },
    trace_id: 'trace-synth-1',
  }

  const workspace = {
    ticket_id: ticketId,
    created_at: '2026-11-15T09:00:00Z',
    status,
    handling_mode: 'assisted',
    is_authority_required,
    customer: { display_name: 'Nguyen Van A' },
    excerpt: 'Please check my refund status for ORD-1001.',
    draft_status,
    intent: suggestion.analysis?.intent,
    message: { body: 'Please check my refund status for ORD-1001.', created_at: '2026-11-15T09:00:00Z' },
    order: {
      order_id: 'ORD-1001',
      order_status: 'shipped',
      source_status: 'Shipping',
      placed_at: '2026-10-01T07:00:00Z',
      order_total: { amount_minor: 100000, currency: 'VND' },
      shipping_cost: { amount_minor: 15000, currency: 'VND' },
      lines: [{ product_id: 'PRD-1', product_name: 'Wireless Mouse', quantity: 1 }],
      shipment: { shipment_status: 'delivered', delivered_at: '2026-10-04T12:00:00Z', timeline: [] },
      refund: { refund_status: 'requested', refund_amount: { amount_minor: 50000, currency: 'VND' } },
    },
    other_orders: [],
    suggestion,
    proposal,
    escalation: null,
    reply,
  }
  if (allowed_actions !== '__ABSENT__') {
    workspace.allowed_actions = allowed_actions
  }
  const summary = {
    ticket_id: ticketId,
    created_at: workspace.created_at,
    status: workspace.status,
    handling_mode: workspace.handling_mode,
    is_authority_required,
    customer: workspace.customer,
    excerpt: workspace.excerpt,
    draft_status,
    intent: workspace.intent,
  }
  return { actor, workspace, ticketList: [summary] }
}

async function setupSyntheticScenario(page, stateProvider) {
  const calls = []
  await page.route('**/v1/**', async route => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()
    const state = stateProvider()
    let bodyJson = null
    if (req.postData()) {
      try { bodyJson = JSON.parse(req.postData()) } catch { bodyJson = req.postData() }
    }
    calls.push({ method, path, body: bodyJson })

    const json = (payload, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })

    if (path === '/v1/sessions/current' && method === 'GET') {
      return json(state.actor)
    }
    if (path === '/v1/console/tickets' && method === 'GET') {
      return json({ items: state.ticketList, next_cursor: null })
    }
    if (path === `/v1/console/tickets/${state.workspace.ticket_id}` && method === 'GET') {
      return json(state.workspace)
    }
    if (path === `/v1/console/tickets/${state.workspace.ticket_id}/replies` && method === 'POST') {
      return json(state.workspace, 201)
    }
    if (path === `/v1/console/tickets/${state.workspace.ticket_id}/reply-proposals` && method === 'POST') {
      return json(state.workspace, 201)
    }
    if (path === `/v1/console/tickets/${state.workspace.ticket_id}/escalations` && method === 'POST') {
      return json(state.workspace, 201)
    }
    if (path === `/v1/console/tickets/${state.workspace.ticket_id}/suggestions` && method === 'POST') {
      return json(state.workspace, 201)
    }
    if (path === `/v1/console/tickets/${state.workspace.ticket_id}/views` && method === 'POST') {
      return json({}, 200)
    }
    return json({ detail: `Unexpected synthetic route ${method} ${path}` }, 404)
  })
  return calls
}

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    // 1. Read-only Real Runtime Browser Check (staff-1 and admin-1, zero ticket mutations)
    {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await context.newPage()
      const consoleErrors = []
      const pageErrors = []
      const server5xx = []
      page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
      page.on('pageerror', err => pageErrors.push(String(err)))
      page.on('response', res => { if (res.status() >= 500) server5xx.push(`${res.status()} ${res.url()}`) })

      await page.goto(`${BASE_URL}/sign-in`)
      await page.getByLabel('Login name').fill('staff-1')
      await page.getByLabel('Password', { exact: true }).fill(credentials.passwords.staff)
      await page.getByRole('button', { name: 'Sign in', exact: true }).click()
      await page.getByRole('button', { name: 'Sign out' }).waitFor({ state: 'visible' })
      await page.goto(`${BASE_URL}/console`)
      await page.getByRole('status', { name: 'Loading inbox', exact: true }).waitFor({ state: 'hidden' })
      const staffHealth = await checkVisualHealth(page, 'real-runtime-staff-console')
      await page.screenshot({ path: join(OUT_DIR, 'real-runtime-staff-console.png'), fullPage: true, animations: 'disabled' })

      await page.getByRole('button', { name: 'Sign out' }).click()
      await page.getByRole('heading', { name: 'Sign in to SupportIQ' }).waitFor({ state: 'visible' })

      await page.getByLabel('Login name').fill('admin-1')
      await page.getByLabel('Password', { exact: true }).fill(credentials.passwords.admin)
      await page.getByRole('button', { name: 'Sign in', exact: true }).click()
      await page.getByRole('button', { name: 'Sign out' }).waitFor({ state: 'visible' })
      await page.goto(`${BASE_URL}/console`)
      await page.getByRole('status', { name: 'Loading inbox', exact: true }).waitFor({ state: 'hidden' })
      const adminHealth = await checkVisualHealth(page, 'real-runtime-admin-console')
      await page.screenshot({ path: join(OUT_DIR, 'real-runtime-admin-console.png'), fullPage: true, animations: 'disabled' })

      await page.getByRole('button', { name: 'Sign out' }).click()
      await page.getByRole('heading', { name: 'Sign in to SupportIQ' }).waitFor({ state: 'visible' })

      const unexpectedErrors = consoleErrors.filter(e =>
        !e.includes('status of 401 (Unauthorized)') &&
        !e.includes("violates the following Content Security Policy directive: \"font-src 'self'\"")
      )
      if (unexpectedErrors.length || pageErrors.length || server5xx.length) {
        throw new Error(`Real runtime browser errors: unexpected=${JSON.stringify(unexpectedErrors)} page=${JSON.stringify(pageErrors)} 5xx=${JSON.stringify(server5xx)}`)
      }
      record('real-runtime-readonly-staff-admin', 'PASS', {
        staffHealth,
        adminHealth,
        unexpectedConsoleErrors: 0,
        observedExpectedConsoleMessages: consoleErrors.length,
        pageErrors: 0,
        server5xx: 0,
      })
      await context.close()
    }

    async function runSynthetic(id, fn) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
      const page = await context.newPage()
      const pageErrors = []
      const consoleErrors = []
      page.on('pageerror', err => pageErrors.push(String(err)))
      page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()) })
      try {
        const detail = await fn(page)
        const unexpectedErrors = consoleErrors.filter(e =>
          !e.includes("violates the following Content Security Policy directive: \"font-src 'self'\"")
        )
        if (pageErrors.length || unexpectedErrors.length) {
          throw new Error(`Console/page errors in ${id}: unexpected=${JSON.stringify(unexpectedErrors)} page=${JSON.stringify(pageErrors)}`)
        }
        record(id, 'PASS', detail)
      } finally {
        await context.close()
      }
    }

    // P1: Contradictory admin role with escalate-only allowed_actions
    await runSynthetic('P1-contradictory-admin-escalate-only', async page => {
      const state = makeWorkspacePayload({
        actor: { account_id: 'acc-admin-1', display_name: 'Minh Le', role: 'admin' },
        allowed_actions: ['escalate'],
        is_authority_required: true,
      })
      const calls = await setupSyntheticScenario(page, () => state)
      await page.goto(`${BASE_URL}/console/tickets/${state.workspace.ticket_id}`)
      await page.getByRole('heading', { name: 'Customer message' }).waitFor({ state: 'visible' })
      const sendCount = await page.getByRole('button', { name: 'Send reply', exact: true }).count()
      const proposalCount = await page.getByRole('button', { name: 'Submit for approval', exact: true }).count()
      const escalateVisible = await page.getByRole('button', { name: 'Escalate ticket', exact: true }).isVisible()
      if (sendCount !== 0 || proposalCount !== 0 || !escalateVisible) {
        throw new Error(`Unexpected buttons: send=${sendCount}, proposal=${proposalCount}, escalate=${escalateVisible}`)
      }
      await page.getByRole('button', { name: 'Escalate ticket', exact: true }).click()
      await page.getByRole('dialog').waitFor({ state: 'visible' })
      await page.getByRole('dialog').getByRole('group', { name: 'Reasons' }).getByRole('button').first().click()
      await page.getByRole('dialog').getByRole('button', { name: 'Escalate ticket', exact: true }).click()
      await page.waitForTimeout(150)
      const postPaths = calls.filter(c => c.method === 'POST').map(c => c.path)
      if (!postPaths.includes(`/v1/console/tickets/${state.workspace.ticket_id}/escalations`) || postPaths.some(p => p.endsWith('/replies') || p.endsWith('/reply-proposals'))) {
        throw new Error(`Unexpected POST paths: ${JSON.stringify(postPaths)}`)
      }
      const visual = await checkVisualHealth(page, 'P1-contradictory-admin-escalate-only')
      return { postPaths, visual }
    })

    // P2: Absent / null / non-array / empty allowed_actions fail closed even for admin
    for (const [label, allowed] of [
      ['absent', '__ABSENT__'],
      ['null', null],
      ['non-array-string', 'send_reply'],
      ['empty', []],
    ]) {
      await runSynthetic(`P2-fail-closed-${label}`, async page => {
        const state = makeWorkspacePayload({
          actor: { account_id: 'acc-admin-1', display_name: 'Minh Le', role: 'admin' },
          allowed_actions: allowed,
        })
        const calls = await setupSyntheticScenario(page, () => state)
        await page.goto(`${BASE_URL}/console/tickets/${state.workspace.ticket_id}`)
        await page.getByRole('heading', { name: 'Customer message' }).waitFor({ state: 'visible' })
        const waitText = await page.getByText('This ticket is waiting on an administrator.', { exact: true }).isVisible()
        const sendCount = await page.getByRole('button', { name: 'Send reply', exact: true }).count()
        const propCount = await page.getByRole('button', { name: 'Submit for approval', exact: true }).count()
        const escCount = await page.getByRole('button', { name: 'Escalate ticket', exact: true }).count()
        const postCalls = calls.filter(c => c.method === 'POST' && !c.path.endsWith('/views'))
        if (!waitText || sendCount !== 0 || propCount !== 0 || escCount !== 0 || postCalls.length !== 0) {
          throw new Error(`Failed closed violation (${label}): waitText=${waitText} send=${sendCount} prop=${propCount} esc=${escCount} posts=${postCalls.length}`)
        }
        return { label, waitText, zeroPosts: true }
      })
    }

    // P3: Pending AI draft prevents sending even if allowed_actions includes send_reply
    await runSynthetic('P3-ai-pending-safety', async page => {
      const state = makeWorkspacePayload({
        actor: { account_id: 'acc-staff-1', display_name: 'Mai Nguyen', role: 'staff' },
        allowed_actions: ['send_reply', 'correct_intent'],
        analysis_status: 'pending',
        draft_status: 'pending',
        draftText: null,
      })
      const calls = await setupSyntheticScenario(page, () => state)
      await page.goto(`${BASE_URL}/console/tickets/${state.workspace.ticket_id}`)
      await page.getByRole('heading', { name: 'Customer message' }).waitFor({ state: 'visible' })
      const pendingVisible = await page.getByText('The AI is still working on this ticket.', { exact: true }).isVisible()
      const sendDisabled = await page.getByRole('button', { name: 'Send reply', exact: true }).isDisabled()
      if (!pendingVisible || !sendDisabled || calls.some(c => c.method === 'POST' && !c.path.endsWith('/views'))) {
        throw new Error(`Pending safety failed: pendingVisible=${pendingVisible}, sendDisabled=${sendDisabled}`)
      }
      return { pendingVisible, sendDisabled, zeroPosts: true }
    })

    // P4: Closed & own-proposal awaiting_approval fail closed
    await runSynthetic('P4-closed-and-own-proposal-fail-closed', async page => {
      const stateClosed = makeWorkspacePayload({
        ticketId: 'TCK-CLOSED-1',
        status: 'closed',
        allowed_actions: [],
        reply: { body: 'Sent earlier.', by: 'Minh Le', sent_at: '2026-11-15T09:10:00Z' },
      })
      const callsClosed = await setupSyntheticScenario(page, () => stateClosed)
      await page.goto(`${BASE_URL}/console/tickets/${stateClosed.workspace.ticket_id}`)
      await page.getByRole('heading', { name: 'Sent reply' }).waitFor({ state: 'visible' })
      if ((await page.getByRole('button', { name: 'Send reply', exact: true }).count()) !== 0 || callsClosed.some(c => c.method === 'POST' && !c.path.endsWith('/views'))) {
        throw new Error('Closed ticket should not expose Send reply or POST')
      }

      const stateOwnProp = makeWorkspacePayload({
        ticketId: 'TCK-OWN-PROP-1',
        status: 'awaiting_approval',
        actor: { account_id: 'acc-staff-1', display_name: 'Mai Nguyen', role: 'staff' },
        allowed_actions: [],
        is_authority_required: true,
        proposal: {
          proposal_id: 'PROP-1',
          body: 'My own proposal',
          basis: 'reply_proposal',
          by: 'Mai Nguyen',
          created_at: '2026-11-15T09:05:00Z',
        },
      })
      await page.unrouteAll()
      const callsOwn = await setupSyntheticScenario(page, () => stateOwnProp)
      await page.goto(`${BASE_URL}/console/tickets/${stateOwnProp.workspace.ticket_id}`)
      await page.getByText('Awaiting approval', { exact: false }).first().waitFor({ state: 'visible' })
      const waitingAdmin = await page.getByText('This ticket is waiting on an administrator.', { exact: true }).isVisible()
      const sendCount = await page.getByRole('button', { name: 'Send reply', exact: true }).count()
      const propCount = await page.getByRole('button', { name: 'Submit for approval', exact: true }).count()
      if (!waitingAdmin || sendCount !== 0 || propCount !== 0 || callsOwn.some(c => c.method === 'POST' && !c.path.endsWith('/views'))) {
        throw new Error(`Own proposal fail-closed failed: waitingAdmin=${waitingAdmin} send=${sendCount} prop=${propCount}`)
      }
      return { closedSafe: true, ownProposalSafe: true }
    })

    // P5: Dynamic permission revocation between modal open and confirm!
    await runSynthetic('P5-dynamic-revocation-between-modal-open-and-confirm', async page => {
      let currentState = makeWorkspacePayload({
        actor: { account_id: 'acc-staff-1', display_name: 'Mai Nguyen', role: 'staff' },
        allowed_actions: ['send_reply', 'correct_intent'],
      })
      const calls = await setupSyntheticScenario(page, () => currentState)
      await page.goto(`${BASE_URL}/console/tickets/${currentState.workspace.ticket_id}`)
      await page.getByRole('button', { name: 'Send reply', exact: true }).click()
      await page.getByRole('dialog').waitFor({ state: 'visible' })
      await page.screenshot({ path: join(OUT_DIR, 'modal-open-before-revocation.png'), fullPage: true, animations: 'disabled' })

      // Revoke send_reply in the authoritative backend payload & wait for the 10s workspace refetchInterval poll
      currentState = makeWorkspacePayload({
        actor: currentState.actor,
        allowed_actions: ['correct_intent'],
      })
      await page.getByRole('dialog').waitFor({ state: 'hidden', timeout: 12500 })
      const sendAfter = await page.getByRole('button', { name: 'Send reply', exact: true }).count()
      const replyPosts = calls.filter(c => c.method === 'POST' && c.path.endsWith('/replies'))
      if (sendAfter !== 0 || replyPosts.length !== 0) {
        throw new Error(`Dynamic revocation failed: sendAfter=${sendAfter}, replyPosts=${replyPosts.length}`)
      }
      await page.screenshot({ path: join(OUT_DIR, 'modal-closed-after-revocation.png'), fullPage: true, animations: 'disabled' })
      const visual = await checkVisualHealth(page, 'P5-after-revocation')
      return { modalAutoClosed: true, sendCountAfter: sendAfter, replyPosts: replyPosts.length, visual }
    })

    // P6: Legitimate manual (no_ai_draft)
    await runSynthetic('P6-legitimate-manual-no-ai-draft', async page => {
      const state = makeWorkspacePayload({
        actor: { account_id: 'acc-staff-1', display_name: 'Mai Nguyen', role: 'staff' },
        allowed_actions: ['send_reply'],
        analysis_status: 'ready',
        draft_status: 'llm_unavailable',
        draftText: null,
      })
      const calls = await setupSyntheticScenario(page, () => state)
      await page.goto(`${BASE_URL}/console/tickets/${state.workspace.ticket_id}`)
      await page.getByLabel('Reply to customer').fill('Thank you. We checked your order and the refund is processing.')
      await page.getByRole('button', { name: 'Send reply', exact: true }).click()
      await page.getByRole('dialog').getByRole('button', { name: 'Send reply', exact: true }).click()
      await page.waitForTimeout(150)
      const replyPost = calls.find(c => c.method === 'POST' && c.path.endsWith('/replies'))
      if (!replyPost || replyPost.body?.basis !== 'no_ai_draft') {
        throw new Error(`Expected no_ai_draft POST, got ${JSON.stringify(replyPost)}`)
      }
      return { postBody: replyPost.body }
    })

    // P7: Legitimate staff Submit for approval (reply-proposals)
    await runSynthetic('P7-legitimate-staff-submit-proposal', async page => {
      const state = makeWorkspacePayload({
        actor: { account_id: 'acc-staff-1', display_name: 'Mai Nguyen', role: 'staff' },
        allowed_actions: ['submit_reply_proposal', 'escalate'],
        is_authority_required: true,
      })
      const calls = await setupSyntheticScenario(page, () => state)
      await page.goto(`${BASE_URL}/console/tickets/${state.workspace.ticket_id}`)
      if ((await page.getByRole('button', { name: 'Send reply', exact: true }).count()) !== 0) {
        throw new Error('Staff on authority-required ticket should not see Send reply')
      }
      await page.screenshot({ path: join(OUT_DIR, 'staff-submit-for-approval.png'), fullPage: true, animations: 'disabled' })
      await page.getByRole('button', { name: 'Submit for approval', exact: true }).click()
      await page.getByRole('dialog').getByRole('button', { name: 'Submit for approval', exact: true }).click()
      await page.waitForTimeout(150)
      const propPost = calls.find(c => c.method === 'POST' && c.path.endsWith('/reply-proposals'))
      if (!propPost || propPost.body?.basis !== 'ai_draft') {
        throw new Error(`Expected reply-proposals POST with ai_draft basis, got ${JSON.stringify(propPost)}`)
      }
      const visual = await checkVisualHealth(page, 'P7-staff-submit-for-approval')
      return { postBody: propPost.body, visual }
    })

    // P8: Legitimate cross-person admin approval (reply_proposal)
    await runSynthetic('P8-legitimate-cross-person-admin-approval', async page => {
      const state = makeWorkspacePayload({
        status: 'awaiting_approval',
        actor: { account_id: 'acc-admin-1', display_name: 'Minh Le', role: 'admin' },
        allowed_actions: ['send_reply'],
        is_authority_required: true,
        proposal: {
          proposal_id: 'PROP-1',
          body: 'Staff proposed refund confirmation.',
          basis: 'reply_proposal',
          by: 'Mai Nguyen',
          created_at: '2026-11-15T09:05:00Z',
        },
      })
      const calls = await setupSyntheticScenario(page, () => state)
      await page.goto(`${BASE_URL}/console/tickets/${state.workspace.ticket_id}`)
      await page.getByText('Mai Nguyen', { exact: false }).waitFor({ state: 'visible' })
      await page.screenshot({ path: join(OUT_DIR, 'admin-cross-person-approval.png'), fullPage: true, animations: 'disabled' })
      await page.getByRole('button', { name: 'Send reply', exact: true }).click()
      await page.getByRole('dialog').getByRole('button', { name: 'Send reply', exact: true }).click()
      await page.waitForTimeout(150)
      const replyPost = calls.find(c => c.method === 'POST' && c.path.endsWith('/replies'))
      if (!replyPost || replyPost.body?.basis !== 'reply_proposal') {
        throw new Error(`Expected admin reply_proposal POST, got ${JSON.stringify(replyPost)}`)
      }
      const visual = await checkVisualHealth(page, 'P8-admin-cross-person-approval')
      return { postBody: replyPost.body, visual }
    })

    const summary = {
      verdict: 'PASS',
      total_cases: results.length,
      passed: results.filter(r => r.status === 'PASS').length,
      failed: results.filter(r => r.status !== 'PASS').length,
      results,
    }
    writeFileSync(join(OUT_DIR, 'playwright_permission_verification.json'), JSON.stringify(summary, null, 2))
    console.log(JSON.stringify(summary, null, 2))
  } finally {
    await browser.close()
  }
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
