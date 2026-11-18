import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import App from './App';
import { PermissionCatalog } from './components/permission-catalog';

const company = { id: 'a', name: 'Société lisible', country_code: 'FR', currency_code: 'EUR' };
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
function show(path: string) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[`/administration/entreprises/a/${path}`]}><App/></MemoryRouter></QueryClientProvider>); }
function server(failSequence = false) {
  let installed = false; let prefix = 'FAC-';
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const post = init?.method === 'POST';
    if (url.endsWith('/auth/csrf/')) return json({ csrfToken: 'test' });
    if (url.endsWith('/auth/me/')) return json({ id: 'u', full_name: 'Alice', email: 'alice@example.com' });
    if (url === '/api/v1/companies/') return json([company]);
    if (url.endsWith('/context/')) return json({ company, membership_id: 'self', permissions: ['company.view', 'company.manage', 'roles.view', 'roles.manage', 'audit.view', 'sequences.view'], modules: ['core'] });
    if (url.endsWith('/roles/')) return json([{ id: 'admin', name: 'Administrateur', is_system: true, permission_codes: ['company.view'] }]);
    if (url.endsWith('/permissions/')) return json([{ code: 'company.view', description: 'Consulter l’entreprise', module_code: 'core', module_name: 'Administration' }]);
    if (url.endsWith('/role-templates/')) { if (post) { installed = true; return json({ id: 'sales', name: 'Commercial' }, 201); } return json([{ code: 'sales', name: 'Commercial', permission_codes: ['company.view'], installed }]); }
    if (url.endsWith('/sequences/invoice/')) { if (failSequence) return json({ detail: 'Préfixe protégé après émission.' }, 400); prefix = JSON.parse(init?.body as string).prefix; return json({ prefix, preview: `${prefix}000001` }); }
    if (url.endsWith('/sequences/')) return json([{ document_type: 'invoice', label: 'Factures clients', module_name: 'Facturation', description: 'Référence des factures.', prefix, next_number: 1, preview: `${prefix}000001`, can_edit: true }]);
    if (url.includes('/audit/?')) return json({ count: 1, results: [{ id: 'event', action: 'sales.order_confirm', action_label: 'Confirmation · Commande', target_label: 'CMD-000042', module_name: 'Ventes', company_name: company.name, entity_type: 'SalesOrder', entity_id: 'uuid-investigation', actor: 'Alice', created_at: '2026-11-17T10:00:00Z', changes: [{ label: 'Statut', before: 'Brouillon', after: 'Confirmé' }], before_data: { status: 'draft' }, after_data: { status: 'confirmed' } }], filters: { actors: [{ actor_id: 'actor', actor__full_name: 'Alice' }], modules: [{ code: 'sales', name: 'Ventes' }] } });
    throw new Error(`Requête inattendue : ${url}`);
  });
  vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => localStorage.clear());

it('regroupe et sélectionne les permissions par module, y compris après recherche', async () => {
  function Harness() {
    const [selected, setSelected] = useState<string[]>([]);
    return <PermissionCatalog permissions={[{ code: 'sales.order.view', description: 'Consulter les ventes', module_code: 'sales', module_name: 'Ventes' }, { code: 'inventory.view', description: 'Consulter les stocks', module_code: 'inventory', module_name: 'Inventaire' }]} selected={selected} onChange={setSelected}/>;
  }
  render(<Harness/>);
  await userEvent.click(screen.getByRole('button', { name: 'Tout sélectionner · Ventes' }));
  expect(screen.getByRole('checkbox', { name: 'Consulter les ventes' })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Consulter les stocks' })).not.toBeChecked();
  await userEvent.type(screen.getByLabelText('Rechercher une autorisation'), 'stocks');
  expect(screen.queryByRole('checkbox', { name: 'Consulter les ventes' })).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('1 autorisation');
  await userEvent.clear(screen.getByLabelText('Rechercher une autorisation'));
  expect(screen.getByRole('checkbox', { name: 'Consulter les ventes' })).toBeChecked();
});

it('installe un rôle prédéfini par l’API sans attribution de membre', async () => {
  const fetch = server(); vi.spyOn(window, 'confirm').mockReturnValue(true);
  show('roles');
  await userEvent.click(await screen.findByRole('button', { name: 'Ajouter · Commercial' }));
  expect(await screen.findByText('Déjà disponible')).toBeInTheDocument();
  expect(fetch.mock.calls.find(([url, init]) => url.endsWith('/role-templates/') && init?.method === 'POST')?.[1]?.body).toBe(JSON.stringify({ code: 'sales' }));
  expect(fetch.mock.calls.some(([url]) => url.includes('/members/'))).toBe(false);
});

it('affiche un audit lisible et conserve les détails techniques, avec filtres API', async () => {
  const fetch = server(); show('audit');
  const row = await screen.findByRole('row', { name: /Confirmation · Commande/ });
  expect(within(row).getByText('CMD-000042')).toBeInTheDocument();
  await userEvent.click(within(row).getByText('Consulter les changements'));
  expect(within(row).getByText('Confirmé')).toBeVisible();
  expect(within(row).getByText('Détails techniques').closest('details')).not.toHaveAttribute('open');
  await userEvent.selectOptions(screen.getByLabelText('Module'), 'sales');
  expect(fetch.mock.calls.some(([url]) => url.includes('module=sales'))).toBe(true);
  await userEvent.selectOptions(screen.getByLabelText('Auteur'), 'actor');
  expect(fetch.mock.calls.some(([url]) => url.includes('actor=actor'))).toBe(true);
});

it('configure le préfixe avec aperçu et confirmation sans écrire le compteur', async () => {
  const fetch = server(); vi.spyOn(window, 'confirm').mockReturnValue(true); show('sequences');
  await userEvent.click(await screen.findByRole('button', { name: 'Configurer · Factures clients' }));
  const input = screen.getByLabelText('Préfixe · Factures clients');
  await userEvent.clear(input); await userEvent.type(input, 'FACT-');
  expect(screen.getByText('Aperçu : FACT-000001')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le préfixe' }));
  expect(await screen.findByText('FACT-000001', { selector: 'strong' })).toBeInTheDocument();
  expect(fetch.mock.calls.find(([url]) => url.endsWith('/sequences/invoice/'))?.[1]?.body).toBe(JSON.stringify({ prefix: 'FACT-' }));
});

it('garde le formulaire et affiche le refus réel après émission concurrente', async () => {
  server(true); vi.spyOn(window, 'confirm').mockReturnValue(true); show('sequences');
  await userEvent.click(await screen.findByRole('button', { name: 'Configurer · Factures clients' }));
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le préfixe' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Préfixe protégé');
  expect(screen.getByLabelText('Préfixe · Factures clients')).toBeInTheDocument();
});
