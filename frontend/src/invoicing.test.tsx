import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const base = '/administration/entreprises/a';
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
type Row = Record<string, unknown> & { id: string; reference: string; status: string; allowed_actions: string[]; lines: Record<string, unknown>[] };
function show(path: string) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function server({ seeded = false, manage = true, enabled = true, reject = false, fullyBilled = false }: { seeded?: boolean; manage?: boolean; enabled?: boolean; reject?: boolean; fullyBilled?: boolean } = {}) {
  const invoices: Row[] = []; const credits: Row[] = [];
  const order = { id: 'order', reference: 'CMD-000001', status: 'confirmed', version: 1, partner_id: 'partner', partner_name: 'Client réel', warehouse_name: 'Principal', order_date: '2026-11-17', currency_code: 'EUR', total_amount: '1.21', untaxed_amount: '1.01', tax_amount: '.20', allowed_actions: [], approval: { required: false, approved: true }, approval_requests: [], reservations: [], lines: [{ id: 'order-line', product_id: 'product', product_name: 'Article', product_type: 'service', unit_name: 'Unité', description: 'Prestation', quantity: '3.000000', billable_quantity: fullyBilled ? '0.000000' : '3.000000', unit_price: '0.335000', discount_rate: '0', tax_rate: '20', line_total: '1.005' }] };
  const makeInvoice = (body: Record<string, unknown>, status = 'draft'): Row => ({ ...body, id: 'invoice', reference: 'FAC-000001', status, partner_id: 'partner', partner_name: 'Client réel', sales_order_id: body.sales_order_id || null, order_reference: body.sales_order_id ? 'CMD-000001' : null, currency_code: 'EUR', issue_date: '2026-11-17', due_date: '2026-12-17', untaxed_amount: '1.010000', tax_amount: '0.200000', total_amount: '1.210000', credited_amount: '0', net_amount: '1.21', notes: '', allowed_actions: status === 'draft' && manage ? ['validate', 'cancel'] : [], lines: [{ id: 'invoice-line', product_name: '', description: 'Prestation', unit_name: '', quantity: '3', unit_price: '0.335', discount_rate: '0', tax_rate: '20', line_total: '1.005', credited_quantity: '0', creditable_quantity: '3' }] });
  if (seeded) invoices.push(makeInvoice({}, 'validated'));
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'user', full_name: 'Alice', email: 'alice@example.com' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Société', currency_code: 'EUR' }]);
    if (path.endsWith('/context/')) return json({ company: { id: 'a', name: 'Société', currency_code: 'EUR' }, permissions: ['company.view', 'sales.order.view', 'invoicing.invoice.view', 'invoicing.credit_note.view', ...(manage ? ['invoicing.invoice.create', 'invoicing.invoice.validate', 'invoicing.invoice.cancel', 'invoicing.credit_note.create', 'invoicing.credit_note.validate'] : [])], modules: ['core', 'sales', ...(enabled ? ['invoicing'] : [])] });
    if (path.includes('/history/')) return json({ count: 0, results: [] });
    if (path.endsWith('/sales/orders/order/')) return json(order);
    if (path.includes('/invoicing/lookups/?order=')) return json({ order });
    if (path.includes('/invoicing/lookups/')) return json({ partners: [{ id: 'partner', name: 'Client réel' }], products: [{ id: 'product', name: 'Article', description: 'Prestation', unit_price: '0.335000', tax_rate: '20.0000' }] });
    if (path.includes('/invoicing/invoices/?')) return json({ count: invoices.length, results: invoices });
    if (path.includes('/invoicing/credit-notes/?')) return json({ count: credits.length, results: credits });
    if (path.endsWith('/invoicing/invoices/') && init?.method === 'POST') { invoices.push(makeInvoice(body)); return json(invoices[0], 201); }
    if (path.endsWith('/invoicing/credit-notes/') && init?.method === 'POST') {
      const row: Row = { ...body, id: 'credit', reference: 'AV-000001', status: 'draft', invoice_id: 'invoice', invoice_reference: 'FAC-000001', partner_name: 'Client réel', currency_code: 'EUR', untaxed_amount: '1.01', tax_amount: '.20', total_amount: '1.21', allowed_actions: ['validate'], lines: [{ id: 'credit-line', invoice_line_id: 'invoice-line', description: 'Prestation', quantity: '3', unit_name: '', amount: '1.005' }] };
      credits.push(row); return json(row, 201);
    }
    if (path.endsWith('/invoices/invoice/')) return json(invoices[0]);
    if (path.endsWith('/credit-notes/credit/')) return json(credits[0]);
    if (path.endsWith('/validate/')) {
      if (reject) return json({ detail: 'Quantité facturable dépassée.' }, 400);
      const row = path.includes('/credit-notes/') ? credits[0] : invoices[0]; row.status = 'validated'; row.allowed_actions = [];
      if (path.includes('/credit-notes/')) { invoices[0].credited_amount = '1.21'; invoices[0].net_amount = '0'; invoices[0].lines[0].credited_quantity = '3'; invoices[0].lines[0].creditable_quantity = '0'; }
      return json(row);
    }
    if (path.endsWith('/cancel/')) { invoices[0].status = 'cancelled'; invoices[0].allowed_actions = []; return json(invoices[0]); }
    throw new Error(`Requête imprévue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => { localStorage.clear(); vi.spyOn(window, 'confirm').mockReturnValue(true); });
async function fillDirect() {
  await screen.findByRole('option', { name: 'Client réel' });
  await userEvent.selectOptions(screen.getByLabelText('Client facturé'), 'partner');
  await userEvent.selectOptions(screen.getByLabelText('Produit facultatif 1'), 'product');
  const quantity = screen.getByLabelText('Quantité à facturer 1'); await userEvent.clear(quantity); await userEvent.type(quantity, '3');
}
describe('Factures et avoirs connectés', () => {
  it('masque la facturation sans quantité restante', async () => {
    server({ fullyBilled: true }); show(base + '/ventes/order');
    await screen.findByRole('heading', { name: 'CMD-000001' });
    expect(screen.queryByRole('link', { name: 'Facturer la commande' })).not.toBeInTheDocument();
  });
  it('crée une facture directe avec des chaînes exactes puis la valide', async () => {
    const fetch = server(); show(base + '/factures/nouveau'); await fillDirect();
    await userEvent.click(screen.getByRole('button', { name: 'Créer le brouillon de facture' }));
    expect(await screen.findByRole('heading', { name: 'FAC-000001' })).toBeInTheDocument();
    const creation = fetch.mock.calls.find(([path, init]) => path.endsWith('/invoicing/invoices/') && init?.method === 'POST')!;
    expect(JSON.parse(creation[1]!.body as string)).toMatchObject({ partner_id: 'partner', sales_order_id: null, lines: [{ quantity: '3', unit_price: '0.335000', tax_rate: '20.0000' }] });
    await userEvent.click(screen.getByRole('button', { name: 'Valider le document' }));
    expect(await screen.findByText('Validé')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Créer un avoir' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Annuler le brouillon' })).not.toBeInTheDocument();
  });
  it('relie une commande à une facture partielle en préservant les prix source', async () => {
    const fetch = server(); show(base + '/ventes/order');
    await userEvent.click(await screen.findByRole('link', { name: 'Facturer la commande' }));
    expect(await screen.findByRole('heading', { name: 'Facturer CMD-000001' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Prix unitaire 1')).toHaveValue('0.335000'));
    expect(screen.getByLabelText('Prix unitaire 1')).toHaveAttribute('readonly');
    const quantity = screen.getByLabelText('Quantité à facturer 1'); await userEvent.clear(quantity); await userEvent.type(quantity, '1');
    await userEvent.click(screen.getByRole('button', { name: 'Créer le brouillon de facture' }));
    await screen.findByRole('heading', { name: 'FAC-000001' });
    const creation = fetch.mock.calls.find(([path, init]) => path.endsWith('/invoicing/invoices/') && init?.method === 'POST')!;
    expect(JSON.parse(creation[1]!.body as string)).toMatchObject({ sales_order_id: 'order', order_version: 1, lines: [{ sales_order_line_id: 'order-line', quantity: '1' }] });
  });
  it('crée et valide un avoir depuis une facture puis recharge le net corrigé', async () => {
    const fetch = server({ seeded: true }); show(base + '/factures/invoice');
    await userEvent.click(await screen.findByRole('link', { name: 'Créer un avoir' }));
    await userEvent.type(await screen.findByLabelText('Motif de l’avoir'), 'Correction');
    await userEvent.type(screen.getByLabelText('Prestation — quantité à créditer'), '3');
    await userEvent.click(screen.getByRole('button', { name: 'Créer le brouillon d’avoir' }));
    expect(await screen.findByRole('heading', { name: 'AV-000001' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Valider le document' }));
    expect(await screen.findByText('Validé')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'FAC-000001' }));
    await waitFor(() => expect(within(screen.getByText('Net après avoirs').parentElement!).getByText('0 EUR')).toBeInTheDocument());
    expect(fetch.mock.calls.some(([path, init]) => path.endsWith('/credit-notes/') && JSON.parse(init!.body as string).lines[0].quantity === '3')).toBe(true);
  });
  it('affiche un refus de validation et permet d’annuler le brouillon', async () => {
    server({ reject: true }); show(base + '/factures/nouveau'); await fillDirect();
    await userEvent.click(screen.getByRole('button', { name: 'Créer le brouillon de facture' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Valider le document' }));
    expect(await screen.findByText('Quantité facturable dépassée.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Annuler le brouillon' }));
    expect(await screen.findByText('Annulé')).toBeInTheDocument();
  });
  it('refuse une URL de création sans droit avant les requêtes financières', async () => {
    const fetch = server({ manage: false }); show(base + '/factures/nouveau');
    expect(await screen.findByRole('heading', { name: 'Accès non autorisé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/invoicing/'))).toBe(false);
  });
  it('bloque le module désactivé sans charger les factures', async () => {
    const fetch = server({ enabled: false }); show(base + '/factures');
    expect(await screen.findByRole('heading', { name: 'Module désactivé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/invoicing/'))).toBe(false);
  });
});
