import { useOutletContext } from 'react-router-dom';
import type { Company, User } from './api';

export type CompanyContext = { company: Company; membership_id: string; permissions: string[]; modules?: string[] };
export type WorkspaceContext = { user: User; companies: Company[]; companyId: string; context?: CompanyContext; contextLoading: boolean; contextError: Error | null; retryContext: () => void };
export function useWorkspace() { return useOutletContext<WorkspaceContext>(); }
export const companyPath = (id: string) => `/administration/entreprises/${encodeURIComponent(id)}`;
export function rememberedCompany(userId: string) { try { return localStorage.getItem(`qavelys:company:${userId}`); } catch { return null; } }
export function rememberCompany(userId: string, companyId: string) { try { localStorage.setItem(`qavelys:company:${userId}`, companyId); } catch { /* La navigation par URL reste disponible. */ } }
