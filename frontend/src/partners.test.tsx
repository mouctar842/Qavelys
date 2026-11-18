import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import App from './App';

const base = '/administration/entreprises/a';
const initial = { id: 'p', name: 'Tiers partagé', email: 'work@example.com', phone: '', address: 'Adresse générale', status: 'active', is_customer: true, is_supplier: true, customer_reference: 'CLI-42', supplier_reference: 'FOUR-7', delivery_address: 'Livraison client', customer_notes: 'Note client conservée', supplier_notes: 'Retrait fournisseur' };
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
function show(path: string) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[base + path]}><App/></MemoryRouter></QueryClientProvider>); }
function server({ supplier = true, readonly = false, activityError = false } = {}) {
  const item = { ...initial, is_supplier: supplier };
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url, 'http://test').pathname; const post = init?.method === 'POST'; const body = post ? JSON.parse(init?.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test' });
    if (path.endsWith('/auth/me/')) return json({ id: 'u', full_name: 'Gestionnaire', email: 'owner@example.com' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Entreprise A', currency_code: 'EUR' }]);
    if (path.endsWith('/context/')) return json({ company: { id: 'a', name: 'Entreprise A', currency_code: 'EUR' }, permissions: ['company.view', 'contacts.view', ...(!readonly ? ['contacts.manage', 'sales.order.view', 'sales.order.create', 'purchases.order.view', 'purchases.order.create', 'invoicing.invoice.view', 'invoicing.invoice.create', 'invoicing.payment.view', 'invoicing.payment.create'] : [])], modules: ['core', 'contacts', 'sales', 'purchases', 'invoicing', 'inventory'] });
    if (path.endsWith('/reference/partners/p/profiles/')) { item[body.profile === 'supplier' ? 'is_supplier' : 'is_customer'] = true; return json(item); }
    if (path.endsWith('/reference/partners/p/activity/')) {
      if (activityError) return json({ detail: 'Activité momentanément indisponible.' }, 503);
      const params = new URL(url, 'http://test').searchParams; const customer = params.get('profile') === 'customer';
      return json({ available_sections: [{ code: customer ? 'invoices' : 'purchases', label: customer ? 'Factures' : 'Commandes fournisseurs' }], section: customer ? 'invoices' : 'purchases', count: customer ? 1 : 0, results: customer ? [{ id: 'invoice', label: 'FAC-000001', date: '2026-11-18', status: 'validated', amount: '100.000000', currency_code: 'EUR' }] : [], ...(customer ? { balances: [{ currency_code: 'EUR', amount_due: '60.000000', credit_balance: '0.000000' }] } : {}) });
    }
    if (path.endsWith('/reference/partners/p/update/')) { Object.assign(item, body); return json(item); }
    if (path.endsWith('/reference/partners/p/')) return json(item);
    if (path.endsWith('/reference/partners/')) {
      if (post) { Object.assign(item, body); return json(item, 201); }
      return json({ count: 1, page: 1, page_size: 25, results: [item] });
    }
    if (path.endsWith('/purchases/lookups/') || path.endsWith('/sales/lookups/')) return json({ partners: [], products: [], warehouses: [] });
    throw new Error(`Requête inattendue : ${url}`);
  }); vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => { localStorage.clear(); vi.spyOn(window, 'confirm').mockReturnValue(true); });

it('crée un fournisseur avec son formulaire propre et sans profil client implicite', async () => {
  const fetch = server(); show('/fournisseurs/nouveau');
  await userEvent.type(await screen.findByLabelText('Nom'), 'Fournisseur atelier');
  await userEvent.type(screen.getByLabelText('Référence chez le fournisseur'), 'FOUR-99');
  await userEvent.type(screen.getByLabelText('Instructions d’approvisionnement'), 'Prévenir le dépôt');
  expect(screen.queryByLabelText('Adresse de livraison')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le fournisseur' }));
  expect(await screen.findByRole('heading', { name: 'Fournisseur atelier' })).toBeInTheDocument();
  const call = fetch.mock.calls.find(([url, init]) => url.endsWith('/reference/partners/') && init?.method === 'POST')!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({ is_customer: false, is_supplier: true, supplier_reference: 'FOUR-99', supplier_notes: 'Prévenir le dépôt' });
});

it('réutilise le même tiers par ajout explicite du second profil', async () => {
  const fetch = server({ supplier: false }); show('/fournisseurs/nouveau');
  await userEvent.type(await screen.findByLabelText('Rechercher dans tous les tiers'), 'partagé');
  await userEvent.click(await screen.findByRole('button', { name: 'Utiliser ce tiers · Tiers partagé' }));
  expect(await screen.findByRole('heading', { name: 'Tiers partagé' })).toBeInTheDocument();
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/p/profiles/'))).toBe(true);
  expect(fetch.mock.calls.some(([url, init]) => url.endsWith('/reference/partners/') && init?.method === 'POST')).toBe(false);
});

it('conserve les informations client lors de l’édition fournisseur', async () => {
  const fetch = server(); show('/fournisseurs/p/modifier');
  const input = await screen.findByLabelText('Instructions d’approvisionnement');
  await userEvent.clear(input); await userEvent.type(input, 'Nouvelle instruction');
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le fournisseur' }));
  await screen.findByRole('heading', { name: 'Tiers partagé' });
  const call = fetch.mock.calls.find(([url]) => url.endsWith('/p/update/'))!;
  const body = JSON.parse(call[1]!.body as string);
  expect(body.supplier_notes).toBe('Nouvelle instruction');
  expect(body).not.toHaveProperty('customer_notes'); expect(body).not.toHaveProperty('is_customer');
  await userEvent.click(screen.getByRole('link', { name: 'Ouvrir le profil client' }));
  expect(await screen.findByText('Note client conservée')).toBeInTheDocument();
});

it('présente les créances exactes et les liens des vrais documents', async () => {
  server(); show('/clients/p');
  expect(await screen.findByText('Créances clients (EUR)')).toBeInTheDocument();
  expect(screen.getByText('60', { selector: 'dd' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'FAC-000001' })).toHaveAttribute('href', base + '/factures/invoice');
  expect(screen.queryByText('Retrait fournisseur')).not.toBeInTheDocument();
});

it('préremplit le fournisseur contrôlé dans l’éditeur de commande existant', async () => {
  const fetch = server(); show('/fournisseurs/p');
  await userEvent.click(await screen.findByRole('link', { name: 'Créer une commande fournisseur' }));
  expect(await screen.findByLabelText('Fournisseur')).toHaveValue('p');
  expect(fetch.mock.calls.some(([url]) => url.endsWith('/reference/partners/p/'))).toBe(true);
});

it('refuse un mauvais profil au préremplissage et affiche les erreurs sans faux solde', async () => {
  server({ supplier: false }); show('/achats/nouveau?partner=p');
  expect(await screen.findByRole('alert')).toHaveTextContent('profil requis');
});

it('masque les écritures à un lecteur et montre la panne réelle d’activité', async () => {
  server({ readonly: true, activityError: true }); show('/clients/p');
  expect(await screen.findByRole('alert')).toHaveTextContent('Activité momentanément indisponible');
  expect(screen.queryByRole('link', { name: 'Modifier le client' })).not.toBeInTheDocument();
  expect(screen.queryByText('Créances clients (EUR)')).not.toBeInTheDocument();
});
