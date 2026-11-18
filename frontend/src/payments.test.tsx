import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const base = '/administration/entreprises/a';
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
type Row = Record<string, unknown> & { status: string; allowed_actions: string[]; allocations: Record<string, unknown>[]; available_amount: string; allocated_amount: string };
function show(path: string) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function server({ seeded = false, reject = false, manage = true, pdfReject = false }: { seeded?: boolean; reject?: boolean; manage?: boolean; pdfReject?: boolean } = {}) {
  const invoice = { id: 'invoice', reference: 'FAC-000001', status: 'validated', partner_id: 'partner', partner_name: 'Client réel', sales_order_id: null, currency_code: 'EUR', issue_date: '2026-11-17', due_date: '2026-12-17', untaxed_amount: '100', tax_amount: '0', total_amount: '100', credited_amount: '0', net_amount: '100', paid_amount: '0', amount_due: '100', credit_balance: '0', payment_status: 'unpaid', allowed_actions: [], lines: [{ id: 'invoice-line', description: 'Prestation', quantity: '1', unit_price: '100', discount_rate: '0', tax_rate: '0', line_total: '100', unit_name: '', credited_quantity: '0', creditable_quantity: '1' }] };
  let payment: Row | undefined = seeded ? { id: 'payment', reference: 'PAY-000001', status: 'validated', partner_id: 'partner', partner_name: 'Client réel', amount: '60', currency_code: 'EUR', method: 'bank_transfer', payment_date: '2026-11-17', external_reference: '', notes: '', available_amount: '60', allocated_amount: '0', allowed_actions: manage ? ['allocate', 'cancel'] : [], allocations: [], can_view_invoices: true, can_reverse: manage } : undefined;
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'user', full_name: 'Alice', email: 'alice@example.com' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Société', currency_code: 'EUR' }]);
    if (path.endsWith('/context/')) return json({ company: { id: 'a', name: 'Société', currency_code: 'EUR' }, permissions: ['company.view', 'invoicing.invoice.view', 'invoicing.payment.view', 'invoicing.document.export', ...(manage ? ['invoicing.payment.create', 'invoicing.payment.validate', 'invoicing.payment.allocate', 'invoicing.payment.reverse_allocation', 'invoicing.payment.cancel'] : [])], modules: ['core', 'invoicing'] });
    if (path.includes('/history/')) return json({ count: 0, results: [] });
    if (path.endsWith('/invoices/invoice/pdf/')) return pdfReject ? json({ detail: 'Export refusé.' }, 403) : new Response('%PDF-1.7 test', { headers: { 'Content-Type': 'application/pdf' } });
    if (path.endsWith('/invoices/invoice/')) return json(invoice);
    if (path.includes('/payments/lookups/')) return json({ partners: [{ id: 'partner', name: 'Client réel' }] });
    if (path.includes('/payments/payment/invoices/')) return json({ count: 1, results: [invoice] });
    if (path.includes('/payments/?')) return json({ count: payment ? 1 : 0, results: payment ? [payment] : [] });
    if (path.endsWith('/payments/') && init?.method === 'POST') { payment = { ...body, id: 'payment', reference: 'PAY-000001', status: 'draft', partner_name: 'Client réel', currency_code: 'EUR', available_amount: '0', allocated_amount: '0', allowed_actions: ['validate', 'cancel'], allocations: [], can_view_invoices: true, can_reverse: true }; return json(payment, 201); }
    if (path.endsWith('/payments/payment/')) return json(payment);
    if (path.endsWith('/payments/payment/validate/')) { payment!.status = 'validated'; payment!.available_amount = payment!.amount as string; payment!.allowed_actions = ['allocate', 'cancel']; return json(payment); }
    if (path.endsWith('/payments/payment/allocate/')) {
      if (reject) return json({ detail: 'Montant supérieur au disponible du paiement.' }, 400);
      payment!.allocated_amount = body.allocations[0].amount; payment!.available_amount = '0'; payment!.allowed_actions = [];
      payment!.allocations = [{ id: 'allocation', invoice_id: 'invoice', invoice_reference: 'FAC-000001', payment_id: 'payment', payment_reference: 'PAY-000001', amount: body.allocations[0].amount, status: 'active', reversal_reason: '' }];
      invoice.paid_amount = body.allocations[0].amount; invoice.amount_due = '40'; invoice.payment_status = 'partial'; return json(payment);
    }
    if (path.endsWith('/allocations/allocation/reverse/')) { payment!.allocated_amount = '0'; payment!.available_amount = payment!.amount as string; payment!.allowed_actions = ['allocate', 'cancel']; payment!.allocations[0].status = 'reversed'; payment!.allocations[0].reversal_reason = body.reason; invoice.paid_amount = '0'; invoice.amount_due = '100'; invoice.payment_status = 'unpaid'; return json(payment); }
    if (path.endsWith('/payments/payment/cancel/')) { payment!.status = 'cancelled'; payment!.available_amount = '0'; payment!.allowed_actions = []; payment!.cancellation_reason = body.reason; return json(payment); }
    throw new Error(`Requête imprévue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => { localStorage.clear(); vi.spyOn(window, 'confirm').mockReturnValue(true); });
describe('Paiements et export connectés', () => {
  it('enregistre depuis une facture, valide, alloue partiellement et extourne sans effacer', async () => {
    const fetch = server(); show(base + '/factures/invoice');
    await userEvent.click(await screen.findByRole('link', { name: 'Enregistrer un paiement pour cette facture' }));
    await screen.findByRole('option', { name: 'Client réel' });
    await waitFor(() => expect(screen.getByLabelText('Client du paiement')).toHaveValue('partner'));
    const amount = screen.getByLabelText('Montant reçu (EUR)'); await userEvent.clear(amount); await userEvent.type(amount, '60');
    await userEvent.click(screen.getByRole('button', { name: 'Créer le brouillon de paiement' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Valider le paiement' }));
    await screen.findByRole('option', { name: 'FAC-000001 - dû 100 EUR' });
    await waitFor(() => expect(screen.getByLabelText('Facture à régler 1')).toHaveValue('invoice'));
    await userEvent.type(screen.getByLabelText('Montant à allouer 1'), '60');
    await userEvent.click(screen.getByRole('button', { name: 'Confirmer les allocations' }));
    await userEvent.type(await screen.findByLabelText('Motif d’extourne 1'), 'Réaffectation');
    await userEvent.click(screen.getByRole('button', { name: 'Extourner l’allocation 1' }));
    expect(await screen.findByText('Réaffectation')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Extourner l’allocation 1' })).not.toBeInTheDocument();
    const creation = fetch.mock.calls.find(([path, init]) => path.endsWith('/payments/') && init?.method === 'POST')!;
    expect(JSON.parse(creation[1]!.body as string).amount).toBe('60');
  });
  it('conserve les montants du formulaire quand une allocation est refusée', async () => {
    server({ seeded: true, reject: true }); show(base + '/paiements/payment');
    await screen.findByRole('option', { name: 'FAC-000001 - dû 100 EUR' });
    await userEvent.selectOptions(screen.getByLabelText('Facture à régler 1'), 'invoice');
    await userEvent.type(screen.getByLabelText('Montant à allouer 1'), '80');
    await userEvent.click(screen.getByRole('button', { name: 'Confirmer les allocations' }));
    expect(await screen.findByText('Montant supérieur au disponible du paiement.')).toBeInTheDocument();
    expect(screen.getByLabelText('Montant à allouer 1')).toHaveValue('80');
  });
  it('exige un motif avant l’annulation d’un paiement validé non alloué', async () => {
    const fetch = server({ seeded: true }); show(base + '/paiements/payment');
    const button = await screen.findByRole('button', { name: 'Annuler le paiement' }); expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText('Motif d’annulation du paiement'), 'Erreur de saisie');
    await userEvent.click(button); expect(await screen.findByText('Annulé')).toBeInTheDocument();
    const request = fetch.mock.calls.find(([path]) => path.endsWith('/payment/cancel/'))!;
    expect(JSON.parse(request[1]!.body as string).reason).toBe('Erreur de saisie');
  });
  it('refuse une URL de création sans permission avant les requêtes de paiement', async () => {
    const fetch = server({ manage: false }); show(base + '/paiements/nouveau');
    expect(await screen.findByRole('heading', { name: 'Accès non autorisé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/payments/'))).toBe(false);
  });
  it('télécharge le vrai type PDF avec le nom du document', async () => {
    const fetch = server(); const create = vi.fn(() => 'blob:pdf-test'); Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: create }); Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    let name = ''; vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { name = this.download; });
    show(base + '/factures/invoice'); await userEvent.click(await screen.findByRole('button', { name: 'Télécharger le PDF' }));
    await waitFor(() => expect(create).toHaveBeenCalled()); expect(name).toBe('FAC-000001.pdf');
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/invoices/invoice/pdf/'))).toBe(true);
  });
  it('affiche le refus serveur d’export sans créer de téléchargement', async () => {
    server({ pdfReject: true }); show(base + '/factures/invoice');
    await userEvent.click(await screen.findByRole('button', { name: 'Télécharger le PDF' }));
    expect(await screen.findByText('Export refusé.')).toBeInTheDocument();
  });
});
