import { test, expect, type Page } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { readFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(process.cwd(),'../..')
const credentials = JSON.parse(readFileSync(resolve(root,'.local/application.json'),'utf8')) as {passwords: Record<string,string>}
const output = resolve(root,'.impeccable/review')
mkdirSync(output,{recursive:true})

async function signIn(page: Page, role: string) {
  await page.goto('/sign-in')
  await page.getByLabel('Login name').fill(`${role}-1`)
  await page.getByLabel('Password', {exact: true}).fill(credentials.passwords[role])
  await page.getByRole('button',{name:'Sign in',exact:true}).click()
  await expect(page.getByRole('button',{name:'Sign out'})).toBeVisible()
}
async function signOut(page: Page) {
  await page.getByRole('button',{name:'Sign out'}).click()
  await expect(page.getByRole('heading',{name:'Sign in to SupportIQ'})).toBeVisible()
}
async function capture(page: Page, name: string, project: string) {
  await page.evaluate(() => document.fonts.ready)
  await page.screenshot({path:resolve(output,`${name}-${project}.png`),fullPage:true,animations:'disabled'})
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false)
  const results = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze()
  expect(results.violations.map(violation => ({id:violation.id, description:violation.description, nodes:violation.nodes.map(node => node.target)}))).toEqual([])
}

test('customer request, human reply and customer receipt', async ({page}, testInfo) => {
  await page.goto('/sign-in')
  await capture(page,'sign-in',testInfo.project.name)
  await signIn(page,'customer')
  await expect(page.getByRole('heading',{name:'Products',exact:true})).toBeVisible()
  await capture(page,'products',testInfo.project.name)
  await page.getByRole('link',{name:'My orders',exact:true}).first().click()
  await expect(page.getByRole('heading',{name:'My orders',exact:true})).toBeVisible()
  await capture(page,'orders',testInfo.project.name)
  await page.goto('/shop/orders/ORD-1001')
  await page.getByRole('button',{name:'Contact support',exact:true}).click()
  await expect(page.getByLabel('Write to support about this order')).toBeFocused()
  await expect(page.getByRole('button',{name:'Send message'})).toBeDisabled()
  const message = `Please check the delivery of my package. Review ${testInfo.project.name} ${Date.now()}.`
  await page.getByLabel('Write to support about this order').fill(message)
  await page.getByRole('button',{name:'Send message'}).click()
  await expect(page.getByRole('status').filter({hasText:'Message sent.'})).toBeVisible()
  await capture(page,'order-received',testInfo.project.name)
  const ticketId = await page.locator('.ticket-thread').filter({hasText:message}).locator('.thread-heading .identifier').innerText()
  await signOut(page)
  await signIn(page,'staff')
  await page.goto(`/console/tickets/${ticketId}`)
  await expect(page.getByRole('heading',{name:'Customer message'})).toBeVisible()
  await expect(page.getByLabel('Reply to customer')).toBeVisible()
  await capture(page,'console',testInfo.project.name)
  const reply = 'I have checked the order records. Your package is in transit with GHN Express.'
  await page.getByLabel('Reply to customer').fill('Hello [NAME_1]')
  await expect(page.getByRole('button',{name:'Send reply',exact:true})).toBeDisabled()
  await page.getByLabel('Reply to customer').fill(reply)
  await page.getByRole('button',{name:'Send reply',exact:true}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.getByRole('dialog').getByRole('button',{name:'Send reply',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Sent reply'})).toBeVisible()
  await signOut(page)
  await signIn(page,'customer')
  await page.goto(`/shop/orders/ORD-1001#${ticketId}`)
  await expect(page.locator(`#${ticketId}`).getByText(reply,{exact:true})).toBeVisible()
  await expect(page.locator(`#${ticketId}`).getByText('Replied',{exact:true})).toBeVisible()
  await capture(page,'order-replied',testInfo.project.name)
})

test('admin confirmations, versions and manager reports', async ({page}, testInfo) => {
  await signIn(page,'admin')
  await expect(page.getByRole('heading',{name:'Internal accounts'})).toBeVisible()
  await capture(page,'accounts',testInfo.project.name)
  await page.getByRole('button',{name:'Make manager',exact:true}).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await capture(page,'account-confirmation',testInfo.project.name)
  await page.getByRole('button',{name:'Cancel',exact:true}).click()
  await page.getByRole('link',{name:'Versions',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Versions in use'})).toBeVisible()
  await expect(page.getByText('Backend build',{exact:true})).toBeVisible()
  await capture(page,'versions',testInfo.project.name)
  await signOut(page)
  await signIn(page,'manager')
  await page.getByRole('link',{name:'Reports',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Support reports'})).toBeVisible()
  await expect(page.getByText('Tickets created',{exact:true})).toBeVisible()
  await capture(page,'reports',testInfo.project.name)
})


test('general support without an order', async ({page},testInfo) => {
  await signIn(page,'customer')
  await page.goto('/shop/support')
  await expect(page.getByRole('heading',{name:'How can we help?'})).toBeVisible()
  await capture(page,'general-support',testInfo.project.name)
  await page.getByLabel('Your message').fill('What is your return policy?')
  await expect(page.getByLabel('Your message')).toHaveValue('What is your return policy?')
  await page.getByRole('button',{name:'Send request',exact:true}).click()
  await expect(page.getByRole('heading',{name:'Support request',exact:true})).toBeVisible()
  await expect(page.getByText('What is your return policy?',{exact:true})).toBeVisible()
  await capture(page,'general-request',testInfo.project.name)
  await page.getByRole('link',{name:'Your requests',exact:true}).click()
  await expect(page.getByText('General support',{exact:true}).first()).toBeVisible()
})
