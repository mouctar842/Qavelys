import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api, ApiError, type User } from '../api';
import { Button } from '../components/ui/button';
import { ErrorMessage, Loading } from '../components/feedback';
import { PublicHeader } from './public';
import { companyPath } from '../workspace';

const emailSchema = z.object({ email: z.email('Adresse e-mail invalide.') });
const passwordSchema = z.object({ password: z.string().min(8, 'Au moins 8 caractères.'), confirm: z.string() }).refine(value => value.password === value.confirm, { path: ['confirm'], message: 'Les mots de passe doivent être identiques.' });
export function ForgotPasswordPage() {
  const form = useForm<z.infer<typeof emailSchema>>({ resolver: zodResolver(emailSchema) });
  const action = useMutation({ mutationFn: (data: z.infer<typeof emailSchema>) => api<{ detail: string }>('auth/password-reset/', data) });
  return <><PublicHeader/><main className="verification-layout"><section className="card"><h1>Mot de passe oublié</h1><p>Recevez un lien pour choisir un nouveau mot de passe.</p>{action.isSuccess ? <p role="status">{action.data.detail}</p> : <form noValidate onSubmit={form.handleSubmit(data => action.mutate(data))}><label>E-mail<input type="email" autoComplete="email" {...form.register('email')}/><small>{form.formState.errors.email?.message}</small></label><ErrorMessage error={action.error}/><Button disabled={action.isPending}>Envoyer le lien</Button></form>}<Link to="/login">Retour à la connexion</Link></section></main></>;
}
export function ResetPasswordPage() {
  const params = new URLSearchParams(useLocation().hash.slice(1));
  const form = useForm<z.infer<typeof passwordSchema>>({ resolver: zodResolver(passwordSchema) });
  const action = useMutation({ mutationFn: (data: z.infer<typeof passwordSchema>) => api<{ detail: string }>('auth/password-reset-confirm/', { uid: params.get('uid'), token: params.get('token'), password: data.password }) });
  return <><PublicHeader/><main className="verification-layout"><section className="card"><h1>Nouveau mot de passe</h1>{action.isSuccess ? <p role="status">{action.data.detail}</p> : !params.get('uid') || !params.get('token') ? <p>Ce lien est incomplet. Demandez un nouveau lien de réinitialisation.</p> : <form noValidate onSubmit={form.handleSubmit(data => action.mutate(data))}><label>Nouveau mot de passe<input type="password" autoComplete="new-password" {...form.register('password')}/><small>{form.formState.errors.password?.message}</small></label><label>Confirmer le mot de passe<input aria-label="Confirmer le mot de passe" aria-describedby="reset-confirm-error" type="password" autoComplete="new-password" {...form.register('confirm')}/><small id="reset-confirm-error">{form.formState.errors.confirm?.message}</small></label><ErrorMessage error={action.error}/><Button disabled={action.isPending}>Enregistrer le mot de passe</Button></form>}<Link to="/login">Se connecter</Link></section></main></>;
}
const verificationSchema = emailSchema.extend({ password: z.string().min(1, 'Mot de passe requis.') });
export function ResendVerificationPage() {
  const form = useForm<z.infer<typeof verificationSchema>>({ resolver: zodResolver(verificationSchema) });
  const action = useMutation({ mutationFn: (data: z.infer<typeof verificationSchema>) => api<{ detail: string }>('auth/resend-verification/', data) });
  return <><PublicHeader/><main className="verification-layout"><section className="card"><h1>Recevoir un nouveau lien</h1>{action.isSuccess ? <p role="status">{action.data.detail}</p> : <form noValidate onSubmit={form.handleSubmit(data => action.mutate(data))}><label>E-mail<input type="email" {...form.register('email')}/><small>{form.formState.errors.email?.message}</small></label><label>Mot de passe<input type="password" autoComplete="current-password" {...form.register('password')}/><small>{form.formState.errors.password?.message}</small></label><ErrorMessage error={action.error}/><Button disabled={action.isPending}>Renvoyer le lien</Button></form>}<Link to="/login">Retour à la connexion</Link></section></main></>;
}
export function InvitationPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const token = new URLSearchParams(location.hash.slice(1)).get('token');
  const me = useQuery({ queryKey: ['me'], queryFn: () => api<User>('auth/me/'), retry: false });
  const action = useMutation({ mutationFn: () => api<{ company_id: string }>('invitations/accept/', { token }), onSuccess: result => { void cache.invalidateQueries({ queryKey: ['companies'] }); navigate(companyPath(result.company_id), { replace: true }); } });
  return <><PublicHeader/><main className="verification-layout"><section className="card"><h1>Rejoindre une entreprise</h1>{!token ? <p>Le lien d’invitation est incomplet.</p> : me.isPending ? <Loading text="Vérification de votre session…"/> : me.error ? <>{!(me.error instanceof ApiError && me.error.status === 403) && <ErrorMessage error={me.error}/>}<p>Connectez-vous ou créez votre compte avec l’adresse qui a reçu l’invitation.</p><div className="hero-actions"><Button asChild><Link to="/login" state={{ from: '/invitation' + location.hash }}>Se connecter</Link></Button><Link to="/register" state={{ from: '/invitation' + location.hash }}>Créer un compte</Link></div></> : <><p>Vous êtes connecté avec {me.data.email}. Acceptez l’invitation pour rejoindre l’entreprise.</p><ErrorMessage error={action.error}/><Button disabled={action.isPending} onClick={() => action.mutate()}>Accepter l’invitation</Button></>}</section></main></>;
}
