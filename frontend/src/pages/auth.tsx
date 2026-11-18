import { useState } from 'react';
import { ArrowRight, Eye, EyeOff, ShieldCheck } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { api } from '../api';
import { Button } from '../components/ui/button';
import { ErrorMessage } from '../components/feedback';
import { PublicHeader } from './public';

const credentials = z.object({ email: z.email('Adresse e-mail invalide.'), password: z.string().min(1, 'Mot de passe requis.') });
const registration = credentials.extend({ full_name: z.string().trim().min(1, 'Nom requis.'), password: z.string().min(8, 'Au moins 8 caractères.') });
export function AuthPage({ registerMode = false }: { registerMode?: boolean }) {
  const navigate = useNavigate();
  const location = useLocation();
  const cache = useQueryClient();
  const [showPassword, setShowPassword] = useState(false);
  const form = useForm<z.infer<typeof registration>>({ resolver: zodResolver(registerMode ? registration : credentials.extend({ full_name: z.string() })), defaultValues: { email: '', password: '', full_name: '' } });
  const action = useMutation({ mutationFn: (data: z.infer<typeof registration>) => api<{ detail?: string; authenticated?: boolean }>(`auth/${registerMode ? 'register' : 'login'}/`, data), onSuccess: data => {
    if (!registerMode || data.authenticated) {
      cache.removeQueries();
      const from: unknown = location.state?.from;
      const destination = typeof from === 'string' && (from.startsWith('/administration/') || from.startsWith('/invitation#')) ? from : '/administration';
      navigate(destination, { replace: true });
    }
  } });
  return <><PublicHeader/><main className="auth-layout"><aside className="auth-story"><p className="eyebrow">UN ESPACE QUI VOUS APPARTIENT</p><h2>Votre entreprise.<br/>Vos équipes.<br/><em>Le même cap.</em></h2><p>Retrouvez vos sociétés dans un espace de travail organisé, avec les bons accès pour chaque membre.</p><div className="auth-assurance"><ShieldCheck size={21}/><span>Votre session est sécurisée.<br/>Les données de chaque entreprise sont séparées.</span></div></aside><section className="card auth-panel"><span className="eyebrow">{registerMode ? 'ÉTAPE 1 · VOTRE COMPTE' : 'VOTRE ESPACE DE GESTION'}</span><h1>{registerMode ? 'Créer votre compte' : 'Bienvenue sur Qavelys'}</h1><p>{registerMode ? 'Créez votre compte, puis ajoutez votre entreprise dans votre espace d’administration.' : 'Connectez-vous pour retrouver votre entreprise et votre administration.'}</p>{action.isSuccess && registerMode ? <div className="success-state"><p role="status">{action.data.detail}</p><Button asChild><Link to="/login">Se connecter <ArrowRight size={16}/></Link></Button></div> : <form noValidate onSubmit={form.handleSubmit(data => action.mutate(data))}>
    {registerMode && <label>Nom complet<input autoComplete="name" {...form.register('full_name')}/><small>{form.formState.errors.full_name?.message}</small></label>}
    <label>E-mail<input type="email" autoComplete="email" placeholder="vous@entreprise.com" {...form.register('email')}/><small>{form.formState.errors.email?.message}</small></label>
    <label>Mot de passe<div className="password-field"><input type={showPassword ? 'text' : 'password'} autoComplete={registerMode ? 'new-password' : 'current-password'} {...form.register('password')}/><button type="button" aria-label={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div><small>{form.formState.errors.password?.message}</small></label>
    <ErrorMessage error={action.error}/><Button disabled={action.isPending}>{action.isPending ? 'Ouverture de votre espace…' : registerMode ? 'Créer mon compte' : 'Se connecter'}<ArrowRight size={16}/></Button>
  </form>}{!registerMode && <div className="recovery-links"><Link to="/forgot-password">Mot de passe oublié ?</Link><Link to="/resend-verification">Recevoir un lien de vérification</Link></div>}<p className="auth-switch">{registerMode ? 'Déjà inscrit ?' : 'Première visite ?'} <Link to={registerMode ? '/login' : '/register'} state={location.state}>{registerMode ? 'Se connecter' : 'Créer un compte'}</Link></p><Link className="back-link" to="/">← Retour à l’accueil</Link></section></main></>;
}

export function VerifyEmailPage() {
  const params = new URLSearchParams(useLocation().hash.slice(1));
  const mutation = useMutation({ mutationFn: () => api<{ detail: string }>('auth/verify-email/', { token: params.get('token') ?? '' }) });
  return <><PublicHeader/><main className="verification-layout"><section className="card"><ShieldCheck size={32}/><h1>Vérification de l’adresse</h1><ErrorMessage error={mutation.error}/>{mutation.isSuccess ? <><p role="status">{mutation.data.detail}</p><Button asChild><Link to="/login">Se connecter</Link></Button></> : params.get('token') ? <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>Vérifier mon adresse</Button> : <><p>Ouvrez le lien complet reçu dans votre e-mail pour vérifier votre adresse.</p><Link to="/login">Retour à la connexion</Link></>}</section></main></>;
}
