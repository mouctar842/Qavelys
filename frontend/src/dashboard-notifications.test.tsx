import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const base = '/administration/entreprises/a';
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
function show(path: string) { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function server({ allowed = true, enabled = true, empty = false, error = false }: { allowed?: boolean; enabled?: boolean; empty?: boolean; error?: boolean } = {}) {
  const notices: Record<string, { id: string; type: string; title: string; message: string; created_at: string; read_at: string | null; target: string }[]> = {
    a: [{ id: 'notice-a', type: 'crm_due', title: 'Rappeler le client A', message: 'Échéance réelle', created_at: '2026-11-17T09:00:00Z', read_at: null, target: 'crm/lead-a' }, { id: 'notice-a2', type: 'invoice_overdue', title: 'Facture A en retard', message: 'Consulter le solde', created_at: '2026-11-17T08:00:00Z', read_at: null, target: 'factures/invoice-a' }],
    b: [{ id: 'notice-b', type: 'crm_due', title: 'Alerte B', message: 'Société B uniquement', created_at: '2026-11-17T09:00:00Z', read_at: null, target: 'crm/lead-b' }],
  };
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'user', full_name: 'Alice', email: 'alice@example.com' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Société A', currency_code: 'EUR' }, { id: 'b', name: 'Société B', currency_code: 'GNF' }]);
    const company = path.match(/companies\/([^/]+)\//)?.[1] || 'a';
    const unread = () => notices[company].filter(item => !item.read_at).length;
    if (path.endsWith('/context/')) return json({ company: { id: company, name: `Société ${company.toUpperCase()}`, currency_code: company === 'a' ? 'EUR' : 'GNF' }, permissions: ['company.view', 'notifications.view', 'crm.view', ...(allowed ? ['dashboard.view', 'contacts.view', 'invoicing.invoice.view'] : [])], modules: ['core', 'crm', 'contacts', 'invoicing', ...(enabled ? ['dashboard'] : [])] });
    if (path.includes('/dashboard/?')) {
      if (error) return json({ detail: 'Indicateurs momentanément indisponibles.' }, 503);
      const params = new URL('http://test' + path).searchParams;
      const amount = company === 'b' ? '300' : params.get('start') === '2026-10-01' ? '900' : '1200';
      return json({ period: { start: params.get('start'), end: params.get('end'), timezone: 'UTC' }, generated_at: '2026-11-17T10:00:00Z', sections: empty ? {} : { contacts: { active_customers: company === 'a' ? 4 : 2, new_customers: 1 }, invoicing: { invoice_count: 2, totals: [{ currency_code: 'EUR', billed: amount, credited: '0', net: amount }, { currency_code: 'GNF', billed: '10000', credited: '0', net: '10000' }], monthly: [{ month: '2026-11', currency_code: 'EUR', billed: amount, credited: '0', net: amount }, { month: '2026-11', currency_code: 'GNF', billed: '10000', credited: '0', net: '10000' }], unpaid_count: 1, amount_due: [{ currency_code: 'EUR', amount: '40' }], overdue_count: 1, overdue_amount: [{ currency_code: 'EUR', amount: '40' }], overdue_invoices: [{ id: 'invoice-a', reference: 'FAC-000001', partner_name: 'Client réel', due_date: '2026-11-01', currency_code: 'EUR', amount_due: '40' }] } } });
    }
    if (path.endsWith('/notifications/sync/')) return json({ created: 0 });
    if (path.endsWith('/notifications/summary/')) return json({ unread_count: unread() });
    if (path.includes('/notifications/?')) {
      const params = new URL('http://test' + path).searchParams; const state = params.get('state'); const search = params.get('search') || '';
      const rows = notices[company].filter(item => (state === 'unread' ? !item.read_at : state === 'read' ? Boolean(item.read_at) : true) && item.title.toLowerCase().includes(search.toLowerCase()));
      return json({ count: rows.length, unread_count: unread(), results: rows });
    }
    if (path.endsWith('/notifications/read-all/')) { notices[company].forEach(item => { item.read_at = '2026-11-17T10:00:00Z'; }); return json({ marked_read: notices[company].length }); }
    const read = path.match(/notifications\/([^/]+)\/read\//);
    if (read) { const item = notices[company].find(row => row.id === read[1])!; item.read_at = body.read ? '2026-11-17T10:00:00Z' : null; return json(item); }
    throw new Error(`Requête imprévue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => {
  localStorage.clear(); vi.spyOn(window, 'confirm').mockReturnValue(true);
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});
describe('Tableau de bord et notifications réels', () => {
  it('affiche les montants exacts par devise et applique une période au serveur', async () => {
    const fetch = server(); show(base + '/tableau-de-bord');
    await screen.findByRole('heading', { name: 'Tableau de bord' }, { timeout: 10000 });
    const table = await screen.findByRole('table', { name: 'Montants mensuels exacts' });
    expect(within(table).getAllByText('1200').length).toBeGreaterThan(0);
    expect(within(table).getByText('GNF')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'FAC-000001' })).toHaveAttribute('href', base + '/factures/invoice-a');
    fireEvent.change(screen.getByLabelText('Début de période'), { target: { value: '2026-10-01' } });
    fireEvent.change(screen.getByLabelText('Fin de période'), { target: { value: '2026-10-31' } });
    await userEvent.click(screen.getByRole('button', { name: 'Appliquer la période' }));
    await waitFor(() => expect(within(screen.getByRole('table', { name: 'Montants mensuels exacts' })).getAllByText('900').length).toBeGreaterThan(0));
    expect(fetch.mock.calls.some(([path]) => path.includes('start=2026-10-01&end=2026-10-31'))).toBe(true);
  });
  it('isole les indicateurs lors du changement d’entreprise', async () => {
    server(); show(base + '/tableau-de-bord');
    await screen.findByRole('table', { name: 'Montants mensuels exacts' });
    await userEvent.selectOptions(screen.getByLabelText('Entreprise active'), 'b');
    await waitFor(() => expect(within(screen.getByRole('table', { name: 'Montants mensuels exacts' })).getAllByText('300').length).toBeGreaterThan(0));
    expect(within(screen.getByRole('table', { name: 'Montants mensuels exacts' })).queryByText('1200')).not.toBeInTheDocument();
  });
  it('refuse une URL dashboard sans droit avant la requête métier', async () => {
    const fetch = server({ allowed: false }); show(base + '/tableau-de-bord');
    expect(await screen.findByRole('heading', { name: 'Accès non autorisé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/dashboard/'))).toBe(false);
  });
  it('refuse un dashboard désactivé sans charger ses données', async () => {
    const fetch = server({ enabled: false }); show(base + '/tableau-de-bord');
    expect(await screen.findByRole('heading', { name: 'Module désactivé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/dashboard/'))).toBe(false);
  });
  it('affiche un état vide sans inventer des indicateurs non autorisés', async () => {
    server({ empty: true }); show(base + '/tableau-de-bord');
    expect(await screen.findByRole('heading', { name: 'Aucun indicateur accessible' })).toBeInTheDocument();
    expect(screen.queryByText('Facturé net TTC')).not.toBeInTheDocument();
  });
  it('marque une notification comme lue et actualise le compteur puis toutes les notifications', async () => {
    const fetch = server(); show(base + '/notifications');
    expect(await screen.findByLabelText('2 notifications non lues')).toBeInTheDocument();
    await screen.findByRole('heading', { name: 'Rappeler le client A' });
    await userEvent.click(screen.getAllByRole('button', { name: 'Marquer comme lu' })[0]);
    expect(await screen.findByLabelText('1 notification non lue')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Tout marquer comme lu' }));
    expect(await screen.findByText('0 notification(s) non lue(s).')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path, init]) => path.includes('/notice-a/read/') && JSON.parse(init!.body as string).read === true)).toBe(true);
    expect(screen.getAllByRole('link', { name: 'Ouvrir la source' })[0]).toHaveAttribute('href', base + '/crm/lead-a');
  });
  it('recherche les notifications et isole leur boîte au changement d’entreprise', async () => {
    server(); show(base + '/notifications');
    await screen.findByRole('heading', { name: 'Rappeler le client A' });
    await userEvent.type(screen.getByLabelText('Rechercher une notification'), 'Facture');
    expect(await screen.findByRole('heading', { name: 'Facture A en retard' })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Rappeler le client A' })).not.toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText('Entreprise active'), 'b');
    expect(await screen.findByRole('heading', { name: 'Alerte B' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Facture A en retard' })).not.toBeInTheDocument();
  });
  it('propose les applications actives et montre les erreurs des indicateurs', async () => {
    server({ error: true }); show(base);
    await userEvent.click(await screen.findByRole('link', { name: /Ouvrir le tableau de bord Indicateurs/ }));
    expect(await screen.findByText('Indicateurs momentanément indisponibles.')).toBeInTheDocument();
    expect(screen.queryByText('Facturé net TTC')).not.toBeInTheDocument();
  });
});
