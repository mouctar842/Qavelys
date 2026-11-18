import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import App from './App';

const companies = [{ id: 'a', name: 'Équipe A', country_code: 'FR', currency_code: 'EUR' }, { id: 'b', name: 'Équipe B', country_code: 'FR', currency_code: 'EUR' }];
const rights = ['company.view', 'members.view', 'hr.employee.view', 'hr.employee.manage', 'hr.department.view', 'hr.department.manage', 'hr.mission.view', 'hr.mission.manage'];
const employee = { id: 'e', version: 1, staff_code: 'EMP-01', full_name: 'Aminata Diallo', status: 'active', job_title: 'Technicienne', responsibilities: 'Contrôle qualité', membership_id: null, department_id: 'd', department_name: 'Atelier' };
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
function show(path: string) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[`/administration/entreprises/a/${path}`]}><App/></MemoryRouter></QueryClientProvider>); }
function server({ readonly = false, conflict = false, seedEmployee = false, seedMission = false } = {}) {
  const records: Record<string, Record<string, unknown>[]> = { employees: seedEmployee ? [{ ...employee }] : [], departments: [{ id: 'd', name: 'Atelier', status: 'active', version: 1 }], missions: seedMission ? [{ id: 'm', title: 'Contrôle atelier', employee_id: 'e', employee_name: 'Aminata Diallo', status: 'todo', version: 1, completed_at: null }] : [] };
  const fetch = vi.fn(async (input: string, init?: RequestInit) => {
    const parsed = new URL(input, 'http://test'); const path = parsed.pathname; const post = init?.method === 'POST'; const body = post ? JSON.parse(init?.body as string) : {};
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test' });
    if (path.endsWith('/auth/me/')) return json({ id: 'user', full_name: 'Gestionnaire', email: 'test@example.com' });
    if (path === '/api/v1/companies/') return json(companies);
    if (path.endsWith('/context/')) return json({ company: companies[path.includes('/b/') ? 1 : 0], membership_id: 'self', permissions: readonly ? rights.filter(item => !item.endsWith('.manage')) : rights, modules: ['core', 'hr'] });
    if (path.endsWith('/hr/lookups/')) return json({ departments: [{ id: 'd', name: 'Atelier' }], employees: [{ id: 'e', full_name: 'Aminata Diallo', staff_code: 'EMP-01' }], memberships: [{ id: 'existing', name: 'Compte existant', email: 'external@example.com' }] });
    const match = path.match(/\/hr\/(employees|departments|missions)\/(?:([^/]+)\/)?(?:([^/]+)\/)?$/);
    if (match) {
      const [, resource, id, action] = match; const rows = path.includes('/b/') ? [] : records[resource];
      if (!id) {
        if (post) { const row = { ...body, id: resource === 'employees' ? 'e' : resource === 'missions' ? 'm' : 'd2', version: 1, status: resource === 'missions' ? 'todo' : 'active', department_name: body.department_id ? 'Atelier' : null, membership_status: body.membership_id ? 'active' : null, employee_name: body.employee_id ? 'Aminata Diallo' : undefined }; records[resource].push(row); return json(row, 201); }
        const state = parsed.searchParams.get('state') || 'active'; const search = parsed.searchParams.get('search')?.toLowerCase() || '';
        const filtered = rows.filter(row => (state === 'all' || row.status === state) && JSON.stringify(row).toLowerCase().includes(search));
        return json({ count: filtered.length, results: filtered });
      }
      const row = rows.find(item => item.id === id)!;
      if (post && conflict) return json({ detail: 'La fiche a changé. Rechargez-la.' }, 409);
      if (action && post) { row.status = { archive: 'archived', restore: 'active', start: 'in_progress', complete: 'done', cancel: 'cancelled', reopen: 'todo' }[action]; row.version = Number(row.version) + 1; row.completed_at = action === 'complete' ? '2026-11-17T10:00:00Z' : null; }
      else if (post) Object.assign(row, body, { version: Number(row.version) + 1 });
      return json(row);
    }
    throw new Error(`Appel inattendu : ${input}`);
  }); vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => localStorage.clear());

it('enregistre une fiche sans compte avec le département et des responsabilités', async () => {
  const fetch = server(); show('employes/nouveau');
  await userEvent.type(await screen.findByLabelText('Matricule'), 'EMP-01');
  await userEvent.type(screen.getByLabelText('Nom complet de l’employé'), 'Aminata Diallo');
  await userEvent.selectOptions(screen.getByLabelText('Département'), 'd');
  await userEvent.type(screen.getByLabelText('Responsabilités'), 'Contrôle qualité');
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer la fiche' }));
  expect(await screen.findByRole('heading', { name: 'Aminata Diallo' })).toBeInTheDocument();
  expect(screen.getByText('Sans accès Qavelys', { selector: 'dd' })).toBeInTheDocument();
  const call = fetch.mock.calls.find(([path, init]) => path.endsWith('/hr/employees/') && init?.method === 'POST')!;
  const payload = JSON.parse(call[1]!.body as string);
  expect(payload).toMatchObject({ department_id: 'd', membership_id: null, responsibilities: 'Contrôle qualité' });
  expect(payload.request_key).toBeTruthy();
  expect(fetch.mock.calls.some(([path]) => path.includes('/auth/register/'))).toBe(false);
});

it('valide le matricule et le nom avant toute création', async () => {
  const fetch = server(); show('employes/nouveau');
  await userEvent.click(await screen.findByRole('button', { name: 'Enregistrer la fiche' }));
  expect(await screen.findByText('Ce champ est requis.')).toBeInTheDocument();
  expect(screen.getByText(/Matricule requis/)).toBeInTheDocument();
  expect(fetch.mock.calls.some(([path, init]) => path.endsWith('/hr/employees/') && init?.method === 'POST')).toBe(false);
});

it('lie un accès existant sans mutation des rôles ni du compte global', async () => {
  const fetch = server(); show('employes/nouveau');
  await userEvent.type(await screen.findByLabelText('Matricule'), 'LINK');
  await userEvent.type(screen.getByLabelText('Nom complet de l’employé'), 'Nom local');
  await userEvent.selectOptions(screen.getByLabelText('Accès utilisateur Qavelys facultatif'), 'existing');
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer la fiche' }));
  expect(await screen.findByRole('heading', { name: 'Nom local' })).toBeInTheDocument();
  const call = fetch.mock.calls.find(([path, init]) => path.endsWith('/hr/employees/') && init?.method === 'POST')!;
  expect(JSON.parse(call[1]!.body as string).membership_id).toBe('existing');
  expect(fetch.mock.calls.some(([path, init]) => init?.method === 'POST' && (path.includes('/roles/') || path.endsWith('/auth/me/')))).toBe(false);
});

it('applique les transitions de mission avec confirmation et version attendue', async () => {
  const fetch = server({ seedEmployee: true, seedMission: true }); vi.spyOn(window, 'confirm').mockReturnValue(true); show('missions/m');
  await userEvent.click(await screen.findByRole('button', { name: 'Démarrer' }));
  expect(await screen.findByText('En cours', { selector: '.page-heading p' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Terminer' }));
  expect(await screen.findByText('Terminée', { selector: '.page-heading p' })).toBeInTheDocument();
  expect(JSON.parse(fetch.mock.calls.find(([path]) => path.endsWith('/missions/m/complete/'))![1]!.body as string)).toEqual({ version: 2 });
});

it('préremplit l’employé depuis le lien d’attribution et enregistre la mission', async () => {
  const fetch = server({ seedEmployee: true }); show('missions/nouveau?employee=e');
  expect(await screen.findByLabelText('Employé affecté')).toHaveValue('e');
  await userEvent.type(screen.getByLabelText('Intitulé de la mission'), 'Préparer les équipements');
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer la fiche' }));
  expect(await screen.findByRole('heading', { name: 'Préparer les équipements' })).toBeInTheDocument();
  const call = fetch.mock.calls.find(([path, init]) => path.endsWith('/hr/missions/') && init?.method === 'POST')!;
  expect(JSON.parse(call[1]!.body as string)).toMatchObject({ employee_id: 'e', due_date: null });
});

it('préserve le formulaire et affiche le conflit réel de version', async () => {
  server({ seedEmployee: true, conflict: true }); show('employes/e/modifier');
  const input = await screen.findByLabelText('Poste');
  await userEvent.clear(input); await userEvent.type(input, 'Responsable atelier');
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer la fiche' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('La fiche a changé');
  expect(input).toHaveValue('Responsable atelier');
});

it('sépare les employés des sociétés et masque les actions à un lecteur', async () => {
  server({ seedEmployee: true, readonly: true }); show('employes');
  expect(await screen.findByRole('link', { name: 'Aminata Diallo' })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Créer · Employé' })).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Entreprise active' }), 'b');
  expect(await screen.findByText('Aucun résultat. Les données apparaîtront après leur enregistrement.')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Aminata Diallo' })).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Entreprise active' }), 'a');
  await userEvent.click(await screen.findByRole('link', { name: 'Aminata Diallo' }));
  const card = (await screen.findByRole('heading', { name: 'Aminata Diallo' })).closest('main')!;
  expect(within(card).queryByRole('button', { name: 'Archiver' })).not.toBeInTheDocument();
});
