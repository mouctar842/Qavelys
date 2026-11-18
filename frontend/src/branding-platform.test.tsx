import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const base = '/administration/entreprises/a';
function show(path: string) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
function server({ platform = true, logoError = false, platformError = false, changeError = false } = {}) {
  const companies = [{ id: 'a', name: 'Entreprise Alpha', country_code: 'FR', currency_code: 'EUR', sector: '', logo_url: '/api/v1/companies/a/logo/old/' }, { id: 'b', name: 'Entreprise Beta', country_code: 'GN', currency_code: 'GNF', sector: '', logo_url: null as string | null }];
  const rows = [{ ...companies[0], status: 'active', owner_email: 'owner@example.invalid', member_count: 2 }];
  const audit: { id: string; action: string; target: string; reason: string; actor: string; created_at: string }[] = [];
  const users = [{ id: 'operator', email: 'operator@example.invalid', full_name: 'Opérateur', is_active: true, is_platform_admin: true, email_verified: true }, { id: 'reader', email: 'reader@example.invalid', full_name: 'Lecteur', is_active: true, is_platform_admin: false, email_verified: false }];
  const fetch = vi.fn(async (input: string, init?: RequestInit) => {
    const url = new URL(input, 'http://test.local'); const path = url.pathname;
    if (path.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (path.endsWith('/auth/me/')) return json({ id: 'operator', email: 'operator@example.invalid', full_name: 'Opérateur', is_platform_admin: platform });
    if (path === '/api/v1/companies/') return json(companies);
    const companyId = path.match(/\/companies\/(a|b)\//)?.[1];
    const company = companies.find(row => row.id === companyId);
    if (company && path.endsWith('/context/')) return json({ company, membership_id: 'member', permissions: ['company.view', 'company.manage'], modules: ['core'] });
    if (company && path.endsWith('/settings/')) return json({ ...company, address: '', phone: '', timezone: 'UTC', locale: 'fr' });
    if (company && path.endsWith('/logo/')) {
      if (logoError) return json({ logo: ['Image invalide.'] }, 400);
      company.logo_url = `/api/v1/companies/${company.id}/logo/new/`; return json({ logo_url: company.logo_url }, 201);
    }
    if (path.startsWith('/api/v1/platform/') && platformError) return json({ detail: 'Accès plateforme retiré.' }, 403);
    if (path.endsWith('/platform/overview/')) return json({ companies: 1, active_companies: rows.filter(row => row.status === 'active').length, users: users.length, active_users: users.filter(row => row.is_active).length, available_modules: 1 });
    if (path === '/api/v1/platform/companies/') {
      const search = url.searchParams.get('search') || ''; const status = url.searchParams.get('status');
      const result = rows.filter(row => row.name.includes(search) && (!status || row.status === status));
      return json({ count: result.length, page: 1, page_size: 25, results: result });
    }
    if (path === '/api/v1/platform/users/') return json({ count: users.length, page: 1, page_size: 25, results: users });
    if (path === '/api/v1/platform/modules/') return json({ count: 1, page: 1, page_size: 25, results: [{ id: 'core', name: 'Administration', code: 'core', description: 'Noyau', status: 'available', enabled_companies: 1 }] });
    if (path === '/api/v1/platform/audit/') return json({ count: audit.length, page: 1, page_size: 25, results: audit });
    if (path.match(/\/platform\/(companies|users)\/.+\/(suspend|activate|deactivate)\//)) {
      if (changeError) return json({ detail: 'Dernier administrateur actif.' }, 400);
      const body = JSON.parse(init!.body as string);
      if (path.includes('/companies/')) rows[0].status = path.endsWith('/suspend/') ? 'suspended' : 'active';
      else users[1].is_active = path.endsWith('/activate/');
      audit.push({ id: 'audit', action: 'company.suspended', target: 'Entreprise Alpha', reason: body.reason, actor: 'operator@example.invalid', created_at: '2026-11-17T12:00:00Z' });
      return json({ id: 'a' });
    }
    throw new Error(`Requête inattendue : ${input}`);
  });
  vi.stubGlobal('fetch', fetch); return fetch;
}
beforeEach(() => localStorage.clear());

describe('Logo fourni par l’entreprise', () => {
  it('importe en multipart avec CSRF et actualise le logo courant', async () => {
    const fetch = server(); show(base + '/parametres');
    const image = await screen.findByRole('img', { name: 'Logo de Entreprise Alpha' });
    expect(image).toHaveAttribute('src', '/api/v1/companies/a/logo/old/');
    const file = new File(['unit-test-image'], 'fourni.png', { type: 'image/png' });
    await userEvent.upload(screen.getByLabelText('Fichier du logo'), file);
    await userEvent.click(screen.getByRole('button', { name: 'Importer le logo' }));
    expect(await screen.findByText('Logo enregistré.')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: 'Logo de Entreprise Alpha' })).toHaveAttribute('src', '/api/v1/companies/a/logo/new/');
    const upload = fetch.mock.calls.find(([path]) => path.endsWith('/companies/a/logo/'))![1]!;
    expect(upload.body).toBeInstanceOf(FormData);
    expect((upload.body as FormData).get('logo')).toBe(file);
    expect(upload.headers).toEqual({ 'X-CSRFToken': 'test-only' });
  });
  it('garde le logo précédent si le serveur refuse le fichier', async () => {
    server({ logoError: true }); show(base + '/parametres');
    await userEvent.upload(await screen.findByLabelText('Fichier du logo'), new File(['x'], 'invalide.png', { type: 'image/png' }));
    await userEvent.click(screen.getByRole('button', { name: 'Importer le logo' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Image invalide.');
    expect(screen.getByRole('img', { name: 'Logo de Entreprise Alpha' })).toHaveAttribute('src', '/api/v1/companies/a/logo/old/');
  });
  it('refuse un fichier trop volumineux avant envoi et change de logo avec la société', async () => {
    const fetch = server(); show(base + '/parametres');
    const input = await screen.findByLabelText('Fichier du logo');
    const large = new File(['x'], 'grand.png', { type: 'image/png' }); Object.defineProperty(large, 'size', { value: 2097153 });
    await userEvent.upload(input, large);
    expect(screen.getByRole('alert')).toHaveTextContent('2 Mio');
    expect(screen.getByRole('button', { name: 'Importer le logo' })).toBeDisabled();
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/logo/'))).toBe(false);
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Entreprise active' }), 'b');
    expect(await screen.findByText('Logo de l’entreprise')).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: 'Logo de Entreprise Alpha' })).not.toBeInTheDocument();
    expect(screen.getAllByLabelText('Entreprise Entreprise Beta').length).toBeGreaterThan(0);
  });
});

describe('Console plateforme séparée', () => {
  it('refuse un utilisateur ordinaire avant toute requête globale', async () => {
    const fetch = server({ platform: false }); show('/plateforme');
    expect(await screen.findByRole('heading', { name: 'Accès plateforme non autorisé' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('/platform/'))).toBe(false);
  });
  it('confirme une suspension motivée, recharge les listes et consulte le journal', async () => {
    const fetch = server(); show('/plateforme');
    await userEvent.click(await screen.findByRole('button', { name: 'Suspendre Entreprise Alpha' }));
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/suspend/'))).toBe(false);
    const form = screen.getByRole('region', { name: 'Confirmer le changement d’accès' });
    expect(within(form).getByRole('button', { name: 'Confirmer le changement' })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText('Motif du changement'), 'Demande de contrôle');
    await userEvent.click(within(form).getByRole('button', { name: 'Confirmer le changement' }));
    expect(await screen.findByRole('button', { name: 'Réactiver Entreprise Alpha' })).toBeInTheDocument();
    const call = fetch.mock.calls.find(([path]) => path.endsWith('/companies/a/suspend/'))!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({ reason: 'Demande de contrôle' });
    await userEvent.click(screen.getByRole('button', { name: 'Journal plateforme' }));
    expect(await screen.findByRole('cell', { name: 'Entreprise suspendue' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Demande de contrôle' })).toBeInTheDocument();
  });
  it('affiche les refus serveur et conserve la confirmation sans faux succès', async () => {
    server({ changeError: true }); show('/plateforme');
    await userEvent.click(await screen.findByRole('button', { name: 'Suspendre Entreprise Alpha' }));
    await userEvent.type(screen.getByLabelText('Motif du changement'), 'Demande de contrôle');
    await userEvent.click(screen.getByRole('button', { name: 'Confirmer le changement' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Dernier administrateur actif.');
    expect(screen.getByRole('button', { name: 'Suspendre Entreprise Alpha' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Annuler le changement' }));
    expect(screen.queryByRole('region', { name: 'Confirmer le changement d’accès' })).not.toBeInTheDocument();
  });
  it('recherche, filtre et affiche les comptes et le catalogue sans action fictive', async () => {
    const fetch = server(); show('/plateforme');
    await screen.findByRole('button', { name: 'Suspendre Entreprise Alpha' });
    await userEvent.type(screen.getByLabelText('Rechercher dans la plateforme'), 'Absent');
    expect(await screen.findByText('Aucun résultat.')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.includes('search=Absent'))).toBe(true);
    await userEvent.click(screen.getByRole('button', { name: 'Utilisateurs' }));
    expect(await screen.findByRole('button', { name: 'Désactiver operator@example.invalid' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Désactiver reader@example.invalid' })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: 'Modules' }));
    expect(await screen.findByRole('cell', { name: 'Disponible' })).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Modules' })).toBeInTheDocument();
  });
  it('montre le refus API si les droits viennent d’être retirés', async () => {
    server({ platformError: true }); show('/plateforme');
    expect((await screen.findAllByRole('alert'))[0]).toHaveTextContent('Accès plateforme retiré.');
    expect(screen.queryByRole('region', { name: 'Indicateurs plateforme' })).not.toBeInTheDocument();
  });
});
