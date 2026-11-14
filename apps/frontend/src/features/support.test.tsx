import {afterEach, expect, it, vi} from 'vitest'
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react'
import {MemoryRouter, Route, Routes} from 'react-router-dom'
import {SupportHome} from './support'
import {post} from '../api'

vi.mock('../api', () => ({api: vi.fn(), post: vi.fn()}))
afterEach(() => {cleanup(); vi.clearAllMocks()})

it.each([
  ['/shop/support?order_id=ORD-OWNED', 'ORD-OWNED'],
  ['/shop/support', null],
])('preserves order context and opens the created ticket from %s', async (path, orderId) => {
  vi.mocked(post).mockResolvedValue({ticket_id:'TCK-NEW', order_id:orderId})
  render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/shop/support" element={<SupportHome/>}/>
    <Route path="/shop/support/TCK-NEW" element={<h1>Created ticket</h1>}/>
  </Routes></MemoryRouter>)
  fireEvent.change(screen.getByLabelText('Your message'), {target:{value:'Please check my delivery.'}})
  fireEvent.click(screen.getByRole('button', {name:'Send request'}))
  await waitFor(() => expect(post).toHaveBeenCalledWith('/v1/shop/tickets',
    {message:'Please check my delivery.', order_id:orderId}, expect.any(String)))
  await screen.findByRole('heading', {name:'Created ticket'})
})
