import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, companyKey } from '../api';
import { useWorkspace } from '../workspace';
import { Button } from './ui/button';
import { ErrorMessage, Failure, Loading } from './feedback';

type Template = { code: string; name: string; permission_codes: string[]; installed: boolean };
export function RoleTemplates() {
  const { companyId } = useWorkspace();
  const cache = useQueryClient();
  const templates = useQuery({ queryKey: companyKey(companyId, 'role-templates'), queryFn: () => api<Template[]>(`companies/${companyId}/role-templates/`), retry: false });
  const action = useMutation({ mutationFn: (code: string) => api(`companies/${companyId}/role-templates/`, { code }), onSuccess: () => Promise.all([cache.invalidateQueries({ queryKey: companyKey(companyId, 'roles') }), cache.invalidateQueries({ queryKey: companyKey(companyId, 'role-templates') })]) });
  return <section className="card management-card"><h2>Rôles prédéfinis</h2><p>Ajoutez un rôle adapté aux modules disponibles. Aucun accès n’est attribué automatiquement ; vous pourrez ensuite ajuster ses autorisations.</p><ErrorMessage error={action.error}/>{action.isSuccess && <p role="status">Rôle disponible dans l’entreprise.</p>}{templates.isPending ? <Loading/> : templates.error ? <Failure error={templates.error} retry={() => void templates.refetch()}/> : <div className="role-edit-list">{templates.data.map(item => <div key={item.code}><span><strong>{item.name}</strong><small>{item.permission_codes.length} autorisation(s)</small></span>{item.installed ? <span className="status-badge">Déjà disponible</span> : <Button variant="outline" disabled={action.isPending} onClick={() => { if (window.confirm(`Ajouter le rôle « ${item.name} » sans l’attribuer à un utilisateur ?`)) action.mutate(item.code); }}>Ajouter · {item.name}</Button>}</div>)}</div>}</section>;
}
