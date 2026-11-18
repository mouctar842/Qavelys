import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const root = '/administration/entreprises/a/inventaire';
function show(path: string) { return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
function server(manage = true, enabled = true) {
  let warehouse: Record<string, unknown> = { id: 'warehouse', name: 'Principal', code: 'MAIN', active: true };
  let adjustment: Record<string, unknown> | undefined;
  let validated = false;
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'u', full_name: 'Alice', email: 'alice@example.com' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Société', currency_code: 'EUR' }, { id: 'b', name: 'Autre société', currency_code: 'EUR' }]);
    if (path.endsWith('/context/')) return json({ company: { id: path.includes('/b/') ? 'b' : 'a', name: 'Société', currency_code: 'EUR' }, permissions: ['company.view', 'inventory.view', ...(manage ? ['inventory.warehouse.manage', 'inventory.adjustment.create', 'inventory.adjustment.validate', 'inventory.transfer.create'] : [])], modules: enabled ? ['core', 'inventory'] : ['core'] });
    if (path.includes('/lookups/')) return json({ products: [{ id: 'product', name: 'Article', sku: 'ART' }], warehouses: [{ id: 'warehouse', name: 'Principal', code: 'MAIN' }], locations: [{ id: 'location', name: 'MAIN / Stock' }, { id: 'destination', name: 'SEC / Stock' }] });
    if (path.endsWith('/warehouses/') && init?.method === 'POST') { warehouse = { ...warehouse, ...body }; return json(warehouse); }
    if (path.endsWith('/warehouses/warehouse/update/')) { warehouse = { ...warehouse, ...body }; return json(warehouse); }
    if (path.endsWith('/warehouses/warehouse/archive/')) { warehouse = { ...warehouse, active: false }; return json(warehouse); }
    if (path.endsWith('/warehouses/warehouse/')) return json(warehouse);
    if (path.endsWith('/adjustments/') && init?.method === 'POST') { adjustment = { id: 'adjustment', ...body, reference: 'AJU-000001', status: 'draft', location_name: 'Stock', lines: body.lines.map((line: Record<string, unknown>) => ({ ...line, id: 'line', product_name: 'Article', difference: null })) }; return json(adjustment); }
    if (path.endsWith('/adjustments/adjustment/validate/')) { validated = true; adjustment = { ...adjustment, status: 'validated', lines: [{ id: 'line', product_name: 'Article', counted_quantity: '12.123456', difference: '12.123456' }] }; return json(adjustment); }
    if (path.endsWith('/adjustments/adjustment/')) return json(adjustment);
    if (path.includes('/balances/?')) return json({ count: validated ? 1 : 0, results: validated ? [{ id: 'balance', product_name: 'Article', warehouse_name: 'Principal', location_name: 'Stock', quantity: '12.123456', reserved_quantity: '0.000000', available_quantity: '12.123456' }] : [] });
    if (path.endsWith('/transfers/') && init?.method === 'POST') return json({ detail: 'Stock disponible insuffisant.' }, 400);
    throw new Error(`Requête imprévue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => localStorage.clear());
describe('Inventaire connecté', () => {
  it('crée un entrepôt, modifie sa configuration et archive sa fiche', async () => {
    server(); vi.spyOn(window, 'confirm').mockReturnValue(true); show(root + '/entrepots/nouveau');
    await userEvent.type(await screen.findByLabelText('Nom'), 'Entrepôt Nord');
    await userEvent.type(screen.getByLabelText('Code'), 'NORD');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));
    expect(await screen.findByRole('heading', { name: 'Entrepôt Nord' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: 'Modifier' }));
    const name = await screen.findByLabelText('Nom'); await userEvent.clear(name); await userEvent.type(name, 'Nord 2');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer' }));
    expect(await screen.findByRole('heading', { name: 'Nord 2' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Archiver' }));
    expect(await screen.findByText('Archivé')).toBeInTheDocument();
  });
  it('valide un comptage exact puis recharge les soldes du backend', async () => {
    const fetch = server(); vi.spyOn(window, 'confirm').mockReturnValue(true); show(root + '/ajustements/nouveau');
    await screen.findByRole('option', { name: 'MAIN / Stock' });
    await userEvent.selectOptions(await screen.findByLabelText('Emplacement'), 'location');
    await userEvent.type(screen.getByLabelText('Motif du comptage'), 'Inventaire annuel');
    await userEvent.selectOptions(await screen.findByLabelText('Produit 1'), 'product');
    const quantity = screen.getByLabelText('Quantité comptée 1'); await userEvent.clear(quantity); await userEvent.type(quantity, '12.123456');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le brouillon' }));
    expect(await screen.findByRole('heading', { name: 'AJU-000001' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Valider les mouvements' }));
    expect(await screen.findByText('Validé')).toBeInTheDocument();
    const call = fetch.mock.calls.find(([path, init]) => path.endsWith('/adjustments/') && init?.method === 'POST')!;
    expect(JSON.parse(call[1]!.body as string).lines[0].counted_quantity).toBe('12.123456');
    expect(JSON.parse(call[1]!.body as string).request_key).toMatch(/^[a-f0-9-]{36}$/);
    await userEvent.click(screen.getByRole('link', { name: 'État des stocks' }));
    expect(await screen.findByRole('cell', { name: 'Article' })).toBeInTheDocument();
    expect(await screen.findAllByRole('cell', { name: '12.123456' })).toHaveLength(2);
  });
  it('affiche le refus du serveur et conserve le formulaire de transfert', async () => {
    server(); show(root + '/transferts/nouveau');
    await screen.findByRole('option', { name: 'ART — Article' });
    await userEvent.selectOptions(await screen.findByLabelText('Produit'), 'product');
    await userEvent.selectOptions(screen.getByLabelText('Emplacement source'), 'location');
    await userEvent.selectOptions(screen.getByLabelText('Emplacement destination'), 'destination');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le brouillon' }));
    expect(await screen.findByText('Stock disponible insuffisant.')).toBeInTheDocument();
    expect(screen.getByLabelText('Produit')).toHaveValue('product');
  });
  it('efface le formulaire lors du changement d’entreprise', async () => {
    server(); show(root + '/entrepots/nouveau');
    await userEvent.type(await screen.findByLabelText('Nom'), 'Valeur entreprise A');
    await userEvent.selectOptions(screen.getByLabelText('Entreprise active'), 'b');
    await waitFor(() => expect(screen.getByLabelText('Nom')).toHaveValue(''));
  });
  it('bloque les créations sans permission', async () => {
    const fetch = server(false); show(root + '/entrepots/nouveau');
    expect(await screen.findByRole('heading', { name: 'Accès non autorisé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/inventory/'))).toBe(false);
  });
});
