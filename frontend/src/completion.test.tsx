import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import App from './App';

function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }); }
function setup({ blocked = false, rejected = false, canResume = true } = {}) {
  const order = { id: 'order', reference: 'CMD-CLOSE', version: 1, closure_version: 0, completed_at: null as string | null, status: 'confirmed', partner_name: 'Client', warehouse_name: 'Principal', order_date: '2026-11-17', notes: '', currency_code: 'EUR', untaxed_amount: '80', tax_amount: '16', total_amount: '96', fulfillment_status: 'done', approval: { required: false, approved: true, approver_role_name: null }, lines: [], reservations: [], approval_requests: [], allowed_actions: blocked ? [] : ['complete'], completion: { eligible: !blocked, reasons: blocked ? ['Toutes les factures liées doivent être intégralement réglées.'] : [] } };
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'user', email: 'test@example.invalid', full_name: 'Opérateur' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Société' }]);
    if (path.endsWith('/context/')) return json({ company: { id: 'a', name: 'Société' }, permissions: ['company.view', 'sales.order.view'], modules: ['core', 'sales'] });
    if (path.includes('/history/')) return json({ count: 0, results: [] });
    if (path.endsWith('/sales/orders/order/')) return json(order);
    if (path.endsWith('/complete/')) {
      if (rejected) return json({ detail: 'Une allocation vient d’être extournée.' }, 400);
      order.status = 'completed'; order.closure_version = 1; order.completed_at = '2026-11-17T12:00:00Z'; order.allowed_actions = canResume ? ['resume'] : []; order.completion.eligible = false; return json(order);
    }
    if (path.endsWith('/resume/')) { order.status = 'confirmed'; order.closure_version = 2; order.completed_at = null; order.allowed_actions = ['complete']; order.completion.eligible = true; return json(order); }
    throw new Error(`Requête inattendue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch);
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={['/administration/entreprises/a/ventes/order']}><App/></MemoryRouter></QueryClientProvider>);
  return fetch;
}
beforeEach(() => { localStorage.clear(); vi.spyOn(window, 'confirm').mockReturnValue(true); });

it('clôture, affiche la date et reprend avec motif et version de cycle', async () => {
  const fetch = setup();
  await userEvent.click(await screen.findByRole('button', { name: 'Clôturer la commande' }));
  expect(await screen.findByText('Terminée', { selector: 'header .status-badge' })).toBeInTheDocument();
  const close = fetch.mock.calls.find(([path]) => path.endsWith('/complete/'))!;
  expect(JSON.parse(close[1]!.body as string)).toEqual({ version: 1, closure_version: 0 });
  expect(screen.getByRole('button', { name: 'Reprendre la commande' })).toBeDisabled();
  await userEvent.type(screen.getByLabelText('Motif de reprise'), 'Correction après clôture');
  await userEvent.click(screen.getByRole('button', { name: 'Reprendre la commande' }));
  expect(await screen.findByRole('button', { name: 'Clôturer la commande' })).toBeInTheDocument();
  const resume = fetch.mock.calls.find(([path]) => path.endsWith('/resume/'))!;
  expect(JSON.parse(resume[1]!.body as string)).toEqual({ version: 1, closure_version: 1, reason: 'Correction après clôture' });
  await userEvent.click(screen.getByRole('button', { name: 'Clôturer la commande' }));
  expect(await screen.findByLabelText('Motif de reprise')).toHaveValue('');
  expect(screen.getByRole('button', { name: 'Reprendre la commande' })).toBeDisabled();
});
it('explique le règlement manquant sans proposer une clôture fictive', async () => {
  setup({ blocked: true });
  expect(await screen.findByText('Toutes les factures liées doivent être intégralement réglées.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Clôturer la commande' })).not.toBeInTheDocument();
});
it('affiche un refus serveur et conserve la commande confirmée', async () => {
  setup({ rejected: true });
  await userEvent.click(await screen.findByRole('button', { name: 'Clôturer la commande' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Une allocation vient d’être extournée.');
  expect(screen.getByText('Confirmée')).toBeInTheDocument();
});
it('ne propose pas la reprise si le serveur ne l’autorise pas', async () => {
  setup({ canResume: false });
  await userEvent.click(await screen.findByRole('button', { name: 'Clôturer la commande' }));
  expect(await screen.findByText('Terminée', { selector: 'header .status-badge' })).toBeInTheDocument();
  expect(screen.queryByLabelText('Motif de reprise')).not.toBeInTheDocument();
});
