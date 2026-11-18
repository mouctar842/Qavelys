import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const base = '/administration/entreprises/a';
function show(path: string) { return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
function server(active = true) {
  let enabled = active;
  const contacts: Record<string, unknown>[] = [];
  const products: Record<string, unknown>[] = [];
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const post = init?.method === 'POST';
    const body = post ? JSON.parse(init!.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'u', full_name: 'Alice', email: 'alice@example.com' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Entreprise A', country_code: 'GN', currency_code: 'GNF', sector: '' }]);
    if (path.endsWith('/context/')) return json({ company: { id: 'a', name: 'Entreprise A', country_code: 'GN', currency_code: 'GNF', sector: '' }, membership_id: 'self', permissions: ['company.view', 'modules.view', 'modules.manage', 'contacts.view', 'contacts.manage', 'products.view', 'products.manage', 'categories.view', 'taxes.view'], modules: enabled ? ['core', 'contacts', 'catalog'] : ['core'] });
    if (path.endsWith('/modules/contacts/enable/')) { enabled = true; return json({ detail: 'Activé' }); }
    if (path.endsWith('/modules/')) return json([{ code: 'contacts', name: 'Contacts', description: 'Clients et fournisseurs', enabled, status: 'available', dependencies: ['core'] }]);
    if (path.endsWith('/reference/units/')) return json([{ id: 'unit', name: 'Unité', symbol: 'u', category: 'count' }]);
    if (path.endsWith('/price-history/')) return json([]);
    if (path.includes('/reference/categories/') || path.includes('/reference/taxes/')) return json({ count: 0, page: 1, page_size: 25, results: [] });
    const match = path.match(/\/reference\/(partners|products)\/(?:([^/?]+)\/)?(?:([^/?]+)\/)?/);
    if (match) {
      const [, resource, id, action] = match;
      const rows = resource === 'partners' ? contacts : products;
      if (post && !id) { const item = { id: resource === 'partners' ? 'contact' : 'product', ...body, status: 'active', active: true, taxes: [], unit_name: 'Unité' }; rows.push(item); return json(item, 201); }
      const item = rows.find(value => value.id === id);
      if (id && !item) return json({ detail: 'Introuvable.' }, 404);
      if (post && action === 'update') { Object.assign(item!, body); return json(item); }
      if (post && (action === 'archive' || action === 'restore')) { item!.status = action === 'archive' ? 'archived' : 'active'; item!.active = action === 'restore'; return json(item); }
      if (id) return json(item);
      return json({ count: rows.length, page: 1, page_size: 25, results: rows });
    }
    throw new Error(`Requête imprévue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
beforeEach(() => localStorage.clear());
describe('Référentiel connecté', () => {
  it('active un module et ouvre son menu sans simuler de données', async () => {
    server(false);
    show(base + '/modules');
    await screen.findByRole('heading', { name: 'Modules de l’entreprise' });
    expect(within(screen.getByRole('navigation', { name: 'Navigation de l’administration' })).queryByRole('link', { name: 'Clients' })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Activer avec ses dépendances' }));
    const link = await screen.findByRole('link', { name: 'Clients' });
    await userEvent.click(link);
    expect(await screen.findByText('Aucune donnée ne correspond à votre recherche.')).toBeInTheDocument();
  });
  it('refuse une URL de module désactivé avant de demander ses données', async () => {
    const fetch = server(false);
    show(base + '/contacts');
    expect(await screen.findByRole('heading', { name: 'Module désactivé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/reference/partners/'))).toBe(false);
  });
  it('crée un client-fournisseur puis modifie et archive sa fiche', async () => {
    const fetch = server();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
    show(base + '/contacts/nouveau');
    await userEvent.type(await screen.findByLabelText('Nom'), 'Client Alpha');
    await userEvent.type(screen.getByLabelText('E-mail'), 'client@example.com');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Fournisseur' }));
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));
    expect(await screen.findByRole('heading', { name: 'Client Alpha' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Modifier' }));
    const phone = await screen.findByLabelText('Téléphone');
    await userEvent.type(phone, '+224123');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));
    expect(await screen.findByText('+224123')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Archiver' }));
    expect(await screen.findByText('Archivé')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/contact/archive/'))).toBe(true);
    expect(confirm).toHaveBeenCalled();
    confirm.mockRestore();
  });
  it('transmet les prix en chaînes décimales et ouvre la fiche produit', async () => {
    const fetch = server();
    show(base + '/produits/nouveau');
    await userEvent.type(await screen.findByLabelText('Nom'), 'Produit Alpha');
    await userEvent.type(screen.getByLabelText('SKU'), 'P-001');
    await userEvent.selectOptions(screen.getByLabelText('Unité de référence'), 'unit');
    await userEvent.clear(screen.getByLabelText('Prix de vente'));
    await userEvent.type(screen.getByLabelText('Prix de vente'), '123.456789');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));
    expect(await screen.findByRole('heading', { name: 'Produit Alpha' })).toBeInTheDocument();
    const call = fetch.mock.calls.find(([path, init]) => path.endsWith('/reference/products/') && init?.method === 'POST')!;
    expect(JSON.parse(call[1]!.body as string).sale_price).toBe('123.456789');
    expect(await screen.findByText('Aucune modification de prix enregistrée.')).toBeInTheDocument();
  });
});
