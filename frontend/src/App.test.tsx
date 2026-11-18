import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

function CurrentRoute() { return <span data-testid="current-route">{useLocation().pathname}</span>; }
function show(path: string) { return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><App/><CurrentRoute/></MemoryRouter></QueryClientProvider>); }
describe('Socle Qavelys', () => {
  it('ouvre l’administration après une inscription connectée sans revenir au formulaire de connexion', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      const responses: Record<string, unknown> = {
        '/api/v1/auth/csrf/': { csrfToken: 'test-only-csrf' },
        '/api/v1/auth/register/': { authenticated: true, detail: 'Compte créé.' },
        '/api/v1/auth/me/': { id: 'new', full_name: 'Nouvel administrateur', email: 'new@example.com' },
        '/api/v1/companies/': [],
      };
      if (!(input in responses)) throw new Error(`Appel imprévu : ${input}`);
      return new Response(JSON.stringify(responses[input]), { status: input.endsWith('/register/') ? 201 : 200, headers: { 'Content-Type': 'application/json' } });
    }));
    show('/register');
    await userEvent.type(screen.getByLabelText('Nom complet'), 'Nouvel administrateur');
    await userEvent.type(screen.getByLabelText('E-mail'), 'new@example.com');
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'Long-password!2026');
    await userEvent.click(screen.getByRole('button', { name: 'Créer mon compte' }));
    expect(await screen.findByRole('heading', { name: 'Administration' })).toBeInTheDocument();
    expect(screen.getByTestId('current-route')).toHaveTextContent('/administration/entreprise/nouvelle');
    expect(await screen.findByRole('heading', { name: 'Créer une entreprise' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Bienvenue sur Qavelys' })).not.toBeInTheDocument();
  });
  it('refuse l’administration sans session et affiche la connexion', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'Authentification requise.' }), { status: 403, headers: { 'Content-Type': 'application/json' } })));
    show('/administration');
    expect(await screen.findByRole('heading', { name: 'Bienvenue sur Qavelys' })).toBeInTheDocument();
    expect(screen.getByTestId('current-route')).toHaveTextContent('/login');
  });
  it('affiche les instructions réelles de remise de l’e-mail après inscription', async () => {
    const detail = 'En développement local, ouvrez le dernier e-mail dans .local/emails.';
    vi.stubGlobal('fetch', vi.fn(async (input: string) => new Response(JSON.stringify(input.endsWith('/csrf/') ? { csrfToken: 'test-only-csrf' } : { detail }), { status: input.endsWith('/csrf/') ? 200 : 202, headers: { 'Content-Type': 'application/json' } })));
    show('/register');
    await userEvent.type(screen.getByLabelText('Nom complet'), 'Compte de test');
    await userEvent.type(screen.getByLabelText('E-mail'), 'test@example.com');
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'Long-password!2026');
    await userEvent.click(screen.getByRole('button', { name: 'Créer mon compte' }));
    expect(await screen.findByRole('status')).toHaveTextContent(detail);
  });
  it('valide le formulaire d’inscription avant tout envoi', async () => {
    show('/register');
    await userEvent.click(screen.getByRole('button', { name: 'Créer mon compte' }));
    expect(await screen.findByText('Nom requis.')).toBeInTheDocument();
    expect(screen.getByText('Au moins 8 caractères.')).toBeInTheDocument();
  });
  it('conserve le choix du thème', async () => {
    localStorage.clear();
    show('/login');
    await userEvent.click(screen.getByRole('button', { name: 'Activer le thème sombre' }));
    expect(document.documentElement).toHaveClass('dark');
    expect(localStorage.getItem('theme')).toBe('dark');
  });
  it('change les collaborateurs affichés avec l’entreprise sélectionnée', async () => {
    // Fixtures exclusivement réservées à ce test : aucun remplacement réseau en production.
    const companies = [
      { id: 'a', name: 'Entreprise A', country_code: 'FR', currency_code: 'EUR', sector: '' },
      { id: 'b', name: 'Entreprise B', country_code: 'SN', currency_code: 'XOF', sector: '' },
    ];
    vi.stubGlobal('fetch', vi.fn(async (input: string) => {
      let data: unknown;
      if (input.endsWith('auth/me/')) data = { id: 'u', full_name: 'Compte de test', email: 'test@example.com' };
      else if (input === '/api/v1/companies/') data = companies;
      else if (input.endsWith('/context/')) data = { company: companies.find(c => input.includes(`/companies/${c.id}/`)), membership_id: 'self', permissions: ['company.view', 'members.view'] };
      else if (input.endsWith('/members/')) data = [{ id: 'member', full_name: input.includes('/companies/a/') ? 'Alice de A' : 'Bob de B', status: 'active' }];
      else throw new Error(`Appel réseau imprévu : ${input}`);
      return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    show('/administration/entreprises/a/collaborateurs');
    expect(await screen.findByRole('cell', { name: 'Alice de A' })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByRole('combobox', { name: /Entreprise active/ }), 'b');
    expect(await screen.findByRole('cell', { name: 'Bob de B' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'Alice de A' })).not.toBeInTheDocument();
    expect(screen.getByTestId('current-route')).toHaveTextContent('/administration/entreprises/b/collaborateurs');
    await userEvent.selectOptions(screen.getByRole('combobox', { name: /Entreprise active/ }), 'a');
    expect(await screen.findByRole('cell', { name: 'Alice de A' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'Bob de B' })).not.toBeInTheDocument();
  });
});
