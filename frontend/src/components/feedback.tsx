import { AlertCircle, ArrowRight, LoaderCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Button } from './ui/button';

export function Loading({ text = 'Chargement de votre espace…' }: { text?: string }) {
  return <div className="loading-state" role="status"><LoaderCircle size={22} className="spin"/>{text}</div>;
}
export function ErrorMessage({ error }: { error: Error | null }) {
  return error ? <p role="alert" className="error inline-error"><AlertCircle size={18}/>{error.message}</p> : null;
}
export function Failure({ error, retry }: { error: Error; retry?: () => void }) {
  return <section className="card failure"><AlertCircle size={30}/><h2>Impossible d’ouvrir cette page</h2><ErrorMessage error={error}/>{retry && <Button variant="outline" onClick={retry}>Réessayer</Button>}</section>;
}
export function NotFound() {
  return <section className="card empty-state"><span className="eyebrow">PAGE INTROUVABLE</span><h1>Ce chemin ne mène à aucune page.</h1><p>Retrouvez votre espace depuis l’administration.</p><Button asChild><Link to="/administration">Retour à mon espace <ArrowRight size={16}/></Link></Button></section>;
}
