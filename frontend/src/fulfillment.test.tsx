import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FulfillmentPanel } from './pages/fulfillment';
import type { Order, OrderDomain } from './pages/orders';
import { api, companyKey } from './api';

function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }); }
function server({ domain = 'purchases', reject = false, readonly = false }: { domain?: OrderDomain; reject?: boolean; readonly?: boolean } = {}) {
  const kind = domain === 'sales' ? 'deliveries' : 'receipts'; const code = domain === 'sales' ? 'delivery' : 'receipt';
  const order = { id: 'order', status: 'confirmed', version: 1, fulfillment_status: 'not_started', lines: [{ id: 'line', product_name: 'Article', product_type: 'stockable', unit_name: 'Unité', quantity: '5.000000', fulfilled_quantity: '0.000000', remaining_quantity: '5.000000' }] };
  const documents: { id: string; reference: string; status: string; location_name: string; notes: string; validated_at: string | null; allowed_actions: string[]; lines: Record<string, string>[] }[] = [];
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/order/')) return json(order);
    if (path.includes('/lookups/')) return json({ locations: [{ id: 'location', name: 'MAIN / Stock' }] });
    if (path.includes(`/${kind}/?`)) return json({ count: documents.length, results: documents });
    if (path.endsWith(`/${kind}/`) && init?.method === 'POST') {
      documents.push({ id: 'document', reference: domain === 'sales' ? 'LIV-000001' : 'REC-000001', status: 'draft', location_name: 'MAIN / Stock', notes: body.notes, validated_at: null, allowed_actions: ['validate', 'cancel'], lines: body.lines.map((line: Record<string, string>) => ({ ...line, id: 'document-line', product_name: 'Article', unit_name: 'Unité', product_type: 'stockable' })) });
      return json(documents[0], 201);
    }
    if (path.endsWith('/validate/')) {
      if (reject) return json({ detail: 'Stock réservé insuffisant à cet emplacement.' }, 400);
      documents[0].status = 'validated'; documents[0].validated_at = '2026-11-17T10:00:00Z'; documents[0].allowed_actions = [];
      order.fulfillment_status = 'partial'; order.lines[0].fulfilled_quantity = documents[0].lines[0].quantity; order.lines[0].remaining_quantity = '3.000000';
      return json(documents[0]);
    }
    if (path.endsWith('/cancel/')) { documents[0].status = 'cancelled'; documents[0].allowed_actions = []; return json(documents[0]); }
    throw new Error(`Requête imprévue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch);
  const permissions = [`${domain}.order.view`, `inventory.${code}.view`, ...(readonly ? [] : [`inventory.${code}.create`, `inventory.${code}.validate`, `inventory.${code}.cancel`])];
  return { fetch, domain, context: { companyId: 'a', context: { permissions, modules: ['inventory', domain], company: { id: 'a' } } } };
}
function show(value: ReturnType<typeof server>) {
  function Page() {
    const order = useQuery({ queryKey: [...companyKey('a', `${value.domain}-orders`), 'order'], queryFn: () => api<Order>(`companies/a/${value.domain}/orders/order/`) });
    return order.data ? <FulfillmentPanel order={order.data} domain={value.domain}/> : <p>Chargement de commande</p>;
  }
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><Routes><Route element={<Outlet context={value.context}/>}><Route path="/" element={<Page/>}/></Route></Routes></MemoryRouter></QueryClientProvider>);
}
beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true); });
describe('Exécution partielle connectée', () => {
  it('crée une réception exacte puis valide et recharge le restant', async () => {
    const value = server(); show(value);
    await screen.findByRole('option', { name: 'MAIN / Stock' });
    await userEvent.type(screen.getByLabelText('Article — quantité à recevoir'), '2.000000');
    await userEvent.click(screen.getByRole('button', { name: 'Créer le brouillon de réception' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Valider REC-000001' }));
    await waitFor(() => expect(screen.getByText(/Exécution : Partielle/)).toBeInTheDocument());
    expect(screen.getByText(/Reçu : 2 · Restant : 3/)).toBeInTheDocument();
    const creation = value.fetch.mock.calls.find(([path, init]) => path.endsWith('/receipts/') && init?.method === 'POST')!;
    expect(JSON.parse(creation[1]!.body as string)).toMatchObject({ order_id: 'order', version: 1, location_id: 'location', lines: [{ order_line_id: 'line', quantity: '2.000000' }] });
    expect(screen.queryByRole('button', { name: 'Annuler REC-000001' })).not.toBeInTheDocument();
  });
  it('crée et valide une livraison en demandant confirmation', async () => {
    show(server({ domain: 'sales' }));
    await screen.findByRole('option', { name: 'MAIN / Stock' });
    await userEvent.type(screen.getByLabelText('Article — quantité à livrer'), '2');
    await userEvent.click(screen.getByRole('button', { name: 'Créer le brouillon de livraison' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Valider LIV-000001' }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('Valider LIV-000001'));
    expect(await screen.findByText(/Exécution : Partielle/)).toBeInTheDocument();
  });
  it('affiche le refus sans transformer le brouillon en livraison validée puis permet son annulation', async () => {
    show(server({ domain: 'sales', reject: true }));
    await screen.findByRole('option', { name: 'MAIN / Stock' });
    await userEvent.type(screen.getByLabelText('Article — quantité à livrer'), '2');
    await userEvent.click(screen.getByRole('button', { name: 'Créer le brouillon de livraison' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Valider LIV-000001' }));
    expect(await screen.findByText('Stock réservé insuffisant à cet emplacement.')).toBeInTheDocument();
    expect(screen.getByText('Brouillon · MAIN / Stock')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Annuler LIV-000001' }));
    expect(await screen.findByText('Annulé · MAIN / Stock')).toBeInTheDocument();
  });
  it('ne charge pas de formulaire ni de choix d’emplacement sans droit de création', async () => {
    const value = server({ readonly: true }); show(value);
    expect(await screen.findByText('Aucun document de réception.')).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: 'Nouvelle réception' })).not.toBeInTheDocument();
    expect(value.fetch.mock.calls.some(([path]) => path.includes('/lookups/'))).toBe(false);
  });
});
