import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const base = '/administration/entreprises/a/crm';
const initialLead = { id: 'lead', title: 'Contrat Alpha', stage: 'new', partner_id: null, partner_name: null, partner_is_customer: false, owner_id: 'self', owner_name: 'Alice', expected_revenue: '1200.125000', probability: 30, created_at: '2026-11-16T12:00:00Z', updated_at: '2026-11-16T12:00:00Z' };
function show(path: string) { return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function json(data: unknown) { return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } }); }
function server(enabled = true, manage = true) {
  let lead = { ...initialLead } as Record<string, unknown>;
  let activities: Record<string, unknown>[] = [];
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'u', full_name: 'Alice', email: 'alice@example.com' });
    if (path === '/api/v1/companies/') return json([{ id: 'a', name: 'Société', currency_code: 'EUR' }]);
    if (path.endsWith('/context/')) return json({ company: { id: 'a', name: 'Société', currency_code: 'EUR' }, permissions: ['company.view', 'crm.view', 'contacts.view', ...(manage ? ['crm.manage', 'contacts.manage'] : [])], modules: enabled ? ['core', 'contacts', 'crm'] : ['core'] });
    if (path.endsWith('/lookups/')) return json({ members: [{ id: 'self', name: 'Alice' }], partners: [] });
    if (path.includes('/history/')) return json({ count: 1, results: [{ id: 'history', action: 'crm.lead_created', actor: 'Alice', created_at: '2026-11-16T12:00:00Z' }] });
    if (path.endsWith('/leads/lead/move/')) { lead = { ...lead, stage: body.stage }; return json(lead); }
    if (path.endsWith('/leads/lead/convert-customer/')) { lead = { ...lead, partner_id: 'customer', partner_name: body.name, partner_is_customer: true }; return json(lead); }
    if (path.endsWith('/leads/lead/')) return json(lead);
    if (path.endsWith('/leads/') && init?.method === 'POST') { lead = { ...lead, ...body }; return json(lead); }
    if (path.includes('/leads/?')) { const stage = new URL(path, 'http://test').searchParams.get('stage'); const rows = !stage || lead.stage === stage ? [lead] : []; return json({ count: rows.length, page: 1, results: rows }); }
    if (path.endsWith('/activities/') && init?.method === 'POST') { activities.push({ id: 'activity', ...body, assigned_to_name: 'Alice', status: 'planned' }); return json(activities[0]); }
    if (path.endsWith('/activities/activity/complete/')) { activities = activities.map(item => ({ ...item, status: 'done' })); return json(activities[0]); }
    if (path.includes('/activities/?')) { const status = new URL(path, 'http://test').searchParams.get('status'); const rows = activities.filter(item => !status || item.status === status); return json({ count: rows.length, page: 1, results: rows }); }
    throw new Error(`Requête imprévue : ${path}`);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
beforeEach(() => localStorage.clear());
describe('CRM connecté', () => {
  it('déplace une opportunité et recharge la colonne persistée', async () => {
    const fetch = server(); show(base);
    const select = await screen.findByLabelText('Étape de Contrat Alpha');
    await userEvent.selectOptions(select, 'qualified');
    await waitFor(() => expect(within(screen.getByRole('region', { name: 'Étape Qualifié' })).getByRole('heading', { name: 'Contrat Alpha' })).toBeInTheDocument());
    expect(within(screen.getByRole('region', { name: 'Étape Nouveau' })).queryByRole('heading', { name: 'Contrat Alpha' })).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([path, init]) => path.endsWith('/move/') && JSON.parse(init!.body as string).stage === 'qualified')).toBe(true);
  });
  it('crée une opportunité avec un montant exact puis la convertit en client', async () => {
    const fetch = server(); show(base + '/nouveau');
    await userEvent.type(await screen.findByLabelText('Titre'), 'Nouveau contrat');
    const amount = screen.getByLabelText('Revenu attendu');
    await userEvent.clear(amount); await userEvent.type(amount, '42.123456');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer l’opportunité' }));
    expect(await screen.findByRole('heading', { name: 'Nouveau contrat' })).toBeInTheDocument();
    const call = fetch.mock.calls.find(([path, init]) => path.endsWith('/leads/') && init?.method === 'POST')!;
    expect(JSON.parse(call[1]!.body as string).expected_revenue).toBe('42.123456');
    await userEvent.click(screen.getByRole('button', { name: 'Convertir en client' }));
    await userEvent.type(screen.getByLabelText('Nom du client'), 'Client Alpha');
    await userEvent.click(screen.getByRole('button', { name: 'Confirmer la conversion' }));
    expect(await screen.findByRole('link', { name: 'Ouvrir le contact' })).toHaveAttribute('href', '/administration/entreprises/a/contacts/customer');
    expect(screen.queryByRole('button', { name: 'Convertir en client' })).not.toBeInTheDocument();
  });
  it('planifie puis termine une activité sans la laisser dans les activités à faire', async () => {
    const fetch = server(); show(base + '/lead');
    await userEvent.type(await screen.findByLabelText('Description'), 'Appeler le client');
    await userEvent.type(screen.getByLabelText('Échéance'), '2026-11-17T10:30');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer l’activité' }));
    expect(await screen.findByRole('heading', { name: 'Appeler le client' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Terminer' }));
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Appeler le client' })).not.toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText('État des activités'), 'done');
    expect(await screen.findByText('Terminée')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/activity/complete/'))).toBe(true);
  });
  it('masque les actions sans droit et bloque le module désactivé', async () => {
    const fetch = server(false); show(base);
    expect(await screen.findByRole('heading', { name: 'Module désactivé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/crm/'))).toBe(false);
  });
});
