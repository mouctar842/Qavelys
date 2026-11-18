import { Navigate, Route, Routes } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { NotFound } from './components/feedback';
import { AppLayout, CompanyGate, WorkspaceStart } from './layout/AppLayout';
import { AuthPage, VerifyEmailPage } from './pages/auth';
import { HomePage } from './pages/public';
import { ForgotPasswordPage, InvitationPage, ResetPasswordPage, ResendVerificationPage } from './pages/account-recovery';
import { AuditPage, InvitationsPage, ModulesPage, SequencesPage, SettingsPage } from './pages/core-management';
import { AccountPage, CompanyPage, CreateCompanyPage, MembersPage, OverviewPage, RolesPage } from './pages/administration';
import { ReferenceDetailPage, ReferenceEditorPage, ReferenceListPage, UnitsPage, referenceConfig, type Resource } from './pages/reference';
import './navigation.css';
import { CrmBoardPage, CrmListPage, CrmActivitiesPage, LeadDetailPage, LeadEditorPage } from './pages/crm';
import { InventoryDetailPage, InventoryDocumentEditor, InventoryListPage, InventoryStructureEditor, inventoryConfig, type InventoryResource } from './pages/inventory';
import { OrderDetailPage, OrderEditorPage, OrderListPage, orderConfig, type OrderDomain } from './pages/orders';
import { ApprovalRequestsPage, ApprovalRulesPage } from './pages/approvals';
import { FinanceDetailPage, FinanceListPage } from './pages/invoicing';
import { CreditEditorPage, InvoiceEditorPage } from './pages/invoice-editors';
import { PaymentDetailPage, PaymentEditorPage, PaymentListPage } from './pages/payments';
import { NotificationsPage } from './pages/notifications';
import { Loading } from './components/feedback';
import { PlatformPage } from './pages/platform';
import { PeopleDetailPage, PeopleEditorPage, PeopleListPage, peopleConfig, type PeopleResource } from './pages/people';
import { PartnerDetailPage, PartnerEditorPage, PartnerListPage, type PartnerProfile } from './pages/partners';
const DashboardPage = lazy(() => import('./pages/dashboard').then(module => ({ default: module.DashboardPage })));

function referenceRoutes(resource: Resource) {
  const config = referenceConfig[resource];
  return <Route key={resource} element={<CompanyGate permission={`${config.permission}.view`} module={config.module}/>}>
    <Route path={config.path} element={<ReferenceListPage key={resource} resource={resource}/>}/>
    <Route path={`${config.path}/:recordId`} element={<ReferenceDetailPage key={resource} resource={resource}/>}/>
    <Route element={<CompanyGate permission={`${config.permission}.manage`} module={config.module}/>}>
      <Route path={`${config.path}/nouveau`} element={<ReferenceEditorPage key={`${resource}-new`} resource={resource}/>}/>
      <Route path={`${config.path}/:recordId/modifier`} element={<ReferenceEditorPage key={`${resource}-edit`} resource={resource}/>}/>
    </Route>
  </Route>;
}

function inventoryRoutes(resource: InventoryResource) {
  const config = inventoryConfig[resource];
  const structure = resource === 'warehouses' || resource === 'locations';
  return <Route key={resource} element={<CompanyGate permission="inventory.view" module="inventory"/>}>
    <Route path={`inventaire/${config.path}`} element={<InventoryListPage resource={resource} key={resource}/>}/>
    {config.permission && <Route path={`inventaire/${config.path}/:recordId`} element={<InventoryDetailPage resource={resource} key={resource}/>}/>}
    {config.permission && <Route element={<CompanyGate permission={config.permission} module="inventory"/>}>
      <Route path={`inventaire/${config.path}/nouveau`} element={structure ? <InventoryStructureEditor resource={resource} key={`${resource}-new`}/> : <InventoryDocumentEditor resource={resource as 'transfers' | 'adjustments'} key={resource}/>}/>
      {structure && <Route path={`inventaire/${config.path}/:recordId/modifier`} element={<InventoryStructureEditor resource={resource} key={`${resource}-edit`}/>}/>}
    </Route>}
  </Route>;
}

export default function AppRouter() {
  return <Routes>
    <Route path="/plateforme" element={<PlatformPage/>}/>
    <Route path="/" element={<HomePage/>}/>
    <Route path="/login" element={<AuthPage key="login"/>}/>
    <Route path="/register" element={<AuthPage key="register" registerMode/>}/>
    <Route path="/verify-email" element={<VerifyEmailPage/>}/>
    <Route path="/forgot-password" element={<ForgotPasswordPage/>}/>
    <Route path="/reset-password" element={<ResetPasswordPage/>}/>
    <Route path="/resend-verification" element={<ResendVerificationPage/>}/>
    <Route path="/invitation" element={<InvitationPage/>}/>
    <Route path="/inscription" element={<Navigate to="/register" replace/>}/>
    <Route path="/connexion" element={<Navigate to="/login" replace/>}/>
    <Route path="/admin" element={<Navigate to="/administration" replace/>}/>
    <Route path="/administration" element={<AppLayout/>}>
      <Route index element={<WorkspaceStart/>}/>
      <Route path="entreprise/nouvelle" element={<CreateCompanyPage/>}/>
      <Route path="compte" element={<AccountPage/>}/>
      <Route path="entreprises/:companyId" element={<CompanyGate/>}>
        <Route index element={<OverviewPage/>}/>
        <Route path="entreprise" element={<CompanyPage/>}/>
        {(['customer', 'supplier'] as PartnerProfile[]).map(profile => { const path = profile === 'customer' ? 'clients' : 'fournisseurs'; return <Route key={profile} element={<CompanyGate permission="contacts.view" module="contacts"/>}>
          <Route path={path} element={<PartnerListPage key={profile} profile={profile}/>}/>
          <Route path={`${path}/:recordId`} element={<PartnerDetailPage key={profile} profile={profile}/>}/>
          <Route element={<CompanyGate permission="contacts.manage" module="contacts"/>}>
            <Route path={`${path}/nouveau`} element={<PartnerEditorPage key={`${profile}-new`} profile={profile}/>}/>
            <Route path={`${path}/:recordId/modifier`} element={<PartnerEditorPage key={`${profile}-edit`} profile={profile}/>}/>
          </Route>
        </Route>; })}
        {(Object.keys(peopleConfig) as PeopleResource[]).map(resource => <Route key={resource} element={<CompanyGate permission={`${peopleConfig[resource].permission}.view`} module="hr"/>}>
          <Route path={peopleConfig[resource].path} element={<PeopleListPage key={resource} resource={resource}/>}/>
          <Route path={`${peopleConfig[resource].path}/:recordId`} element={<PeopleDetailPage key={resource} resource={resource}/>}/>
          <Route element={<CompanyGate permission={`${peopleConfig[resource].permission}.manage`} module="hr"/>}>
            <Route path={`${peopleConfig[resource].path}/nouveau`} element={<PeopleEditorPage key={`${resource}-new`} resource={resource}/>}/>
            <Route path={`${peopleConfig[resource].path}/:recordId/modifier`} element={<PeopleEditorPage key={`${resource}-edit`} resource={resource}/>}/>
          </Route>
        </Route>)}
        <Route element={<CompanyGate permission="dashboard.view" module="dashboard"/>}><Route path="tableau-de-bord" element={<Suspense fallback={<Loading/>}><DashboardPage/></Suspense>}/></Route>
        <Route element={<CompanyGate permission="notifications.view" module="core"/>}><Route path="notifications" element={<NotificationsPage/>}/></Route>
        <Route element={<CompanyGate permission="invoicing.payment.view" module="invoicing"/>}>
          <Route path="paiements" element={<PaymentListPage/>}/>
          <Route path="paiements/:paymentId" element={<PaymentDetailPage/>}/>
          <Route element={<CompanyGate permission="invoicing.payment.create" module="invoicing"/>}><Route path="paiements/nouveau" element={<PaymentEditorPage/>}/></Route>
        </Route>
        <Route element={<CompanyGate permission="invoicing.invoice.view" module="invoicing"/>}>
          <Route path="factures" element={<FinanceListPage kind="invoices"/>}/>
          <Route path="factures/:documentId" element={<FinanceDetailPage kind="invoices" key="invoice"/>}/>
          <Route element={<CompanyGate permission="invoicing.invoice.create" module="invoicing"/>}><Route path="factures/nouveau" element={<InvoiceEditorPage/>}/></Route>
          <Route element={<CompanyGate permission="invoicing.credit_note.view" module="invoicing"/>}>
            <Route path="avoirs" element={<FinanceListPage kind="credit-notes"/>}/>
            <Route path="avoirs/:documentId" element={<FinanceDetailPage kind="credit-notes" key="credit-note"/>}/>
            <Route element={<CompanyGate permission="invoicing.credit_note.create" module="invoicing"/>}><Route path="avoirs/nouveau" element={<CreditEditorPage/>}/></Route>
          </Route>
        </Route>
        {(['sales', 'purchases'] as OrderDomain[]).map(domain => <Route key={domain} element={<CompanyGate permission={`${domain}.order.view`} module={domain}/>}>
          <Route path={orderConfig[domain].path} element={<OrderListPage domain={domain} key={domain}/>}/>
          <Route path={`${orderConfig[domain].path}/:orderId`} element={<OrderDetailPage domain={domain} key={domain}/>}/>
          <Route element={<CompanyGate permission={`${domain}.order.create`} module={domain}/>}><Route path={`${orderConfig[domain].path}/nouveau`} element={<OrderEditorPage domain={domain} key={`${domain}-new`}/>}/></Route>
          <Route element={<CompanyGate permission={`${domain}.order.edit`} module={domain}/>}><Route path={`${orderConfig[domain].path}/:orderId/modifier`} element={<OrderEditorPage domain={domain} key={`${domain}-edit`}/>}/></Route>
        </Route>)}
        <Route element={<CompanyGate permission="approvals.rules.view"/>}><Route path="regles-approbation" element={<ApprovalRulesPage/>}/></Route>
        <Route element={<CompanyGate permission="approvals.requests.view"/>}><Route path="approbations" element={<ApprovalRequestsPage/>}/></Route>
        <Route element={<CompanyGate permission="crm.view" module="crm"/>}>
          <Route path="crm" element={<CrmBoardPage/>}/>
          <Route path="crm/liste" element={<CrmListPage/>}/>
          <Route path="crm/activites" element={<CrmActivitiesPage/>}/>
          <Route path="crm/:leadId" element={<LeadDetailPage/>}/>
          <Route element={<CompanyGate permission="crm.manage" module="crm"/>}>
            <Route path="crm/nouveau" element={<LeadEditorPage key="new"/>}/>
            <Route path="crm/:leadId/modifier" element={<LeadEditorPage key="edit"/>}/>
          </Route>
        </Route>
        {(['partners', 'products', 'categories', 'taxes'] as const).map(referenceRoutes)}
        {(Object.keys(inventoryConfig) as InventoryResource[]).map(inventoryRoutes)}
        <Route element={<CompanyGate permission="products.view" module="catalog"/>}><Route path="unites" element={<UnitsPage/>}/></Route>
        <Route element={<CompanyGate permission="company.manage"/>}><Route path="parametres" element={<SettingsPage/>}/></Route>
        <Route element={<CompanyGate permission="members.manage"/>}><Route path="invitations" element={<InvitationsPage/>}/></Route>
        <Route element={<CompanyGate permission="modules.view"/>}><Route path="modules" element={<ModulesPage/>}/></Route>
        <Route element={<CompanyGate permission="audit.view"/>}><Route path="audit" element={<AuditPage/>}/></Route>
        <Route element={<CompanyGate permission="sequences.view"/>}><Route path="sequences" element={<SequencesPage/>}/></Route>
        <Route element={<CompanyGate permission="members.view"/>}><Route path="collaborateurs" element={<MembersPage/>}/></Route>
        <Route element={<CompanyGate permission="roles.view"/>}><Route path="roles" element={<RolesPage/>}/></Route>
        <Route path="*" element={<NotFound/>}/>
      </Route>
      <Route path="*" element={<NotFound/>}/>
    </Route>
    <Route path="*" element={<main className="verification-layout"><NotFound/></main>}/>
  </Routes>;
}
