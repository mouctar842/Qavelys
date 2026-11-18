import { Link } from 'react-router-dom';
import { ArrowRight, Blocks } from 'lucide-react';
import { companyPath, useWorkspace } from '../workspace';

export function ApplicationsLauncher() {
  const { companyId, context } = useWorkspace();
  const applications = [
    { path: 'employes', title: 'Équipe et missions', text: 'Employés, départements et travail attribué.', module: 'hr', permission: 'hr.employee.view' },
    { path: 'tableau-de-bord', title: 'Ouvrir le tableau de bord', text: 'Indicateurs et alertes de l’entreprise.', module: 'dashboard', permission: 'dashboard.view' },
    { path: 'clients', title: 'Clients', text: 'Ventes, factures et encaissements.', module: 'contacts', permission: 'contacts.view' },
    { path: 'fournisseurs', title: 'Fournisseurs', text: 'Achats et réceptions.', module: 'contacts', permission: 'contacts.view' },
    { path: 'produits', title: 'Catalogue', text: 'Produits, services, unités et prix.', module: 'catalog', permission: 'products.view' },
    { path: 'crm', title: 'Prospection CRM', text: 'Prospects, opportunités et activités.', module: 'crm', permission: 'crm.view' },
    { path: 'ventes', title: 'Commandes clients', text: 'Devis, confirmations et livraisons.', module: 'sales', permission: 'sales.order.view' },
    { path: 'achats', title: 'Commandes fournisseurs', text: 'Achats et réceptions partielles.', module: 'purchases', permission: 'purchases.order.view' },
    { path: 'inventaire/stocks', title: 'Gestion des stocks', text: 'Disponible, réservations et mouvements.', module: 'inventory', permission: 'inventory.view' },
    { path: 'factures', title: 'Facturation clients', text: 'Factures, avoirs et PDF.', module: 'invoicing', permission: 'invoicing.invoice.view' },
    { path: 'paiements', title: 'Encaissements', text: 'Paiements et allocations aux factures.', module: 'invoicing', permission: 'invoicing.payment.view' },
    { path: 'notifications', title: 'Mes alertes personnelles', text: 'Échéances et décisions à consulter.', module: 'core', permission: 'notifications.view' },
  ].filter(app => context!.modules?.includes(app.module) && context!.permissions.includes(app.permission));
  return <><h2 className="section-heading">Applications de l’entreprise</h2>{applications.length === 0 ? <section className="card"><p>Aucune application métier accessible avec les modules et droits actuels.</p>{context!.permissions.includes('modules.view') && <Link to={`${companyPath(companyId)}/modules`}>Gérer les applications</Link>}</section> : <div className="quick-links applications-launcher">{applications.map(app => <Link className="card quick-link" key={app.path} to={`${companyPath(companyId)}/${app.path}`}><span className="feature-icon"><Blocks size={23}/></span><h3>{app.title}</h3><p>{app.text}</p><span className="text-link">Accéder <ArrowRight size={16}/></span></Link>)}</div>}</>;
}
