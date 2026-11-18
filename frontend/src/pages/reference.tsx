import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, Plus, Search } from 'lucide-react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api, companyKey } from '../api';
import { Button } from '../components/ui/button';
import { ErrorMessage, Failure, Loading } from '../components/feedback';
import { companyPath, useWorkspace } from '../workspace';

export type Resource = 'partners' | 'products' | 'categories' | 'taxes';
export const referenceConfig = {
  partners: { title: 'Clients et fournisseurs', singular: 'Contact', path: 'contacts', permission: 'contacts', module: 'contacts' },
  products: { title: 'Produits et services', singular: 'Produit', path: 'produits', permission: 'products', module: 'catalog' },
  categories: { title: 'Catégories', singular: 'Catégorie', path: 'categories', permission: 'categories', module: 'catalog' },
  taxes: { title: 'Taxes', singular: 'Taxe', path: 'taxes', permission: 'taxes', module: 'catalog' },
} as const;
type RefTax = { id: string; name: string; rate: string; active: boolean };
export type ReferenceRecord = { id: string; name: string; email?: string; phone?: string; address?: string; is_customer?: boolean; is_supplier?: boolean; status?: string; active?: boolean; sku?: string; description?: string; type?: string; category_id?: string | null; category_name?: string | null; parent_id?: string | null; unit_id?: string; unit_name?: string; sale_price?: string; cost_price?: string; rate?: string; taxes?: RefTax[] };
type Page = { count: number; page: number; page_size: number; results: ReferenceRecord[] };
type Unit = { id: string; name: string; symbol: string; category: string };
const prefix = (companyId: string) => `companies/${companyId}/reference/`;

export function ReferenceListPage({ resource }: { resource: Resource }) {
  const { companyId, context } = useWorkspace();
  const config = referenceConfig[resource];
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [state, setState] = useState('active');
  const [kind, setKind] = useState('all');
  const [ordering, setOrdering] = useState('name');
  const records = useQuery({ queryKey: [...companyKey(companyId, resource), page, search, state, kind, ordering], queryFn: () => api<Page>(`${prefix(companyId)}${resource}/?page=${page}&search=${encodeURIComponent(search)}&state=${state}&kind=${kind}&ordering=${ordering}`), retry: false });
  const base = `${companyPath(companyId)}/${config.path}`;
  return <><header className="page-heading"><div><p className="eyebrow">RÉFÉRENTIEL</p><h1>{config.title}</h1><p>Les données de {context!.company.name}.</p></div>{context!.permissions.includes(config.permission + '.manage') && <Button asChild><Link to={`${base}/nouveau`}><Plus size={16}/>Créer : {config.singular.toLowerCase()}</Link></Button>}</header><section className="card table-card"><div className="table-toolbar"><label className="search-field"><Search size={17}/><span className="sr-only">Rechercher dans {config.title}</span><input aria-label={`Rechercher dans ${config.title}`} placeholder="Rechercher…" value={search} onChange={event => { setSearch(event.target.value); setPage(1); }}/></label><div className="table-filters">{resource === 'partners' && <select aria-label="Type de contact" value={kind} onChange={event => { setKind(event.target.value); setPage(1); }}><option value="all">Clients et fournisseurs</option><option value="customer">Clients</option><option value="supplier">Fournisseurs</option></select>}{resource !== 'categories' && <select aria-label="État des données" value={state} onChange={event => { setState(event.target.value); setPage(1); }}><option value="active">Actifs</option><option value="archived">Archivés</option><option value="all">Tous</option></select>}<select aria-label="Trier les données" value={ordering} onChange={event => { setOrdering(event.target.value); setPage(1); }}><option value="name">Nom A → Z</option><option value="-name">Nom Z → A</option><option value="-created_at">Plus récents</option></select></div></div>{records.isPending ? <Loading/> : records.error ? <Failure error={records.error} retry={() => void records.refetch()}/> : <><div className="table-scroll"><table><thead><tr><th>Nom</th>{resource === 'partners' ? <><th>E-mail</th><th>Type</th></> : resource === 'products' ? <><th>SKU</th><th>Type</th><th>Prix de vente ({context!.company.currency_code})</th></> : resource === 'taxes' ? <th>Taux</th> : <th>Organisation</th>}<th>Fiche</th></tr></thead><tbody>{records.data.results.map(record => <tr key={record.id}><td><Link to={`${base}/${record.id}`}>{record.name}</Link></td>{resource === 'partners' ? <><td>{record.email || '—'}</td><td>{[record.is_customer && 'Client', record.is_supplier && 'Fournisseur'].filter(Boolean).join(' · ')}</td></> : resource === 'products' ? <><td>{record.sku}</td><td>{record.type === 'service' ? 'Service' : record.type === 'consumable' ? 'Consommable' : 'Stockable'}</td><td>{record.sale_price}</td></> : resource === 'taxes' ? <td>{record.rate} %</td> : <td>{record.parent_id ? 'Sous-catégorie' : 'Catégorie principale'}</td>}<td><Link to={`${base}/${record.id}`} className="text-link">Ouvrir <ArrowRight size={14}/></Link></td></tr>)}</tbody></table></div>{!records.data.count && <p className="empty-list">Aucune donnée ne correspond à votre recherche.</p>}<div className="table-pagination"><span>{records.data.count} résultats · Page {page}</span><div><Button variant="outline" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>Précédente</Button><Button variant="outline" disabled={page * records.data.page_size >= records.data.count} onClick={() => setPage(value => value + 1)}>Suivante</Button></div></div></>}</section></>;
}

type EditorValues = { name: string; email: string; phone: string; address: string; is_customer: boolean; is_supplier: boolean; sku: string; description: string; type: string; category_id: string; parent_id: string; unit_id: string; sale_price: string; cost_price: string; rate: string; tax_ids: string[] };
const empty: EditorValues = { name: '', email: '', phone: '', address: '', is_customer: true, is_supplier: false, sku: '', description: '', type: 'stockable', category_id: '', parent_id: '', unit_id: '', sale_price: '0', cost_price: '0', rate: '0', tax_ids: [] };
function schemaFor(resource: Resource) {
  return z.object({ name: z.string().trim().min(1, 'Nom requis.').max(200), email: z.string(), phone: z.string(), address: z.string(), is_customer: z.boolean(), is_supplier: z.boolean(), sku: z.string(), description: z.string(), type: z.string(), category_id: z.string(), parent_id: z.string(), unit_id: z.string(), sale_price: z.string(), cost_price: z.string(), rate: z.string(), tax_ids: z.array(z.string()) }).superRefine((data, ctx) => {
    const error = (field: keyof EditorValues, message: string) => ctx.addIssue({ code: 'custom', path: [field], message });
    if (resource === 'partners') {
      if (!data.is_customer && !data.is_supplier) error('is_customer', 'Choisissez client, fournisseur ou les deux.');
      if (data.email && !z.email().safeParse(data.email).success) error('email', 'Adresse e-mail invalide.');
    }
    if (resource === 'products') {
      if (!data.sku.trim()) error('sku', 'SKU requis.');
      if (!data.unit_id) error('unit_id', 'Unité requise.');
      for (const field of ['sale_price', 'cost_price'] as const) if (!/^\d{1,14}(?:\.\d{1,6})?$/.test(data[field])) error(field, 'Montant positif, au plus 6 décimales.');
    }
    if (resource === 'taxes' && !/^(?:100(?:\.0{1,4})?|(?:\d|[1-9]\d)(?:\.\d{1,4})?)$/.test(data.rate)) error('rate', 'Taux de 0 à 100 %, au plus 4 décimales.');
  });
}

function CategoryLookup({ selected, change, exclude }: { selected: string; change: (id: string) => void; exclude?: string }) {
  const { companyId } = useWorkspace();
  const [search, setSearch] = useState('');
  const options = useQuery({ queryKey: [...companyKey(companyId, 'categories'), 'lookup', search], queryFn: () => api<Page>(`${prefix(companyId)}categories/?page_size=100&search=${encodeURIComponent(search)}`), retry: false });
  const current = useQuery({ queryKey: [...companyKey(companyId, 'categories'), selected], queryFn: () => api<ReferenceRecord>(`${prefix(companyId)}categories/${selected}/`), enabled: Boolean(selected), retry: false });
  const choices = [...(options.data?.results ?? [])];
  if (current.data && !choices.some(item => item.id === current.data!.id)) choices.push(current.data);
  return <div className="lookup-field"><label htmlFor="category-search">Rechercher une catégorie</label><input id="category-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Saisissez un nom pour retrouver toute catégorie"/><label htmlFor="category-choice">Catégorie</label><select id="category-choice" value={selected} onChange={event => change(event.target.value)}><option value="">Aucune catégorie</option>{choices.filter(item => item.id !== exclude).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{options.isPending && <p role="status">Chargement des catégories…</p>}<ErrorMessage error={options.error}/><ErrorMessage error={current.error}/></div>;
}

function TaxLookup({ selected, change, initial }: { selected: string[]; change: (ids: string[]) => void; initial: RefTax[] }) {
  const { companyId } = useWorkspace();
  const [search, setSearch] = useState('');
  const options = useQuery({ queryKey: [...companyKey(companyId, 'taxes'), 'lookup', search], queryFn: () => api<Page>(`${prefix(companyId)}taxes/?page_size=100&search=${encodeURIComponent(search)}`), retry: false });
  const known = new Map([...initial, ...(options.data?.results ?? [])].map(item => [item.id, item]));
  return <fieldset className="tax-lookup"><legend>Taxes applicables</legend><label htmlFor="tax-search">Rechercher une taxe</label><input id="tax-search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Nom de la taxe"/><div className="selected-taxes">{selected.map(id => <Button type="button" variant="outline" key={id} onClick={() => change(selected.filter(value => value !== id))}>{known.get(id)?.name ?? 'Taxe sélectionnée'} ×</Button>)}</div>{options.isPending ? <Loading/> : options.error ? <ErrorMessage error={options.error}/> : <div className="permission-grid">{options.data.results.map(item => <label className="checkbox-label" key={item.id}><input type="checkbox" checked={selected.includes(item.id)} onChange={event => change(event.target.checked ? [...selected, item.id] : selected.filter(id => id !== item.id))}/><span>{item.name} · {item.rate} %</span></label>)}</div>}</fieldset>;
}

export function ReferenceEditorPage({ resource }: { resource: Resource }) {
  const { companyId } = useWorkspace();
  const { recordId } = useParams();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const config = referenceConfig[resource];
  const schema = useMemo(() => schemaFor(resource), [resource]);
  const form = useForm<EditorValues>({ resolver: zodResolver(schema), defaultValues: empty });
  const record = useQuery({ queryKey: [...companyKey(companyId, resource), recordId], queryFn: () => api<ReferenceRecord>(`${prefix(companyId)}${resource}/${recordId}/`), enabled: Boolean(recordId), retry: false });
  const units = useQuery({ queryKey: companyKey(companyId, 'units'), queryFn: () => api<Unit[]>(`${prefix(companyId)}units/`), enabled: resource === 'products', retry: false });
  useEffect(() => { if (record.data) form.reset({ ...empty, ...record.data, type: record.data.type ?? 'stockable', category_id: record.data.category_id ?? '', parent_id: record.data.parent_id ?? '', tax_ids: record.data.taxes?.map(tax => tax.id) ?? [] }); }, [record.data, form]);
  const action = useMutation({ mutationFn: (data: EditorValues) => {
    const payload = resource === 'partners' ? { name: data.name, email: data.email, phone: data.phone, address: data.address, is_customer: data.is_customer, is_supplier: data.is_supplier } : resource === 'categories' ? { name: data.name, parent_id: data.parent_id || null } : resource === 'taxes' ? { name: data.name, rate: data.rate } : { sku: data.sku, name: data.name, description: data.description, type: data.type, unit_id: data.unit_id, category_id: data.category_id || null, sale_price: data.sale_price, cost_price: data.cost_price, tax_ids: data.tax_ids };
    return api<ReferenceRecord>(`${prefix(companyId)}${resource}/${recordId ? `${recordId}/update/` : ''}`, payload);
  }, onSuccess: async saved => { await cache.invalidateQueries({ queryKey: companyKey(companyId, resource) }); navigate(`${companyPath(companyId)}/${config.path}/${saved.id}`, { replace: true }); } });
  if (recordId && record.isPending) return <Loading/>;
  if (record.error) return <Failure error={record.error} retry={() => void record.refetch()}/>;
  const fields: { name: keyof EditorValues; label: string; multiline?: boolean }[] = [{ name: 'name', label: 'Nom' }];
  if (resource === 'partners') fields.push({ name: 'email', label: 'E-mail' }, { name: 'phone', label: 'Téléphone' }, { name: 'address', label: 'Adresse', multiline: true });
  if (resource === 'products') fields.push({ name: 'sku', label: 'SKU' }, { name: 'description', label: 'Description', multiline: true }, { name: 'sale_price', label: 'Prix de vente' }, { name: 'cost_price', label: 'Coût unitaire' });
  if (resource === 'taxes') fields.push({ name: 'rate', label: 'Taux (%)' });
  return <><header className="page-heading"><div><p className="eyebrow">RÉFÉRENTIEL</p><h1>{recordId ? 'Modifier' : 'Créer'} : {config.singular.toLowerCase()}</h1></div><Link className="text-link" to={`${companyPath(companyId)}/${config.path}`}><ArrowLeft size={16}/>Retour à la liste</Link></header><section className="card editor-card"><form noValidate onSubmit={form.handleSubmit(data => action.mutate(data))}>{fields.map(field => <div className="form-field" key={field.name}><label htmlFor={`field-${field.name}`}>{field.label}</label>{field.multiline ? <textarea id={`field-${field.name}`} {...form.register(field.name)} rows={3}/> : <input id={`field-${field.name}`} {...form.register(field.name)}/>}<small>{form.formState.errors[field.name]?.message}</small></div>)}{resource === 'partners' && <fieldset><legend>Type de contact</legend><div className="row-actions"><label className="checkbox-label"><input type="checkbox" {...form.register('is_customer')}/>Client</label><label className="checkbox-label"><input type="checkbox" {...form.register('is_supplier')}/>Fournisseur</label></div><small>{form.formState.errors.is_customer?.message}</small></fieldset>}{resource === 'products' && <><div className="form-field"><label htmlFor="product-type">Type de produit</label><select id="product-type" {...form.register('type')}><option value="stockable">Stockable</option><option value="consumable">Consommable</option><option value="service">Service</option></select></div><div className="form-field"><label htmlFor="product-unit">Unité de référence</label><select id="product-unit" {...form.register('unit_id')}><option value="">Choisir une unité</option>{units.data?.map(unit => <option key={unit.id} value={unit.id}>{unit.name} ({unit.symbol})</option>)}</select><small>{form.formState.errors.unit_id?.message}</small><ErrorMessage error={units.error}/></div><CategoryLookup selected={form.watch('category_id')} change={id => form.setValue('category_id', id)}/><TaxLookup selected={form.watch('tax_ids')} change={ids => form.setValue('tax_ids', ids)} initial={record.data?.taxes ?? []}/></>}{resource === 'categories' && <CategoryLookup selected={form.watch('parent_id')} change={id => form.setValue('parent_id', id)} exclude={recordId}/>}<ErrorMessage error={action.error}/><Button disabled={action.isPending}>{action.isPending ? 'Enregistrement…' : 'Enregistrer'}</Button></form></section></>;
}

export function ReferenceDetailPage({ resource }: { resource: Resource }) {
  const { companyId, context } = useWorkspace();
  const { recordId } = useParams();
  const cache = useQueryClient();
  const config = referenceConfig[resource];
  const record = useQuery({ queryKey: [...companyKey(companyId, resource), recordId], queryFn: () => api<ReferenceRecord>(`${prefix(companyId)}${resource}/${recordId}/`), retry: false });
  const history = useQuery({ queryKey: [...companyKey(companyId, 'price-history'), recordId], queryFn: () => api<{ id: string; actor: string; created_at: string; old_sale_price: string; new_sale_price: string; old_cost_price: string; new_cost_price: string }[]>(`${prefix(companyId)}products/${recordId}/price-history/`), enabled: resource === 'products', retry: false });
  const inactive = record.data?.status === 'archived' || record.data?.active === false;
  const action = useMutation({ mutationFn: () => api(`${prefix(companyId)}${resource}/${recordId}/${inactive ? 'restore' : 'archive'}/`, {}), onSuccess: () => cache.invalidateQueries({ queryKey: companyKey(companyId, resource) }) });
  if (record.isPending) return <Loading/>;
  if (record.error) return <Failure error={record.error} retry={() => void record.refetch()}/>;
  const item = record.data;
  const values: [string, string | undefined][] = resource === 'partners' ? [['E-mail', item.email], ['Téléphone', item.phone], ['Adresse', item.address], ['Type', [item.is_customer && 'Client', item.is_supplier && 'Fournisseur'].filter(Boolean).join(' · ')]] : resource === 'products' ? [['SKU', item.sku], ['Description', item.description], ['Unité', item.unit_name], ['Catégorie', item.category_name ?? undefined], ['Prix de vente', `${item.sale_price} ${context!.company.currency_code}`], ['Coût unitaire', `${item.cost_price} ${context!.company.currency_code}`], ['Taxes actuelles', item.taxes?.map(tax => `${tax.name} (${tax.rate} %)`).join(', ')]] : resource === 'taxes' ? [['Taux', `${item.rate} %`]] : [['Niveau', item.parent_id ? 'Sous-catégorie' : 'Catégorie principale']];
  return <><header className="page-heading"><div><p className="eyebrow">{config.singular.toUpperCase()}</p><h1>{item.name}</h1><span className="status-badge">{inactive ? 'Archivé' : 'Actif'}</span></div><div className="row-actions"><Link to={`${companyPath(companyId)}/${config.path}`} className="text-link">Retour à la liste</Link>{context!.permissions.includes(config.permission + '.manage') && <Button asChild><Link to="modifier">Modifier</Link></Button>}</div></header><section className="card"><dl className="details-grid">{values.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || 'Non renseigné'}</dd></div>)}</dl><ErrorMessage error={action.error}/>{resource !== 'categories' && context!.permissions.includes(config.permission + '.manage') && <Button className="archive-action" variant="outline" disabled={action.isPending} onClick={() => { if (window.confirm(`${inactive ? 'Réactiver' : 'Archiver'} ${item.name} ? Les données seront conservées.`)) action.mutate(); }}>{inactive ? 'Réactiver' : 'Archiver'}</Button>}</section>{resource === 'products' && <section className="card management-card"><h2>Historique des prix</h2>{history.isPending ? <Loading/> : history.error ? <Failure error={history.error} retry={() => void history.refetch()}/> : history.data.length ? <div className="table-scroll"><table><thead><tr><th>Date</th><th>Auteur</th><th>Vente : avant → après</th><th>Coût : avant → après</th></tr></thead><tbody>{history.data.map(entry => <tr key={entry.id}><td>{new Date(entry.created_at).toLocaleString('fr-FR')}</td><td>{entry.actor}</td><td>{entry.old_sale_price} → {entry.new_sale_price}</td><td>{entry.old_cost_price} → {entry.new_cost_price}</td></tr>)}</tbody></table></div> : <p>Aucune modification de prix enregistrée.</p>}</section>}</>;
}

export function UnitsPage() {
  const { companyId } = useWorkspace();
  const units = useQuery({ queryKey: companyKey(companyId, 'units'), queryFn: () => api<Unit[]>(`${prefix(companyId)}units/`), retry: false });
  return <><header className="page-heading"><div><p className="eyebrow">CATALOGUE GLOBAL</p><h1>Unités de mesure</h1><p>Chaque produit conserve une unité de référence ; aucune conversion implicite.</p></div></header><section className="card">{units.isPending ? <Loading/> : units.error ? <Failure error={units.error} retry={() => void units.refetch()}/> : <table><thead><tr><th>Unité</th><th>Symbole</th><th>Catégorie</th></tr></thead><tbody>{units.data.map(unit => <tr key={unit.id}><td>{unit.name}</td><td>{unit.symbol}</td><td>{unit.category}</td></tr>)}</tbody></table>}</section></>;
}
