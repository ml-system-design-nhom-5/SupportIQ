// Authenticate a real inspector browser without exposing credentials or adding an application bypass.
import {readFileSync} from 'node:fs'
import {resolve} from 'node:path'
import {pathToFileURL} from 'node:url'

const skillRoot = process.env.SUPPORTIQ_TASTE_SKILL || 'C:/Users/PC/.agents/skills/design-taste-frontend'
const local = JSON.parse(readFileSync(resolve('.local/application.json'),'utf8'))
const role = process.argv[2] || 'staff'
const route = process.argv[3] || '/console'
const out = process.argv[4] || `.taste-skill/${role}`
const base = 'http://127.0.0.1:8080'
const response = await fetch(`${base}/v1/sessions`, {method:'POST',headers:{'Origin':base,'Content-Type':'application/json'},body:JSON.stringify({login_name:role+'-1',password:local.passwords[role]})})
if (!response.ok) throw new Error(`Inspector sign-in failed (${response.status})`)
const session = response.headers.getSetCookie().find(value => value.startsWith('supportiq_session='))?.split(';')[0].slice('supportiq_session='.length)
if (!session) throw new Error('Session cookie was not issued')
const {Browser} = await import(pathToFileURL(resolve(skillRoot,'scripts/lib/cdp.mjs')).href)
const original = Browser.prototype.newPage
Browser.prototype.newPage = async function (...args) {
  const page = await original.apply(this,args)
  await page.send('Network.setCookie',{name:'supportiq_session',value:session,url:base,httpOnly:true,sameSite:'Lax'})
  return page
}
process.argv = [process.execPath,resolve(skillRoot,'scripts/inspect.mjs'),base+route,'--app','--out',out,'--allow','palette-purple,monospace']
await import(pathToFileURL(resolve(skillRoot,'scripts/inspect.mjs')).href)
