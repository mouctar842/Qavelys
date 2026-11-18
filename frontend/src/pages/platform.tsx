import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type User } from '../api';
import { Button } from '../components/ui/button';
import { ErrorMessage, Failure, Loading } from '../components/feedback';
import { Brand } from './public';
import { ThemeToggle } from '../theme';

type Section = 'companies' | 'users' | 'modules' | 'audit';
type Row = { id: string; name?: string; email?: string; full_name?: string; status?: string; country_code?: string; currency_code?: string; owner_email?: string; member_count?: number; is_active?: boolean; is_platform_admin?: boolean; email_verified?: boolean; created_at?: string; action?: string; actor?: string; target?: string; reason?: string; enabled_companies?: number; description?: string; code?: string };
type Page = { count: number; page: number; page_size: number; results: Row[] };
const sections: Record<Section, string> = { companies: 'Entreprises', users: 'Utilisateurs', modules: 'Modules', audit: 'Journal plateforme' };
const actions: Record<string, string> = { 'company.suspended': 'Entreprise suspendue', 'company.activated': 'Entreprise réactivée', 'user.deactivated': 'Compte désactivé', 'user.activated': 'Compte réactivé', 'user.platform_access_granted': 'Accès plateforme attribué' };

export function PlatformPage() {
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<User>('auth/me/'), retry: false });
  if (me.isPending) return <Loading/>;
  if (me.error instanceof ApiError && me.error.status === 403) return <Navigate to="/login" replace/>;
  if (me.error) return <main className="verification-layout"><Failure error={me.error} retry={() => void me.refetch()}/></main>;
  if (!me.data.is_platform_admin) return <main className="verification-layout"><section className="card"><h1>Accès plateforme non autorisé</h1><p>Ce compte ne possède pas le rôle de super-administrateur plateforme.</p><Link to="/administration">Retour à mon espace</Link></section></main>;
  return <PlatformConsole me={me.data}/>;
}

function PlatformConsole({ me }: { me: User }) {
  const cache = useQueryClient();
  const [section, setSection] = useState<Section>('companies');
  const [search, setSearch] = useState(''); const [status, setStatus] = useState(''); const [page, setPage] = useState(1); const [ordering, setOrdering] = useState('name');
  const [pending, setPending] = useState<{ row: Row; resource: 'companies' | 'users'; action: string } | null>(null);
  const [reason, setReason] = useState('');
  const overview = useQuery({ queryKey: ['platform', 'overview'], queryFn: () => api<{ companies: number; active_companies: number; users: number; active_users: number; available_modules: number }>('platform/overview/'), retry: false });
  const rows = useQuery({ queryKey: ['platform', section, search, status, page, ordering], queryFn: () => api<Page>(`platform/${section}/?search=${encodeURIComponent(search)}&status=${status}&page=${page}&ordering=${ordering}`), retry: false });
  const mutation = useMutation({
    mutationFn: ({ resource, row, action }: NonNullable<typeof pending>) => api(`platform/${resource}/${row.id}/${action}/`, { reason: reason.trim() }),
    onSuccess: async () => { setPending(null); setReason(''); await Promise.all([cache.invalidateQueries({ queryKey: ['platform'] }), cache.invalidateQueries({ queryKey: ['companies'] }), cache.invalidateQueries({ queryKey: ['company'] })]); },
  });
  function switchSection(next: Section) {
    setSection(next); setSearch(''); setStatus(''); setPage(1); setPending(null); mutation.reset();
    setOrdering(next === 'users' ? 'email' : next === 'audit' ? '-created_at' : 'name');
  }
  function propose(row: Row, resource: 'companies' | 'users') {
    const active = resource === 'companies' ? row.status === 'active' : row.is_active;
    setPending({ row, resource, action: active ? resource === 'companies' ? 'suspend' : 'deactivate' : 'activate' });
    setReason(''); mutation.reset();
  }
  const statusOptions = section === 'companies' ? [['active', 'Actives'], ['suspended', 'Suspendues']] : [['active', 'Actifs'], ['inactive', 'Inactifs']];
  const basicOrder = section === 'users' ? 'email' : section === 'modules' ? 'name' : section === 'audit' ? 'created_at' : 'name';
  return <div className="platform-shell">
    <header className="public-header"><Brand to="/plateforme"/><nav><Link to="/administration">Mon espace entreprise</Link><ThemeToggle/></nav></header>
    <main className="platform-main">
      <header className="page-heading"><div><p className="eyebrow">QAVELYS · PLATEFORME</p><h1>Administration plateforme</h1><p>Gestion des espaces et des comptes. Connecté : {me.email}.</p></div><Button variant="outline" onClick={() => void cache.invalidateQueries({ queryKey: ['platform'] })}>Actualiser la plateforme</Button></header>
      {overview.error ? <Failure error={overview.error} retry={() => void overview.refetch()}/> : overview.isPending ? <Loading/> : <section className="dashboard-metrics" aria-label="Indicateurs plateforme">
        {[["Entreprises", overview.data.companies], ["Entreprises actives", overview.data.active_companies], ["Utilisateurs", overview.data.users], ["Utilisateurs actifs", overview.data.active_users], ["Modules disponibles", overview.data.available_modules]].map(([label, value]) => <article className="card" key={label}><h2>{label}</h2><strong>{value}</strong></article>)}
      </section>}
      <nav className="platform-tabs" aria-label="Sections plateforme">{(Object.keys(sections) as Section[]).map(key => <Button key={key} variant={section === key ? 'default' : 'outline'} aria-pressed={section === key} onClick={() => switchSection(key)}>{sections[key]}</Button>)}</nav>
      <section className="card management-card">
        <h2>{sections[section]}</h2>
        <div className="table-toolbar">
          <label>Rechercher dans la plateforme<input value={search} onChange={event => { setSearch(event.target.value); setPage(1); }}/></label>
          {(section === 'companies' || section === 'users') && <label>Statut plateforme<select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">Tous</option>{statusOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
          <label>Trier la plateforme<select value={ordering} onChange={event => { setOrdering(event.target.value); setPage(1); }}><option value={basicOrder}>{section === 'audit' ? 'Plus anciens' : 'Ordre croissant'}</option><option value={`-${basicOrder}`}>{section === 'audit' ? 'Plus récents' : 'Ordre décroissant'}</option>{section !== 'audit' && section !== 'modules' && <option value="-created_at">Plus récents</option>}</select></label>
        </div>
        {rows.isPending ? <Loading/> : rows.error ? <Failure error={rows.error} retry={() => void rows.refetch()}/> : <>
          {rows.data.results.length === 0 ? <p>Aucun résultat.</p> : <div className="table-scroll"><table aria-label={sections[section]}><thead><tr>
            {section === 'companies' && <><th>Entreprise</th><th>Créateur</th><th>Pays / devise</th><th>Membres</th><th>Statut</th><th>Action</th></>}
            {section === 'users' && <><th>Compte</th><th>Rôle plateforme</th><th>Vérification e-mail</th><th>Statut</th><th>Action</th></>}
            {section === 'modules' && <><th>Module</th><th>Description</th><th>Disponibilité</th><th>Entreprises actives utilisant le module</th></>}
            {section === 'audit' && <><th>Date</th><th>Acteur</th><th>Action</th><th>Cible</th><th>Motif</th></>}
          </tr></thead><tbody>{rows.data.results.map(row => <tr key={row.id}>
            {section === 'companies' && <><td>{row.name}</td><td>{row.owner_email}</td><td>{row.country_code} / {row.currency_code}</td><td>{row.member_count}</td><td>{row.status === 'active' ? 'Active' : 'Suspendue'}</td><td><Button variant="outline" onClick={() => propose(row, 'companies')}>{row.status === 'active' ? 'Suspendre' : 'Réactiver'} {row.name}</Button></td></>}
            {section === 'users' && <><td>{row.full_name}<br/>{row.email}</td><td>{row.is_platform_admin ? 'Super-administrateur' : 'Utilisateur'}</td><td>{row.email_verified ? 'Vérifiée' : 'Non vérifiée'}</td><td>{row.is_active ? 'Actif' : 'Inactif'}</td><td><Button variant="outline" disabled={row.id === me.id} onClick={() => propose(row, 'users')}>{row.is_active ? 'Désactiver' : 'Réactiver'} {row.email}</Button></td></>}
            {section === 'modules' && <><td>{row.name}</td><td>{row.description}</td><td>{row.status === 'available' ? 'Disponible' : 'À venir'}</td><td>{row.enabled_companies}</td></>}
            {section === 'audit' && <><td>{row.created_at && new Date(row.created_at).toLocaleString('fr-FR')}</td><td>{row.actor}</td><td>{actions[row.action || ''] || row.action}</td><td>{row.target}</td><td>{row.reason}</td></>}
          </tr>)}</tbody></table></div>}
          <div className="table-pagination"><span>Page {page} · {rows.data.count} résultat(s)</span><div><Button variant="outline" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>Page précédente</Button><Button variant="outline" disabled={page * rows.data.page_size >= rows.data.count} onClick={() => setPage(value => value + 1)}>Page suivante</Button></div></div>
        </>}
      </section>
      {pending && <section className="card management-card" role="region" aria-label="Confirmer le changement d’accès">
        <h2>Confirmer le changement d’accès</h2><p>{pending.row.name || pending.row.email} : {pending.action === 'activate' ? 'réactivation' : 'suspension d’accès'}. Les données sont conservées.</p>
        <form onSubmit={event => { event.preventDefault(); if (reason.trim().length >= 8) mutation.mutate(pending); }}>
          <label htmlFor="platform-reason">Motif du changement</label><textarea id="platform-reason" minLength={8} maxLength={1000} required value={reason} onChange={event => setReason(event.target.value)}/>
          <small>8 caractères minimum. Le motif figurera dans le journal plateforme.</small><ErrorMessage error={mutation.error}/>
          <div className="dialog-actions"><Button type="button" variant="outline" disabled={mutation.isPending} onClick={() => setPending(null)}>Annuler le changement</Button><Button disabled={reason.trim().length < 8 || mutation.isPending}>Confirmer le changement</Button></div>
        </form>
      </section>}
    </main>
  </div>;
}
