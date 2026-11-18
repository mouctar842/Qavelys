import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';

const company = { id: 'a', name: 'Entreprise Test', country_code: 'GN', currency_code: 'GNF', sector: 'Services' };
const rights = ['company.view', 'company.manage', 'members.view', 'members.manage', 'roles.view', 'roles.manage', 'modules.view', 'modules.manage', 'audit.view', 'sequences.view'];
function show(path: string) { return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><App/></MemoryRouter></QueryClientProvider>); }
function json(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } }); }
function server(guest = false) {
  let authenticated = !guest;
  const roles = [{ id: 'admin', name: 'Administrateur', is_system: true, permission_codes: rights }];
  const invitations: { id: string; email: string; accepted_at: string | null; revoked_at: string | null; expires_at: string; role_ids: string[] }[] = [];
  const fetch = vi.fn(async (input: string, init?: RequestInit) => {
    const post = init?.method === 'POST';
    const body = post ? JSON.parse(init?.body as string) : {};
    if (input.endsWith('/auth/csrf/')) return json({ csrfToken: 'test-only' });
    if (input.endsWith('/auth/me/')) return authenticated ? json({ id: 'u', full_name: 'Alice', email: 'alice@example.com' }) : json({ detail: 'Authentification requise.' }, 403);
    if (input.endsWith('/auth/login/')) { authenticated = true; return json({ id: 'u' }); }
    if (input === '/api/v1/companies/') return json([company]);
    if (input.endsWith('/context/')) return json({ company, membership_id: 'self', permissions: rights });
    if (input.endsWith('/roles/')) return json(roles);
    if (input.endsWith('/role-templates/')) return json([]);
    if (input.endsWith('/permissions/')) return json([{ code: 'company.view', description: 'Consulter l’entreprise' }, { code: 'members.view', description: 'Consulter les membres' }]);
    if (input.endsWith('/roles/create/')) { const role = { id: 'reader', name: body.name, permission_codes: body.permission_codes, is_system: false }; roles.push(role); return json(role, 201); }
    if (input.endsWith('/invitations/')) { if (post) invitations.push({ id: 'invite', email: body.email, role_ids: body.role_ids, expires_at: '2099-01-01T00:00:00Z', accepted_at: null, revoked_at: null }); return json(post ? invitations[0] : invitations, post ? 201 : 200); }
    if (input.endsWith('/invitations/invite/revoke/')) { invitations[0].revoked_at = '2026-11-16T10:00:00Z'; return json(invitations[0]); }
    if (input.endsWith('/invitations/invite/resend/')) return json(invitations[0]);
    if (input.endsWith('/invitations/accept/')) return json({ company_id: 'a' });
    if (input.endsWith('/auth/password-reset/')) return json({ detail: 'Si un compte existe, un e-mail a été préparé.' }, 202);
    if (input.endsWith('/auth/password-reset-confirm/')) return json({ detail: 'Mot de passe modifié.' });
    throw new Error(`Requête inattendue : ${input}`);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
beforeEach(() => localStorage.clear());
describe('Complétion du noyau', () => {
  it('crée un rôle avec les permissions sélectionnées', async () => {
    const fetch = server();
    show('/administration/entreprises/a/roles');
    await userEvent.type(await screen.findByLabelText('Nom du rôle'), 'Lecteur');
    await userEvent.click(screen.getByRole('checkbox', { name: /Consulter l’entreprise/ }));
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le rôle' }));
    expect(await screen.findByRole('heading', { name: 'Lecteur' })).toBeInTheDocument();
    const call = fetch.mock.calls.find(([path]) => path.endsWith('/roles/create/'))!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({ name: 'Lecteur', permission_codes: ['company.view'] });
  });
  it('envoie, renvoie et révoque une invitation réelle par les actions API', async () => {
    const fetch = server();
    show('/administration/entreprises/a/invitations');
    await userEvent.type(await screen.findByLabelText('E-mail du collaborateur'), 'bob@example.com');
    await userEvent.click(screen.getByRole('checkbox', { name: 'Administrateur' }));
    await userEvent.click(screen.getByRole('button', { name: 'Envoyer l’invitation' }));
    const row = await screen.findByRole('row', { name: /bob@example.com/ });
    await userEvent.click(within(row).getByRole('button', { name: 'Renvoyer' }));
    await userEvent.click(within(row).getByRole('button', { name: 'Révoquer' }));
    expect(await within(row).findByText('Révoquée')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/resend/'))).toBe(true);
  });
  it('demande une récupération et contrôle les deux nouveaux mots de passe', async () => {
    const fetch = server();
    const view = show('/forgot-password');
    await userEvent.type(screen.getByLabelText('E-mail'), 'alice@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Envoyer le lien' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Si un compte existe');
    view.unmount();
    show('/reset-password#uid=test-user&token=test-token');
    await userEvent.type(screen.getByLabelText('Nouveau mot de passe'), 'New-strong-password!2026');
    await userEvent.type(screen.getByLabelText('Confirmer le mot de passe'), 'différent');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le mot de passe' }));
    expect(await screen.findByText('Les mots de passe doivent être identiques.')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([path]) => path.endsWith('/password-reset-confirm/'))).toBe(false);
    await userEvent.clear(screen.getByLabelText('Confirmer le mot de passe'));
    await userEvent.type(screen.getByLabelText('Confirmer le mot de passe'), 'New-strong-password!2026');
    await userEvent.click(screen.getByRole('button', { name: 'Enregistrer le mot de passe' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Mot de passe modifié.');
  });
  it('conserve une invitation pendant la connexion puis ouvre son entreprise', async () => {
    const fetch = server(true);
    show('/invitation#token=private-test-token');
    await screen.findByText('Connectez-vous ou créez votre compte avec l’adresse qui a reçu l’invitation.');
    await userEvent.click(screen.getAllByRole('link', { name: 'Se connecter' }).find(link => link.closest('main'))!);
    await userEvent.type(screen.getByLabelText('E-mail'), 'alice@example.com');
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'Long-password!2026');
    await userEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Accepter l’invitation' }));
    expect(await screen.findByRole('heading', { name: 'Votre administration' })).toBeInTheDocument();
    const call = fetch.mock.calls.find(([path]) => path.endsWith('/invitations/accept/'))!;
    expect(JSON.parse(call[1]!.body as string)).toEqual({ token: 'private-test-token' });
  });
});
