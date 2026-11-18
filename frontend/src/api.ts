export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
let csrfToken: string | undefined;
export async function api<T>(path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  if (body !== undefined) {
    const response = await fetch('/api/v1/auth/csrf/', { credentials: 'same-origin' });
    if (!response.ok) throw new ApiError(response.status, 'Impossible d’obtenir le jeton de sécurité.');
    csrfToken = (await response.json() as { csrfToken: string }).csrfToken;
  }
  const response = await fetch(`/api/v1/${path}`, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {}), ...headers }, body: body === undefined ? undefined : JSON.stringify(body) });
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, data && typeof data === 'object' ? Object.entries(data).map(([key, value]) => `${key === 'detail' ? '' : `${key} : `}${String(value)}`).join(' ') : 'Le serveur est indisponible.');
  return data as T;
}
export type Company = { id: string; name: string; country_code: string; currency_code: string; sector: string; logo_url?: string | null };
export type User = { id: string; full_name: string; email: string; is_platform_admin?: boolean };

export async function uploadCompanyLogo(companyId: string, file: File): Promise<{ logo_url: string }> {
  const tokenResponse = await fetch('/api/v1/auth/csrf/', { credentials: 'same-origin' });
  if (!tokenResponse.ok) throw new ApiError(tokenResponse.status, 'Impossible d’obtenir le jeton de sécurité.');
  const { csrfToken } = await tokenResponse.json() as { csrfToken: string };
  const body = new FormData(); body.append('logo', file);
  const response = await fetch(`/api/v1/companies/${companyId}/logo/`, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken }, body });
  const data = await response.json().catch(() => null) as { logo_url: string; detail?: string; logo?: string[] } | null;
  if (!response.ok) throw new ApiError(response.status, data?.detail || data?.logo?.join(' ') || 'Impossible d’importer ce logo.');
  if (!data?.logo_url) throw new ApiError(502, 'Réponse du serveur incomplète.');
  return data;
}
export const companyKey = (companyId: string, resource: string) => ['company', companyId, resource] as const;
