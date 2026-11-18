import { useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { companyKey, uploadCompanyLogo, type Company } from '../api';
import { useWorkspace } from '../workspace';
import { Button } from './ui/button';
import { ErrorMessage } from './feedback';

export function CompanyMark({ company, className = '' }: { company: Pick<Company, 'name' | 'logo_url'>; className?: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => { setFailed(false); }, [company.logo_url]);
  return company.logo_url && !failed
    ? <img className={`company-logo ${className}`} src={company.logo_url} alt={`Logo de ${company.name}`} onError={() => setFailed(true)}/>
    : <span className={`company-logo company-logo-initial ${className}`} aria-label={`Entreprise ${company.name}`}>{company.name.slice(0, 1).toUpperCase()}</span>;
}

export function LogoEditor({ logoUrl }: { logoUrl?: string | null }) {
  const { companyId, context } = useWorkspace();
  const cache = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [validation, setValidation] = useState('');
  const action = useMutation({
    mutationFn: (image: File) => uploadCompanyLogo(companyId, image),
    onSuccess: async () => {
      setFile(null); if (input.current) input.current.value = '';
      await Promise.all([cache.invalidateQueries({ queryKey: companyKey(companyId, 'settings') }), cache.invalidateQueries({ queryKey: companyKey(companyId, 'context') }), cache.invalidateQueries({ queryKey: ['companies'] })]);
    },
  });
  return <section className="card management-card logo-editor">
    <h2>Logo de l’entreprise</h2>
    <CompanyMark company={{ name: context!.company.name, logo_url: logoUrl }}/>
    <p>Importez le logo fourni par votre entreprise. PNG, JPEG ou WebP fixe, 2 Mio maximum et 4096 × 4096 pixels maximum.</p>
    <form onSubmit={event => { event.preventDefault(); if (file && !validation) action.mutate(file); }}>
      <label htmlFor="company-logo-file">Fichier du logo</label>
      <input ref={input} id="company-logo-file" type="file" accept="image/png,image/jpeg,image/webp" disabled={action.isPending} onChange={event => {
        const image = event.target.files?.[0] ?? null; setFile(image); action.reset();
        setValidation(image && image.size > 2 * 1024 * 1024 ? 'Le fichier dépasse 2 Mio.' : '');
      }}/>
      {validation && <p role="alert">{validation}</p>}
      <ErrorMessage error={action.error}/>
      {action.isSuccess && <p role="status">Logo enregistré.</p>}
      <Button disabled={!file || Boolean(validation) || action.isPending}>{action.isPending ? 'Import en cours…' : 'Importer le logo'}</Button>
    </form>
  </section>;
}
