import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api, companyKey } from '../api';
import { Button } from '../components/ui/button';
import { ErrorMessage, Failure, Loading } from '../components/feedback';
import { useWorkspace } from '../workspace';
import { LogoEditor } from '../components/company-logo';
import { PermissionCatalog, type CatalogPermission } from '../components/permission-catalog';
import { RoleTemplates } from '../components/role-templates';

export type ManagedRole = { id: string; name: string; is_system: boolean; permission_codes?: string[] };
type Permission = CatalogPermission;
const roleSchema = z.object({ name: z.string().trim().min(1, 'Nom requis.'), permission_codes: z.array(z.string()) });
export function RoleManagement({ roles }: { roles: ManagedRole[] }) {
  const { companyId } = useWorkspace();
  const cache = useQueryClient();
  const [editing, setEditing] = useState<ManagedRole | null>(null);
  const form = useForm<z.infer<typeof roleSchema>>({ resolver: zodResolver(roleSchema), defaultValues: { name: '', permission_codes: [] } });
  const permissions = useQuery({ queryKey: companyKey(companyId, 'permissions'), queryFn: () => api<Permission[]>(`companies/${companyId}/permissions/`), retry: false });
  const action = useMutation({ mutationFn: (data: z.infer<typeof roleSchema>) => api(`companies/${companyId}/roles/${editing ? `${editing.id}/update` : 'create'}/`, data), onSuccess: async () => { setEditing(null); form.reset({ name: '', permission_codes: [] }); await Promise.all([cache.invalidateQueries({ queryKey: companyKey(companyId, 'roles') }), cache.invalidateQueries({ queryKey: companyKey(companyId, 'context') })]); } });
  return <><RoleTemplates/><section className="card management-card"><h2>Gérer les rôles</h2><div className="role-edit-list">{roles.map(role => <div key={role.id}><strong>{role.name}</strong><span>{role.is_system ? 'Rôle système protégé' : <Button variant="outline" onClick={() => { setEditing(role); form.reset({ name: role.name, permission_codes: role.permission_codes ?? [] }); action.reset(); }}>Modifier</Button>}</span></div>)}</div>{permissions.isPending ? <Loading text="Chargement des permissions…"/> : permissions.error ? <Failure error={permissions.error} retry={() => void permissions.refetch()}/> : <form onSubmit={form.handleSubmit(data => action.mutate(data))}><h3>{editing ? `Modifier ${editing.name}` : 'Créer un rôle'}</h3><label>Nom du rôle<input {...form.register('name')}/><small>{form.formState.errors.name?.message}</small></label><PermissionCatalog permissions={permissions.data} selected={form.watch('permission_codes')} onChange={codes => form.setValue('permission_codes', codes, { shouldDirty: true })}/><ErrorMessage error={action.error}/><div className="dialog-actions">{editing && <Button variant="outline" type="button" onClick={() => { setEditing(null); form.reset({ name: '', permission_codes: [] }); }}>Annuler</Button>}<Button disabled={action.isPending}>{action.isPending ? 'Enregistrement…' : 'Enregistrer le rôle'}</Button></div></form>}</section></>;
}

type Invitation = { id: string; email: string; expires_at: string; accepted_at: string | null; revoked_at: string | null; role_ids: string[] };
const invitationSchema = z.object({ email: z.email('Adresse e-mail invalide.'), role_ids: z.array(z.string()).min(1, 'Choisissez au moins un rôle.') });
export function InvitationsPage() {
  const { companyId } = useWorkspace();
  const cache = useQueryClient();
  const form = useForm<z.infer<typeof invitationSchema>>({ resolver: zodResolver(invitationSchema), defaultValues: { email: '', role_ids: [] } });
  const invitations = useQuery({ queryKey: companyKey(companyId, 'invitations'), queryFn: () => api<Invitation[]>(`companies/${companyId}/invitations/`), retry: false });
  const roles = useQuery({ queryKey: companyKey(companyId, 'roles'), queryFn: () => api<ManagedRole[]>(`companies/${companyId}/roles/`), retry: false });
  const create = useMutation({ mutationFn: (data: z.infer<typeof invitationSchema>) => api(`companies/${companyId}/invitations/`, data), onSuccess: async () => { form.reset({ email: '', role_ids: [] }); await cache.invalidateQueries({ queryKey: companyKey(companyId, 'invitations') }); } });
  const change = useMutation({ mutationFn: ({ id, action }: { id: string; action: string }) => api(`companies/${companyId}/invitations/${id}/${action}/`, {}), onSuccess: () => cache.invalidateQueries({ queryKey: companyKey(companyId, 'invitations') }) });
  return <><header className="page-heading"><div><p className="eyebrow">INVITER VOTRE ÉQUIPE</p><h1>Invitations</h1><p>Chaque invitation est adressée à une personne et contient un lien valable sept jours.</p></div></header><section className="card"><h2>Inviter un collaborateur</h2>{roles.isPending ? <Loading/> : roles.error ? <Failure error={roles.error} retry={() => void roles.refetch()}/> : <form noValidate onSubmit={form.handleSubmit(data => create.mutate(data))}><label>E-mail du collaborateur<input type="email" {...form.register('email')}/><small>{form.formState.errors.email?.message}</small></label><fieldset className="permission-grid"><legend>Rôles à attribuer</legend>{roles.data.map(role => <label className="checkbox-label" key={role.id}><input type="checkbox" value={role.id} {...form.register('role_ids')}/><span>{role.name}</span></label>)}</fieldset><small>{form.formState.errors.role_ids?.message}</small><ErrorMessage error={create.error}/>{create.isSuccess && <p role="status">Invitation enregistrée et e-mail préparé avec le transport configuré.</p>}<Button disabled={create.isPending}>Envoyer l’invitation</Button></form>}</section><section className="card management-card"><h2>Invitations envoyées</h2><ErrorMessage error={change.error}/>{invitations.isPending ? <Loading/> : invitations.error ? <Failure error={invitations.error} retry={() => void invitations.refetch()}/> : invitations.data.length ? <div className="table-scroll"><table><thead><tr><th>E-mail</th><th>État</th><th>Expiration</th><th>Actions</th></tr></thead><tbody>{invitations.data.map(invitation => { const pending = !invitation.accepted_at && !invitation.revoked_at; return <tr key={invitation.id}><td>{invitation.email}</td><td>{invitation.accepted_at ? 'Acceptée' : invitation.revoked_at ? 'Révoquée' : new Date(invitation.expires_at) <= new Date() ? 'Expirée' : 'En attente'}</td><td>{new Date(invitation.expires_at).toLocaleDateString('fr-FR')}</td><td>{pending && <div className="row-actions"><Button variant="outline" disabled={change.isPending} onClick={() => change.mutate({ id: invitation.id, action: 'resend' })}>Renvoyer</Button><Button variant="outline" disabled={change.isPending} onClick={() => change.mutate({ id: invitation.id, action: 'revoke' })}>Révoquer</Button></div>}</td></tr>; })}</tbody></table></div> : <p>Aucune invitation envoyée.</p>}</section></>;
}

const settingsSchema = z.object({ name: z.string().trim().min(1, 'Nom requis.'), sector: z.string(), address: z.string(), phone: z.string(), timezone: z.string().min(1, 'Fuseau requis.'), locale: z.string().min(2, 'Langue requise.') });
type SettingsData = z.infer<typeof settingsSchema> & { logo_url?: string | null };
export function SettingsPage() {
  const { companyId } = useWorkspace();
  const cache = useQueryClient();
  const settings = useQuery({ queryKey: companyKey(companyId, 'settings'), queryFn: () => api<SettingsData>(`companies/${companyId}/settings/`), retry: false });
  const form = useForm<SettingsData>({ resolver: zodResolver(settingsSchema) });
  useEffect(() => { if (settings.data) form.reset(settings.data); }, [settings.data, form]);
  const action = useMutation({ mutationFn: (data: SettingsData) => api<SettingsData>(`companies/${companyId}/settings/`, data), onSuccess: async data => { cache.setQueryData(companyKey(companyId, 'settings'), data); await Promise.all([cache.invalidateQueries({ queryKey: ['companies'] }), cache.invalidateQueries({ queryKey: companyKey(companyId, 'context') })]); } });
  return <><header className="page-heading"><div><p className="eyebrow">PARAMÈTRES</p><h1>Configurer l’entreprise</h1></div></header><section className="card">{settings.isPending ? <Loading/> : settings.error ? <Failure error={settings.error} retry={() => void settings.refetch()}/> : <form noValidate onSubmit={form.handleSubmit(data => action.mutate(data))}>{(['name', 'sector', 'address', 'phone', 'timezone', 'locale'] as const).map((field, index) => <label key={field}>{['Nom', 'Secteur', 'Adresse', 'Téléphone', 'Fuseau horaire (ex. Africa/Conakry)', 'Langue (ex. fr)'][index]}<input {...form.register(field)}/><small>{form.formState.errors[field]?.message}</small></label>)}<ErrorMessage error={action.error}/>{action.isSuccess && <p role="status">Paramètres enregistrés.</p>}<Button disabled={action.isPending}>Enregistrer les paramètres</Button></form>}</section>{settings.data && <LogoEditor key={companyId} logoUrl={settings.data.logo_url}/>}</>;
}

type Module = { code: string; name: string; description: string; status: string; enabled: boolean; dependencies: string[] };
export function ModulesPage() {
  const { companyId, context } = useWorkspace();
  const cache = useQueryClient();
  const modules = useQuery({ queryKey: companyKey(companyId, 'modules'), queryFn: () => api<Module[]>(`companies/${companyId}/modules/`), retry: false });
  const action = useMutation({ mutationFn: (module: Module) => api(`companies/${companyId}/modules/${module.code}/${module.enabled ? 'disable' : 'enable'}/`, {}), onSuccess: () => Promise.all([cache.invalidateQueries({ queryKey: companyKey(companyId, 'modules') }), cache.invalidateQueries({ queryKey: companyKey(companyId, 'context') })]) });
  return <><header className="page-heading"><div><p className="eyebrow">APPLICATIONS</p><h1>Modules de l’entreprise</h1><p>L’activation inclut les dépendances disponibles. La désactivation conserve les données.</p></div></header><ErrorMessage error={action.error}/>{modules.isPending ? <Loading/> : modules.error ? <Failure error={modules.error} retry={() => void modules.refetch()}/> : <div className="module-grid">{modules.data.map(module => <section className="card" key={module.code}><h2>{module.name}</h2><span className="status-badge">{module.enabled ? 'Activé' : module.status === 'available' ? 'Disponible' : 'À venir'}</span><p>{module.description}</p>{module.dependencies.length > 0 && <p className="muted-text">Dépendances : {module.dependencies.join(', ')}</p>}{module.code !== 'core' && module.status === 'available' && context!.permissions.includes('modules.manage') && <Button disabled={action.isPending} onClick={() => action.mutate(module)}>{module.enabled ? 'Désactiver' : 'Activer avec ses dépendances'}</Button>}</section>)}</div>}</>;
}

export { AuditPage, SequencesPage } from './admin-records';

export function ProfileEditor() {
  const { user } = useWorkspace();
  const cache = useQueryClient();
  const [name, setName] = useState(user.full_name);
  const action = useMutation({ mutationFn: () => api('auth/me/', { full_name: name }), onSuccess: () => cache.invalidateQueries({ queryKey: ['me'] }) });
  return <section className="card management-card"><h2>Modifier mon nom</h2><form onSubmit={event => { event.preventDefault(); action.mutate(); }}><label>Nom complet<input required maxLength={150} value={name} onChange={event => setName(event.target.value)}/></label><ErrorMessage error={action.error}/>{action.isSuccess && <p role="status">Nom enregistré.</p>}<Button disabled={action.isPending}>Enregistrer mon nom</Button></form><Link to="/forgot-password">Changer mon mot de passe par e-mail</Link></section>;
}

type AccessMember = { id: string; full_name: string; status: string; roles?: ManagedRole[] };
export function MemberAccessEditor({ members }: { members: AccessMember[] }) {
  const { companyId } = useWorkspace();
  const cache = useQueryClient();
  const [selectedId, setSelectedId] = useState('');
  const [chosen, setChosen] = useState<string[]>([]);
  const roles = useQuery({ queryKey: companyKey(companyId, 'roles'), queryFn: () => api<ManagedRole[]>(`companies/${companyId}/roles/`), retry: false });
  const selected = members.find(member => member.id === selectedId);
  const action = useMutation({ mutationFn: ({ activate = false }: { activate?: boolean }) => api(`companies/${companyId}/members/${selectedId}/${activate ? 'activate' : 'roles'}/`, activate ? {} : { role_ids: chosen }), onSuccess: async () => { await Promise.all([cache.invalidateQueries({ queryKey: companyKey(companyId, 'members') }), cache.invalidateQueries({ queryKey: companyKey(companyId, 'context') }), cache.invalidateQueries({ queryKey: ['companies'] })]); } });
  return <section className="card management-card"><h2>Gérer l’accès d’un collaborateur</h2><label>Collaborateur<select value={selectedId} onChange={event => { const member = members.find(item => item.id === event.target.value); setSelectedId(event.target.value); setChosen(member?.roles?.map(role => role.id) ?? []); action.reset(); }}><option value="">Choisir une personne</option>{members.map(member => <option key={member.id} value={member.id}>{member.full_name}</option>)}</select></label>{roles.isPending ? <Loading/> : roles.error ? <Failure error={roles.error} retry={() => void roles.refetch()}/> : selected && <form onSubmit={event => { event.preventDefault(); if (window.confirm(`Confirmer les nouveaux rôles de ${selected.full_name} ?`)) action.mutate({}); }}><fieldset className="permission-grid"><legend>Rôles de {selected.full_name}</legend>{roles.data.map(role => <label className="checkbox-label" key={role.id}><input type="checkbox" checked={chosen.includes(role.id)} onChange={event => setChosen(values => event.target.checked ? [...values, role.id] : values.filter(id => id !== role.id))}/><span>{role.name}</span></label>)}</fieldset><ErrorMessage error={action.error}/>{action.isSuccess && <p role="status">Accès enregistré.</p>}<div className="dialog-actions">{selected.status === 'suspended' && <Button type="button" variant="outline" disabled={action.isPending} onClick={() => { if (window.confirm(`Réactiver l’accès de ${selected.full_name} ?`)) action.mutate({ activate: true }); }}>Réactiver ce membre</Button>}<Button disabled={action.isPending || !chosen.length}>Enregistrer les rôles</Button></div></form>}</section>;
}
