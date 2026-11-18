import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const base = '/administration/entreprises/a';
function show(path: string) { return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function json(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } }); }
type TestOrder = Record<string, unknown> & { lines: Record<string, unknown>[]; approval: Record<string, unknown>; approval_requests: Record<string, unknown>[] };
function server({ approval = false, seeded = false, manage = true }: { approval?: boolean; seeded?: boolean; manage?: boolean } = {}) {
  const orders: Record<string, TestOrder> = {};
  const rules: Record<string, unknown>[] = [];
  const makeOrder = (body: Record<string, unknown>, domain: string): TestOrder => ({ ...body, id: 'order', reference: domain === 'sales' ? 'CMD-000001' : 'ACH-000001', status: 'draft', version: 1, partner_id: 'partner', partner_name: 'Client fournisseur', warehouse_id: 'warehouse', warehouse_name: 'Principal', notes: '', order_date: '2026-11-16', currency_code: 'EUR', untaxed_amount: '1.010000', tax_amount: '0.200000', total_amount: '1.210000', allowed_actions: manage ? approval ? ['edit', 'submit', 'cancel'] : ['edit', 'confirm', 'cancel'] : [], approval: { required: approval, approved: !approval, approver_role_name: approval ? 'Direction' : null }, lines: ((body.lines || [{ product_id: 'product', quantity: '3', unit_price: '0.335000', discount_rate: '0', tax_rate: '20' }]) as Record<string, unknown>[]).map(line => ({ id: 'line', product_name: 'Article', product_type: 'stockable', unit_name: 'Unité', description: 'Article', line_total: '1.005000000000', reserved_quantity: '0.000000', waiting_quantity: '0.000000', ...line })), reservations: [], approval_requests: [] });
  if (seeded) orders.sales = makeOrder({}, 'sales');
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'user', full_name: 'Alice', email: 'alice@example.com' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Société', currency_code: 'EUR' }]);
    if (path.endsWith('/context/')) return json({ company: { id: 'a', name: 'Société', currency_code: 'EUR' }, permissions: ['company.view', 'sales.order.view', 'purchases.order.view', 'crm.view', ...(manage ? ['crm.manage', 'sales.order.create', 'sales.order.edit', 'sales.order.confirm', 'sales.order.submit', 'sales.order.cancel', 'purchases.order.create', 'purchases.order.edit', 'approvals.rules.view', 'approvals.rules.manage', 'approvals.requests.view', 'approvals.requests.decide'] : [])], modules: ['core', 'sales', 'purchases', 'crm'] });
    if (path.endsWith('/crm/leads/lead/')) return json({ id: 'lead', title: 'Opportunité Alpha', partner_id: 'partner', partner_name: 'Client fournisseur', partner_is_customer: true, owner_name: 'Alice', expected_revenue: '1.21', probability: 50, stage: 'qualified' });
    if (path.includes('/crm/activities/?')) return json({ count: 0, results: [] });
    if (path.includes('/history/')) return json({ count: 0, results: [] });
    if (path.endsWith('/approvals/lookups/')) return json({ roles: [{ id: 'role', name: 'Direction', has_active_members: true }] });
    if (path.includes('/approvals/rules/')) {
      if (init?.method === 'POST') { const row = { id: 'rule', version: 1, approver_role_name: 'Direction', ...body }; if (path.includes('/update/')) rules[0] = row; else rules.push(row); return json(row); }
      return json({ count: rules.length, results: rules });
    }
    if (path.endsWith('/approvals/requests/request/decide/')) {
      const order = orders.sales; order.approval.approved = body.decision === 'approved'; order.status = 'draft'; order.allowed_actions = ['edit', body.decision === 'approved' ? 'confirm' : 'submit', 'cancel']; order.approval_requests[0].status = body.decision;
      order.approval_requests[0].can_decide = false; order.approval_requests[0].decision = { decision: body.decision, actor: 'Alice', comment: body.comment };
      return json({ decision: body.decision });
    }
    const match = path.match(/\/(sales|purchases)\/(.*)/);
    if (match) {
      const [, domain, suffix] = match;
      if (suffix.startsWith('lookups/')) return json({ partners: [{ id: 'partner', name: 'Client fournisseur' }], products: [{ id: 'product', sku: 'ART', name: 'Article', description: 'Article', unit_name: 'Unité', type: 'stockable', unit_price: domain === 'sales' ? '0.335000' : '0.200000', tax_rate: '20.0000' }], warehouses: [{ id: 'warehouse', name: 'Principal', code: 'MAIN' }] });
      if (suffix === 'orders/' && init?.method === 'POST') { orders[domain] = makeOrder(body, domain); return json(orders[domain]); }
      if (suffix.startsWith('orders/?')) return json({ count: orders[domain] ? 1 : 0, results: orders[domain] ? [orders[domain]] : [] });
      const order = orders[domain];
      if (suffix === 'orders/order/') return json(order);
      if (suffix === 'orders/order/confirm/') { order.status = 'confirmed'; order.allowed_actions = ['cancel', ...(domain === 'sales' ? ['reserve'] : [])]; order.lines[0].reserved_quantity = '2.000000'; order.lines[0].waiting_quantity = '1.000000'; return json(order); }
      if (suffix === 'orders/order/cancel/') { order.status = 'cancelled'; order.allowed_actions = []; return json(order); }
      if (suffix === 'orders/order/submit/') { order.status = 'pending_approval'; order.allowed_actions = ['reopen', 'cancel']; order.approval_requests = [{ id: 'request', reference: order.reference, document_type: 'sales_order', document_id: 'order', document_version: 1, status: 'pending', total_amount: order.total_amount, currency_code: 'EUR', approver_role_name: 'Direction', can_decide: true, decision: null }]; return json(order); }
    }
    throw new Error(`Requête imprévue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => { localStorage.clear(); vi.spyOn(window, 'confirm').mockReturnValue(true); });
async function fillOrder() {
  await screen.findByRole('option', { name: 'ART — Article' });
  await userEvent.selectOptions(screen.getByLabelText('Client'), 'partner');
  await userEvent.selectOptions(screen.getByLabelText('Produit 1'), 'product');
  const quantity = screen.getByLabelText('Quantité 1'); await userEvent.clear(quantity); await userEvent.type(quantity, '3');
}
describe('Commandes et approbations connectées', () => {
  it('crée un devis exact, confirme et affiche les réservations renvoyées par le serveur', async () => {
    const fetch = server(); show(base + '/ventes/nouveau'); await fillOrder();
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le brouillon' }));
    expect(await screen.findByRole('heading', { name: 'CMD-000001' })).toBeInTheDocument();
    const creation = fetch.mock.calls.find(([path, init]) => path.endsWith('/sales/orders/') && init?.method === 'POST')!;
    expect(JSON.parse(creation[1]!.body as string).lines[0].unit_price).toBe('0.335000');
    await userEvent.click(screen.getByRole('button', { name: 'Confirmer la commande' }));
    expect(await screen.findByText('Confirmée')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirmer la commande' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Réserver le stock manquant' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Annuler le document' }));
    expect(await screen.findByText('Annulée')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path, init]) => path.endsWith('/confirm/') && JSON.parse(init!.body as string).version === 1)).toBe(true);
  });
  it('soumet, approuve une version avec commentaire puis autorise la confirmation', async () => {
    const fetch = server({ seeded: true, approval: true }); show(base + '/ventes/order');
    expect(await screen.findByRole('button', { name: 'Soumettre à approbation' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Confirmer la commande' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Soumettre à approbation' }));
    await userEvent.type(await screen.findByLabelText('Commentaire de décision'), 'Budget validé');
    await userEvent.click(screen.getByRole('button', { name: 'Approuver' }));
    expect(await screen.findByRole('button', { name: 'Confirmer la commande' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path, init]) => path.endsWith('/decide/') && JSON.parse(init!.body as string).comment === 'Budget validé')).toBe(true);
  });
  it('crée une commande fournisseur avec le coût réel proposé par le catalogue', async () => {
    const fetch = server(); show(base + '/achats/nouveau');
    await screen.findByRole('option', { name: 'ART — Article' });
    await userEvent.selectOptions(screen.getByLabelText('Fournisseur'), 'partner');
    await userEvent.selectOptions(screen.getByLabelText('Produit 1'), 'product');
    expect(screen.getByLabelText('Prix unitaire 1')).toHaveValue('0.200000');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le brouillon' }));
    expect(await screen.findByRole('heading', { name: 'ACH-000001' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path, init]) => path.endsWith('/purchases/orders/') && init?.method === 'POST')).toBe(true);
  });
  it('crée puis désactive une règle sans la supprimer', async () => {
    const fetch = server(); show(base + '/regles-approbation');
    await screen.findByRole('option', { name: 'Direction' });
    await userEvent.selectOptions(screen.getByLabelText('Rôle approbateur'), 'role');
    await userEvent.type(screen.getByLabelText('Maximum exclu (vide = sans plafond)'), '500000');
    await userEvent.click(screen.getByRole('button', { name: 'Créer la règle' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Modifier' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'Règle active' }));
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer la règle' }));
    expect(await screen.findByRole('cell', { name: 'Inactive' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path, init]) => path.endsWith('/rule/update/') && JSON.parse(init!.body as string).active === false)).toBe(true);
  });
  it('relie une opportunité client au formulaire de devis', async () => {
    const fetch = server(); show(base + '/crm/lead');
    await userEvent.click(await screen.findByRole('link', { name: 'Créer un devis' }));
    await screen.findByRole('option', { name: 'ART — Article' });
    expect(screen.getByLabelText('Client')).toHaveValue('partner');
    await userEvent.selectOptions(screen.getByLabelText('Produit 1'), 'product');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le brouillon' }));
    expect(await screen.findByRole('heading', { name: 'CMD-000001' })).toBeInTheDocument();
    const creation = fetch.mock.calls.find(([path, init]) => path.endsWith('/sales/orders/') && init?.method === 'POST')!;
    expect(JSON.parse(creation[1]!.body as string).lead_id).toBe('lead');
  });
  it('refuse le formulaire de création sans permission', async () => {
    const fetch = server({ manage: false }); show(base + '/ventes/nouveau');
    expect(await screen.findByRole('heading', { name: 'Accès non autorisé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/sales/'))).toBe(false);
  });
});
