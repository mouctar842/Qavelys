import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { api, companyKey } from './api';
import { useWorkspace } from './workspace';

export function usePartnerPrefill(profile: 'customer' | 'supplier', enabled = true) {
  const { companyId } = useWorkspace(); const [params] = useSearchParams(); const id = params.get('partner');
  const query = useQuery({ queryKey: [...companyKey(companyId, 'partner-prefill'), id, profile], enabled: Boolean(id) && enabled, retry: false, queryFn: async () => {
    const row = await api<{ id: string; name: string; is_customer: boolean; is_supplier: boolean; status: string }>(`companies/${companyId}/reference/partners/${encodeURIComponent(id!)}/`);
    if (row.status !== 'active' || !row[profile === 'customer' ? 'is_customer' : 'is_supplier']) throw new Error('Ce tiers actif ne possède pas le profil requis pour ce document.');
    return row;
  } });
  return { ...query, requested: Boolean(id) && enabled };
}
