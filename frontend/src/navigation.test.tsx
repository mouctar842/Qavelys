import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

// Données exclusivement isolées dans les tests ; l’application utilise les API Django.
const company = { id: 'a', name: 'Société Alpha', country_code: 'GN', currency_code: 'GNF', sector: 'Services' };
const user = { id: 'user-a', full_name: 'Alice Test', email: 'alice@example.com' };
const permissions = ['company.view', 'members.view', 'members.manage', 'roles.view'];
function RouteProbe() { return <span data-testid="route">{useLocation().pathname}</span>; }
function show(path: string) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={[path]}><App/><RouteProbe/></MemoryRouter></QueryClientProvider>); }
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
function mockApi(options: { empty?: boolean; permissions?: string[]; denyCompany?: boolean } = {}) {
  let companies = options.empty ? [] : [company];
  const members = [{ id: 'self', full_name: 'Alice Test', status: 'active', joined_at: '2026-11-16T09:00:00Z' }, { id: 'employee', full_name: 'Bob Test', status: 'active', joined_at: '2026-11-15T09:00:00Z' }];
  const fetch = vi.fn(async (input: string, init?: RequestInit) => {
    if (input.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (input.endsWith('/auth/register/')) return json({ authenticated: true }, 201);
    if (input.endsWith('/auth/login/')) return json(user);
    if (input.endsWith('/auth/logout/')) return json({ detail: 'Déconnexion effectuée.' });
    if (input.endsWith('/auth/me/')) return json(user);
    if (input === '/api/v1/companies/') {
      if (init?.method === 'POST') { companies = [company]; return json(company, 201); }
      return json(companies);
    }
    if (input.endsWith('/context/')) return options.denyCompany ? json({ detail: 'Entreprise inaccessible.' }, 403) : json({ company, membership_id: 'self', permissions: options.permissions ?? permissions });
    if (input.endsWith('/members/')) return json(members);
    if (input.endsWith('/roles/')) return json([{ id: 'admin', name: 'Administrateur', is_system: true }]);
    if (input.endsWith('/members/employee/suspend/')) { members[1].status = 'suspended'; return json(members[1]); }
    throw new Error(`Appel imprévu : ${input}`);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

beforeEach(() => localStorage.clear());
describe('Navigation reliée aux pages réelles', () => {
  it('relie l’accueil public à l’inscription et à la connexion', async () => {
    show('/');
    expect(screen.getByRole('heading', { name: /Une organisation claire/ })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('link', { name: /Créer mon espace/ })[0]);
    expect(screen.getByRole('heading', { name: 'Créer votre compte' })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('link', { name: 'Se connecter' })[0]);
    expect(screen.getByRole('heading', { name: 'Bienvenue sur Qavelys' })).toBeInTheDocument();
    expect(screen.getByTestId('route')).toHaveTextContent('/login');
  });
  it('enchaîne inscription, création de société, accueil, entreprise, membres, rôles et compte', async () => {
    const fetch = mockApi({ empty: true });
    show('/register');
    await userEvent.type(screen.getByLabelText('Nom complet'), user.full_name);
    await userEvent.type(screen.getByLabelText('E-mail'), user.email);
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'Long-password!2026');
    await userEvent.click(screen.getByRole('button', { name: 'Créer mon compte' }));
    expect(await screen.findByRole('heading', { name: 'Créer une entreprise' })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('Nom de l’entreprise'), company.name);
    await userEvent.type(screen.getByLabelText('Pays (code à 2 lettres)'), 'gn');
    await userEvent.type(screen.getByLabelText('Devise principale'), 'gnf');
    await userEvent.click(screen.getByRole('button', { name: 'Créer mon espace administrateur' }));
    expect(await screen.findByRole('heading', { name: 'Votre administration' })).toBeInTheDocument();
    expect(screen.getByTestId('route')).toHaveTextContent('/administration/entreprises/a');
    const create = fetch.mock.calls.find(([path, init]) => path === '/api/v1/companies/' && init?.method === 'POST')!;
    expect(JSON.parse(create[1]!.body as string)).toMatchObject({ name: company.name, country_code: 'GN', currency_code: 'GNF' });
    expect(create[1]!.headers).toHaveProperty('Idempotency-Key');
    const nav = screen.getByRole('navigation', { name: 'Navigation de l’administration' });
    await userEvent.click(within(nav).getByRole('link', { name: 'Entreprise' }));
    expect(await screen.findByRole('heading', { name: 'Entreprise' })).toBeInTheDocument();
    expect(screen.getByText('Services')).toBeInTheDocument();
    await userEvent.click(within(nav).getByRole('link', { name: 'Collaborateurs' }));
    expect(await screen.findByRole('cell', { name: 'Bob Test' })).toBeInTheDocument();
    await userEvent.type(screen.getByRole('textbox', { name: 'Rechercher un collaborateur' }), 'Bob');
    expect(screen.queryByRole('cell', { name: /Alice Test/ })).not.toBeInTheDocument();
    await userEvent.click(within(nav).getByRole('link', { name: 'Rôles et accès' }));
    expect(await screen.findByRole('heading', { name: 'Administrateur' })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('link', { name: 'Mon compte' })[0]);
    expect(await screen.findByRole('heading', { name: 'Mon compte' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: user.full_name })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Entreprise active' })).toHaveValue('a');
    await userEvent.click(screen.getByRole('link', { name: 'Qavelys, accueil' }));
    expect(await screen.findByRole('heading', { name: 'Votre administration' })).toBeInTheDocument();
    expect(screen.getByTestId('route')).toHaveTextContent('/administration/entreprises/a');
  });
  it('garde l’entreprise et la page dans l’URL à l’ouverture directe', async () => {
    mockApi();
    show('/administration/entreprises/a/roles');
    expect(await screen.findByRole('heading', { name: 'Administrateur' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Entreprise active' })).toHaveValue('a');
    expect(localStorage.getItem('qavelys:company:user-a')).toBe('a');
  });
  it('masque une page sans permission et refuse son URL directe sans requête métier', async () => {
    const fetch = mockApi({ permissions: ['company.view'] });
    show('/administration/entreprises/a/collaborateurs');
    expect(await screen.findByRole('heading', { name: 'Accès non autorisé' })).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Navigation de l’administration' });
    expect(within(nav).queryByRole('link', { name: 'Collaborateurs' })).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/members/'))).toBe(false);
  });
  it('n’affiche pas les données d’une entreprise refusée par le serveur', async () => {
    const fetch = mockApi({ denyCompany: true });
    show('/administration/entreprises/exterieure/collaborateurs');
    expect(await screen.findByRole('alert')).toHaveTextContent('Entreprise inaccessible.');
    expect(screen.queryByRole('cell')).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/members/'))).toBe(false);
  });
  it('confirme la suspension avant d’appeler le backend et recharge les membres', async () => {
    const fetch = mockApi();
    show('/administration/entreprises/a/collaborateurs');
    const bob = await screen.findByRole('row', { name: /Bob Test/ });
    await userEvent.click(within(bob).getByRole('button', { name: 'Suspendre' }));
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/suspend/'))).toBe(false);
    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Confirmer la suspension' }));
    expect(await within(bob).findByText('Suspendu')).toBeInTheDocument();
    expect(fetch.mock.calls.filter(([path]) => path.endsWith('/suspend/'))).toHaveLength(1);
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Filtrer par statut' }), 'suspended');
    expect(screen.queryByRole('cell', { name: /Alice Test/ })).not.toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Bob Test' })).toBeInTheDocument();
  });
  it('déconnecte via le backend et ouvre le formulaire de connexion', async () => {
    const fetch = mockApi();
    show('/administration/compte');
    await screen.findByRole('heading', { name: 'Mon compte' });
    await userEvent.click(screen.getByRole('button', { name: 'Se déconnecter' }));
    expect(await screen.findByRole('heading', { name: 'Bienvenue sur Qavelys' })).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path, init]) => path.endsWith('/auth/logout/') && init?.method === 'POST')).toBe(true);
  });
  it('replie la navigation au passage sur mobile et permet de la rouvrir', async () => {
    vi.stubGlobal('innerWidth', 1200);
    mockApi(); show('/administration/compte');
    await screen.findByRole('heading', { name: 'Mon compte' });
    expect(screen.getByRole('button', { name: 'Réduire la navigation' })).toHaveAttribute('aria-expanded', 'true');
    vi.stubGlobal('innerWidth', 390); fireEvent(window, new Event('resize'));
    expect(screen.getByRole('button', { name: 'Ouvrir la navigation' })).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(screen.getByRole('button', { name: 'Ouvrir la navigation' }));
    expect(screen.getByRole('button', { name: 'Réduire la navigation' })).toHaveAttribute('aria-expanded', 'true');
    await userEvent.click(screen.getByRole('button', { name: 'Fermer le menu' }));
    expect(screen.getByRole('button', { name: 'Ouvrir la navigation' })).toHaveAttribute('aria-expanded', 'false');
  });
  it('affiche une page introuvable au lieu de masquer un lien cassé', () => {
    show('/page-inconnue');
    expect(screen.getByRole('heading', { name: 'Ce chemin ne mène à aucune page.' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Retour à mon espace/ })).toHaveAttribute('href', '/administration');
  });
});
