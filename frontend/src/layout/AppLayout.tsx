import { CompanyMark } from '../components/company-logo';
import { useEffect, useState } from 'react';
import type { LucideIcon } from 'lucide-react';
import { Bell as BellIcon, Building2, ChevronRight, LayoutDashboard, LogOut, Menu, Plus, ShieldCheck, UserRound, Users, X, Settings, Mail, Blocks, History, ListOrdered } from 'lucide-react';
import { Link, NavLink, Navigate, Outlet, useLocation, useMatch, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, companyKey, type Company, type User } from '../api';
import { Button } from '../components/ui/button';
import { ErrorMessage, Failure, Loading } from '../components/feedback';
import { ThemeToggle } from '../theme';
import { Brand } from '../pages/public';
import { companyPath, rememberCompany, rememberedCompany, useWorkspace, type CompanyContext, type WorkspaceContext } from '../workspace';
import { NotificationBell } from '../pages/notifications';

type NavEntry = { to: string; title: string; icon: LucideIcon; permission: string; end?: boolean; module?: string };

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const [collapsed, setCollapsed] = useState(() => window.innerWidth < 900);
  const match = useMatch('/administration/entreprises/:companyId/*');
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<User>('auth/me/'), retry: false });
  const companies = useQuery({ queryKey: ['companies'], queryFn: () => api<Company[]>('companies/'), enabled: me.isSuccess, retry: false });
  const saved = me.data ? rememberedCompany(me.data.id) : null;
  const companyId = match?.params.companyId ?? (companies.data?.find(company => company.id === saved) ?? companies.data?.[0])?.id ?? '';
  const context = useQuery({ queryKey: companyKey(companyId, 'context'), queryFn: () => api<CompanyContext>(`companies/${companyId}/context/`), enabled: me.isSuccess && Boolean(companyId), retry: false });
  const signOut = useMutation({ mutationFn: () => api('auth/logout/', {}), onSuccess: () => { cache.clear(); navigate('/login', { replace: true }); } });
  useEffect(() => { if (me.data && context.data && !context.error) rememberCompany(me.data.id, context.data.company.id); }, [me.data, context.data, context.error]);
  useEffect(() => { if (window.innerWidth < 900) setCollapsed(true); }, [location.pathname]);
  useEffect(() => {
    const closeOnNarrowViewport = () => { if (window.innerWidth < 900) setCollapsed(true); };
    window.addEventListener('resize', closeOnNarrowViewport);
    return () => window.removeEventListener('resize', closeOnNarrowViewport);
  }, []);
  if (me.isPending) return <Loading/>;
  if (me.error instanceof ApiError && me.error.status === 403) return <Navigate to="/login" state={{ from: location.pathname }} replace/>;
  if (me.error) return <main className="verification-layout"><Failure error={me.error} retry={() => void me.refetch()}/><Link to="/">Retour à l’accueil</Link></main>;
  if (companies.isPending) return <Loading text="Chargement de vos entreprises…"/>;
  if (companies.error) return <main className="verification-layout"><Failure error={companies.error} retry={() => void companies.refetch()}/><Button variant="outline" onClick={() => signOut.mutate()}>Se déconnecter</Button><ErrorMessage error={signOut.error}/></main>;
  const permissions = context.error ? [] : context.data?.permissions ?? [];
  const base = companyPath(companyId);
  const entries: NavEntry[] = [{ to: base, title: 'Vue d’ensemble', icon: LayoutDashboard, permission: 'company.view', end: true }, { to: `${base}/entreprise`, title: 'Entreprise', icon: Building2, permission: 'company.view' }, { to: `${base}/collaborateurs`, title: 'Collaborateurs', icon: Users, permission: 'members.view' }, { to: `${base}/roles`, title: 'Rôles et accès', icon: ShieldCheck, permission: 'roles.view' }, { to: `${base}/invitations`, title: 'Invitations', icon: Mail, permission: 'members.manage' }, { to: `${base}/parametres`, title: 'Paramètres', icon: Settings, permission: 'company.manage' }, { to: `${base}/modules`, title: 'Modules', icon: Blocks, permission: 'modules.view' }, { to: `${base}/audit`, title: 'Audit', icon: History, permission: 'audit.view' }, { to: `${base}/sequences`, title: 'Numérotation des documents', icon: ListOrdered, permission: 'sequences.view' }];
  entries.push({ to: `${base}/employes`, title: 'Employés', icon: Users, permission: 'hr.employee.view', module: 'hr' }, { to: `${base}/departements`, title: 'Départements', icon: Building2, permission: 'hr.department.view', module: 'hr' }, { to: `${base}/missions`, title: 'Missions', icon: ListOrdered, permission: 'hr.mission.view', module: 'hr' });
  entries.push({ to: `${base}/clients`, title: 'Clients', icon: Users, permission: 'contacts.view', module: 'contacts' }, { to: `${base}/fournisseurs`, title: 'Fournisseurs', icon: Users, permission: 'contacts.view', module: 'contacts' }, { to: `${base}/produits`, title: 'Produits et services', icon: Blocks, permission: 'products.view', module: 'catalog' }, { to: `${base}/categories`, title: 'Catégories', icon: ListOrdered, permission: 'categories.view', module: 'catalog' }, { to: `${base}/taxes`, title: 'Taxes', icon: ListOrdered, permission: 'taxes.view', module: 'catalog' }, { to: `${base}/unites`, title: 'Unités', icon: ListOrdered, permission: 'products.view', module: 'catalog' });
  entries.push({ to: `${base}/crm`, title: 'CRM', icon: Users, permission: 'crm.view', module: 'crm' });
  entries.push({ to: `${base}/inventaire/stocks`, title: 'Inventaire', icon: Blocks, permission: 'inventory.view', module: 'inventory' });
  entries.push({ to: `${base}/ventes`, title: 'Ventes', icon: ListOrdered, permission: 'sales.order.view', module: 'sales' }, { to: `${base}/achats`, title: 'Achats', icon: ListOrdered, permission: 'purchases.order.view', module: 'purchases' }, { to: `${base}/approbations`, title: 'Approbations', icon: ShieldCheck, permission: 'approvals.requests.view' }, { to: `${base}/regles-approbation`, title: 'Règles d’approbation', icon: Settings, permission: 'approvals.rules.view' });
  const value: WorkspaceContext = { user: me.data, companies: companies.data, companyId, context: context.error ? undefined : context.data, contextLoading: context.isPending, contextError: context.error, retryContext: () => void context.refetch() };
  entries.push({ to: `${base}/factures`, title: 'Factures', icon: ListOrdered, permission: 'invoicing.invoice.view', module: 'invoicing' });
  entries.push({ to: `${base}/paiements`, title: 'Paiements', icon: ListOrdered, permission: 'invoicing.payment.view', module: 'invoicing' });
  entries.push({ to: `${base}/tableau-de-bord`, title: 'Tableau de bord', icon: LayoutDashboard, permission: 'dashboard.view', module: 'dashboard' }, { to: `${base}/notifications`, title: 'Notifications', icon: BellIcon, permission: 'notifications.view', module: 'core' });
  if (permissions.includes('invoicing.invoice.view')) entries.push({ to: `${base}/avoirs`, title: 'Avoirs', icon: ListOrdered, permission: 'invoicing.credit_note.view', module: 'invoicing' });
  function switchCompany(id: string) {
    const suffix = match ? location.pathname.slice(companyPath(companyId).length) : '';
    navigate(`${companyPath(id)}${suffix}`);
  }
  return <div className={`app-shell ${collapsed ? 'is-collapsed' : ''}`}>
    {!collapsed && <button className="sidebar-scrim" aria-label="Fermer le menu" onClick={() => setCollapsed(true)}/>}
    <aside className="app-sidebar"><Brand to="/administration"/><button className="icon-button sidebar-close" aria-label="Fermer la navigation" onClick={() => setCollapsed(true)}><X size={20}/></button><div className="sidebar-section-label">ESPACE DE TRAVAIL</div><nav aria-label="Navigation de l’administration">{companyId && entries.filter(entry => permissions.includes(entry.permission) && (!entry.module || context.data?.modules?.includes(entry.module))).map(entry => <NavLink key={entry.to} to={entry.to} end={entry.end} aria-label={entry.title} title={entry.title} onClick={() => { if (window.innerWidth < 900) setCollapsed(true); }}><entry.icon size={20} aria-hidden="true"/><span>{entry.title}</span></NavLink>)}{!companyId && <NavLink to="/administration" end aria-label="Administration"><LayoutDashboard size={20}/><span>Administration</span></NavLink>}<NavLink to="/administration/entreprise/nouvelle" aria-label="Nouvelle entreprise" title="Nouvelle entreprise"><Plus size={20}/><span>Nouvelle entreprise</span></NavLink></nav><div className="sidebar-bottom">{me.data.is_platform_admin && <NavLink to="/plateforme" aria-label="Administration plateforme" title="Administration plateforme"><ShieldCheck size={20}/><span>Plateforme</span></NavLink>}<NavLink to="/administration/compte" aria-label="Mon compte" title="Mon compte"><UserRound size={20}/><span>Mon compte</span></NavLink><button className="sidebar-logout" onClick={() => signOut.mutate()} disabled={signOut.isPending} aria-label="Se déconnecter" title="Se déconnecter"><LogOut size={19}/><span>Se déconnecter</span></button><div className="sidebar-user"><span className="avatar">{me.data.full_name.slice(0, 1).toUpperCase()}</span><div><strong>{me.data.full_name}</strong><small>{me.data.email}</small></div></div></div></aside><div className="app-body"><header className="app-topbar"><button className="icon-button" onClick={() => setCollapsed(value => !value)} aria-label={collapsed ? 'Ouvrir la navigation' : 'Réduire la navigation'} aria-expanded={!collapsed}><Menu size={21}/></button><div className="topbar-context"><span>Espace de travail</span><ChevronRight size={15}/><strong>{context.data && !context.error ? context.data.company.name : 'Administration'}</strong></div><label className="topbar-company"><span aria-hidden="true">{context.data && !context.error ? <CompanyMark key={companyId} company={context.data.company}/> : <Building2 size={17}/>}</span><span className="sr-only">Entreprise active</span><select aria-label="Entreprise active" value={companyId} disabled={!companies.data.length} onChange={event => switchCompany(event.target.value)}><option value="" disabled>{companyId ? 'Entreprise indisponible' : 'Choisir une entreprise'}</option>{companies.data.map(company => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label><NotificationBell key={companyId} companyId={companyId} enabled={Boolean(!context.error && permissions.includes('notifications.view') && context.data?.modules?.includes('core'))}/><ThemeToggle/></header><main className="app-main"><ErrorMessage error={signOut.error}/><Outlet context={value}/></main><footer className="app-footer"><span>Qavelys · Espace entreprise</span><Link to="/administration/compte">Mon compte</Link></footer></div></div>;
}

export function WorkspaceStart() {
  const { user, companies } = useWorkspace();
  const saved = rememberedCompany(user.id);
  const selected = companies.find(company => company.id === saved) ?? companies[0];
  return <Navigate to={selected ? companyPath(selected.id) : '/administration/entreprise/nouvelle'} replace/>;
}

export function CompanyGate({ permission = 'company.view', module }: { permission?: string; module?: string }) {
  const workspace = useWorkspace();
  if (workspace.contextLoading) return <Loading text="Chargement des accès à cette entreprise…"/>;
  if (workspace.contextError) return <Failure error={workspace.contextError} retry={workspace.retryContext}/>;
  if (!workspace.context?.permissions.includes(permission)) return <section className="card empty-state"><ShieldCheck size={32}/><h1>Accès non autorisé</h1><p>Votre rôle ne vous permet pas de consulter cette page. Choisissez une autre page ou une autre entreprise.</p><Link to="/administration">Retour à mon espace</Link></section>;
  if (module && !workspace.context.modules?.includes(module)) return <section className="card empty-state"><h1>Module désactivé</h1><p>Ce module doit être activé pour cette entreprise. Les données existantes sont conservées.</p>{workspace.context.permissions.includes('modules.view') && <Link to={`${companyPath(workspace.companyId)}/modules`}>Configurer les modules</Link>}</section>;
  return <Outlet key={workspace.companyId} context={workspace}/>;
}
