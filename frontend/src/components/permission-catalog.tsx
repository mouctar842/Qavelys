import { useState } from 'react';
import { Button } from './ui/button';

export type CatalogPermission = { code: string; description: string; module_code?: string; module_name?: string };
export function PermissionCatalog({ permissions, selected, onChange }: { permissions: CatalogPermission[]; selected: string[]; onChange?: (codes: string[]) => void }) {
  const [search, setSearch] = useState('');
  const groups = new Map<string, { name: string; items: CatalogPermission[] }>();
  for (const permission of permissions) {
    if (!onChange && !selected.includes(permission.code)) continue;
    const code = permission.module_code ?? 'core';
    const group = groups.get(code) ?? { name: permission.module_name ?? 'Administration', items: [] };
    group.items.push(permission); groups.set(code, group);
  }
  const term = search.trim().toLocaleLowerCase('fr');
  const visible = [...groups.entries()].map(([code, group]) => ({ code, ...group, items: group.items.filter(item => `${group.name} ${item.description} ${item.code}`.toLocaleLowerCase('fr').includes(term)) })).filter(group => group.items.length);
  return <div className="permission-catalog"><label>Rechercher une autorisation<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Module ou action…"/></label>{onChange && <p role="status">{selected.length} autorisation(s) sélectionnée(s)</p>}{visible.map(group => <fieldset key={group.code} className="permission-module"><legend>{group.name}</legend>{onChange && <div className="row-actions"><Button type="button" variant="outline" onClick={() => onChange([...new Set([...selected, ...group.items.map(item => item.code)])])}>Tout sélectionner · {group.name}</Button><Button type="button" variant="outline" onClick={() => onChange(selected.filter(code => !group.items.some(item => item.code === code)))}>Tout retirer · {group.name}</Button></div>}<div className="permission-grid">{group.items.map(item => onChange ? <label className="checkbox-label" key={item.code}><input type="checkbox" checked={selected.includes(item.code)} onChange={event => onChange(event.target.checked ? [...selected, item.code] : selected.filter(code => code !== item.code))}/><span>{item.description}</span></label> : <p key={item.code}>{item.description}</p>)}</div></fieldset>)}{!visible.length && <p>Aucune autorisation correspondante.</p>}<details><summary>Identifiants techniques des autorisations</summary><ul>{permissions.filter(item => selected.includes(item.code)).map(item => <li key={item.code}>{item.description} : <code>{item.code}</code></li>)}</ul></details></div>;
}
