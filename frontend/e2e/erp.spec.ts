import { test, expect, type Page, type Locator, type TestInfo } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';

type Saved = { id: string; reference: string; version: number; lines: { id: string }[] };
const companyPath = (id: string) => `/administration/entreprises/${id}`;
const apiPath = (id: string, suffix: string) => `/api/v1/companies/${id}/${suffix}`;

async function openPage(page: Page, pathname: string) {
  if (new URL(page.url()).pathname === pathname) return;
  const link = page.locator(`a[href="${pathname}"]`).first();
  if (await link.isVisible()) await link.click();
  else await page.goto(pathname);
  await expect(page).toHaveURL(pathname);
}

async function submit<T>(page: Page, path: string, button: Locator): Promise<T> {
  const [response] = await Promise.all([page.waitForResponse(response => new URL(response.url()).pathname === path && response.request().method() === 'POST', { timeout: 90_000 }), button.click()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return await response.json() as T;
}

async function signup(page: Page, tag: string) {
  const email = `qa-${randomUUID()}@example.invalid`; const password = 'Qavelys-E2E!2026-Only';
  await page.goto('/register');
  await page.getByLabel('Nom complet', { exact: true }).fill(`Administrateur E2E ${tag}`);
  await page.getByLabel('E-mail', { exact: true }).fill(email);
  await page.getByLabel('Mot de passe', { exact: true }).fill(password);
  await submit(page, '/api/v1/auth/register/', page.getByRole('button', { name: 'Créer mon compte', exact: true }));
  await expect(page).toHaveURL(/\/administration\/entreprise\/nouvelle$/);
  const company = await createCompany(page, `E2E Commerce ${tag}`);
  return { company, email, password };
}

async function createCompany(page: Page, name: string) {
  await page.getByLabel('Nom de l’entreprise', { exact: true }).fill(name);
  await page.getByLabel('Pays (code à 2 lettres)', { exact: true }).fill('FR');
  await page.getByLabel('Devise principale', { exact: true }).fill('EUR');
  const company = await submit<{ id: string; name: string }>(page, '/api/v1/companies/', page.getByRole('button', { name: 'Créer mon espace administrateur', exact: true }));
  await expect(page).toHaveURL(companyPath(company.id));
  return company;
}

async function enable(page: Page, companyId: string, code: string, name: string) {
  await openPage(page, companyPath(companyId) + '/modules');
  const card = page.locator('.module-grid > section').filter({ has: page.getByRole('heading', { name, exact: true }) });
  await expect(card).toBeVisible();
  if (await card.getByRole('button', { name: 'Désactiver', exact: true }).isVisible()) return;
  await submit(page, apiPath(companyId, `modules/${code}/enable/`), card.getByRole('button', { name: 'Activer avec ses dépendances', exact: true }));
  await expect(card.getByRole('button', { name: 'Désactiver', exact: true })).toBeVisible();
}

async function partner(page: Page, companyId: string, name = 'Contact E2E') {
  await page.goto(companyPath(companyId) + '/contacts/nouveau');
  await page.getByLabel('Nom', { exact: true }).fill(name);
  await page.getByRole('checkbox', { name: 'Client', exact: true }).check();
  await page.getByRole('checkbox', { name: 'Fournisseur', exact: true }).check();
  const contact = await submit<{ id: string }>(page, apiPath(companyId, 'reference/partners/'), page.getByRole('button', { name: 'Enregistrer', exact: true }));
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  return contact;
}

async function order(page: Page, companyId: string, domain: 'sales' | 'purchases', partnerId: string, warehouseId: string, productId: string, quantity: string) {
  await page.goto(companyPath(companyId) + (domain === 'sales' ? '/ventes/nouveau' : '/achats/nouveau'));
  await expect(page.getByRole('option', { name: 'E2E-ART — Article E2E', exact: true })).toBeAttached();
  await page.getByLabel(domain === 'sales' ? 'Client' : 'Fournisseur', { exact: true }).selectOption(partnerId);
  await page.getByLabel('Entrepôt', { exact: true }).selectOption(warehouseId);
  await page.getByLabel('Produit 1', { exact: true }).selectOption(productId);
  await page.getByLabel('Quantité 1', { exact: true }).fill(quantity);
  const obj = await submit<Saved>(page, apiPath(companyId, `${domain}/orders/`), page.getByRole('button', { name: 'Enregistrer le brouillon', exact: true }));
  await expect(page.getByRole('heading', { name: obj.reference, exact: true })).toBeVisible();
  await submit(page, apiPath(companyId, `${domain}/orders/${obj.id}/confirm/`), page.getByRole('button', { name: 'Confirmer la commande', exact: true }));
  await expect(page.getByText('Confirmée', { exact: true })).toBeVisible();
  return obj;
}

async function fulfillment(page: Page, companyId: string, kind: 'receipts' | 'deliveries', quantity: string) {
  const receipt = kind === 'receipts';
  await page.getByLabel(`Article E2E — quantité à ${receipt ? 'recevoir' : 'livrer'}`, { exact: true }).fill(quantity);
  const document = await submit<Saved>(page, apiPath(companyId, `inventory/${kind}/`), page.getByRole('button', { name: `Créer le brouillon de ${receipt ? 'réception' : 'livraison'}`, exact: true }));
  await submit(page, apiPath(companyId, `inventory/${kind}/${document.id}/validate/`), page.getByRole('button', { name: `Valider ${document.reference}`, exact: true }));
  return document;
}

async function invoice(page: Page, companyId: string, orderId: string, quantity: string) {
  await openPage(page, `${companyPath(companyId)}/ventes/${orderId}`);
  await page.getByRole('link', { name: 'Facturer la commande', exact: true }).click();
  await expect(page.getByLabel('Prix unitaire 1', { exact: true })).toHaveAttribute('readonly');
  await page.getByLabel('Quantité à facturer 1', { exact: true }).fill(quantity);
  const obj = await submit<Saved>(page, apiPath(companyId, 'invoicing/invoices/'), page.getByRole('button', { name: 'Créer le brouillon de facture', exact: true }));
  await submit(page, apiPath(companyId, `invoicing/invoices/${obj.id}/validate/`), page.getByRole('button', { name: 'Valider le document', exact: true }));
  await expect(page.getByText('Validé', { exact: true })).toBeVisible();
  return obj;
}

async function paymentFromInvoice(page: Page, companyId: string, invoiceId: string, amount: string) {
  await page.goto(`${companyPath(companyId)}/factures/${invoiceId}`);
  await page.getByRole('link', { name: 'Enregistrer un paiement pour cette facture', exact: true }).click();
  await expect(page.getByLabel('Client du paiement', { exact: true })).not.toHaveValue('');
  await page.getByLabel('Montant reçu (EUR)', { exact: true }).fill(amount);
  const pay = await submit<Saved>(page, apiPath(companyId, 'invoicing/payments/'), page.getByRole('button', { name: 'Créer le brouillon de paiement', exact: true }));
  await submit(page, apiPath(companyId, `invoicing/payments/${pay.id}/validate/`), page.getByRole('button', { name: 'Valider le paiement', exact: true }));
  await expect(page.getByRole('heading', { name: 'Répartir le paiement', exact: true })).toBeVisible();
  return pay;
}

async function getJson<T>(page: Page, path: string): Promise<T> {
  const response = await page.request.get(path); expect(response.ok(), await response.text()).toBeTruthy(); return await response.json() as T;
}

test('parcours commercial réel, isolation et affichage mobile', async ({ page }, testInfo: TestInfo) => {
  page.on('dialog', dialog => dialog.accept());
  const browserErrors: string[] = []; page.on('pageerror', error => browserErrors.push(error.message));
  const { company, email, password } = await test.step('inscription et entreprise administrée', () => signup(page, 'parcours'));
  const id = company.id; const root = companyPath(id);
  await test.step('activation des modules réels et dépendances', async () => {
    for (const [code, name] of [['sales', 'Ventes'], ['purchases', 'Achats'], ['invoicing', 'Facturation'], ['dashboard', 'Tableau de bord'], ['crm', 'CRM']]) await enable(page, id, code, name);
  });
  const contact = await test.step('client et fournisseur', () => partner(page, id));
  const product = await test.step('taxe et produit réels', async () => {
    await page.goto(root + '/taxes/nouveau');
    await page.getByLabel('Nom', { exact: true }).fill('TVA E2E'); await page.getByLabel('Taux (%)', { exact: true }).fill('20');
    await submit(page, apiPath(id, 'reference/taxes/'), page.getByRole('button', { name: 'Enregistrer', exact: true }));
    await page.goto(root + '/produits/nouveau');
    await page.getByLabel('Nom', { exact: true }).fill('Article E2E'); await page.getByLabel('SKU', { exact: true }).fill('E2E-ART');
    await page.getByLabel('Prix de vente', { exact: true }).fill('10'); await page.getByLabel('Coût unitaire', { exact: true }).fill('3');
    await expect(page.getByRole('option', { name: 'Unité (u)', exact: true })).toBeAttached(); await page.getByLabel('Unité de référence', { exact: true }).selectOption({ label: 'Unité (u)' });
    await page.getByRole('checkbox', { name: /TVA E2E/ }).check();
    return submit<{ id: string }>(page, apiPath(id, 'reference/products/'), page.getByRole('button', { name: 'Enregistrer', exact: true }));
  });
  const warehouse = await test.step('création d’un entrepôt et emplacement', async () => {
    await page.goto(root + '/inventaire/entrepots/nouveau');
    await page.getByLabel('Nom', { exact: true }).fill('Dépôt E2E'); await page.getByLabel('Code', { exact: true }).fill('E2E');
    return submit<{ id: string }>(page, apiPath(id, 'inventory/warehouses/'), page.getByRole('button', { name: 'Enregistrer', exact: true }));
  });
  await test.step('commande fournisseur et deux réceptions partielles', async () => {
    const purchase = await order(page, id, 'purchases', contact.id, warehouse.id, product.id, '10');
    await fulfillment(page, id, 'receipts', '6'); await fulfillment(page, id, 'receipts', '4');
    const closed = await submit<{ status: string }>(page, apiPath(id, `purchases/orders/${purchase.id}/complete/`), page.getByRole('button', { name: 'Clôturer la commande', exact: true }));
    expect(closed.status).toBe('completed');
    const stock = await getJson<{ results: { product_id: string; quantity: string }[] }>(page, apiPath(id, 'inventory/balances/'));
    expect(stock.results.find(row => row.product_id === product.id)?.quantity).toMatch(/^10(?:\.0+)?$/);
  });
  const sale = await test.step('devis, confirmation et réservation', async () => {
    const obj = await order(page, id, 'sales', contact.id, warehouse.id, product.id, '8');
    const saved = await getJson<{ lines: { reserved_quantity: string; waiting_quantity: string }[] }>(page, apiPath(id, `sales/orders/${obj.id}/`));
    expect(saved.lines[0].reserved_quantity).toMatch(/^8(?:\.0+)?$/); expect(saved.lines[0].waiting_quantity).toMatch(/^0(?:\.0+)?$/);
    return obj;
  });
  await test.step('deux livraisons partielles et solde physique', async () => {
    await fulfillment(page, id, 'deliveries', '3'); await fulfillment(page, id, 'deliveries', '5');
    const stock = await getJson<{ results: { product_id: string; quantity: string; reserved_quantity: string }[] }>(page, apiPath(id, 'inventory/balances/'));
    const balance = stock.results.find(row => row.product_id === product.id)!; expect(balance.quantity).toMatch(/^2(?:\.0+)?$/); expect(balance.reserved_quantity).toMatch(/^0(?:\.0+)?$/);
  });
  const firstInvoice = await test.step('première facture partielle', () => invoice(page, id, sale.id, '3'));
  const secondInvoice = await test.step('seconde facture partielle', () => invoice(page, id, sale.id, '5'));
  await test.step('un paiement réparti entre deux factures', async () => {
    const pay = await paymentFromInvoice(page, id, firstInvoice.id, '50');
    await expect(page.getByLabel('Facture à régler 1', { exact: true })).toHaveValue(firstInvoice.id);
    await page.getByLabel('Montant à allouer 1', { exact: true }).fill('36');
    await page.getByRole('button', { name: 'Ajouter une facture à régler', exact: true }).click();
    await page.getByLabel('Facture à régler 2', { exact: true }).selectOption(secondInvoice.id); await page.getByLabel('Montant à allouer 2', { exact: true }).fill('14');
    await submit(page, apiPath(id, `invoicing/payments/${pay.id}/allocate/`), page.getByRole('button', { name: 'Confirmer les allocations', exact: true }));
    const remaining = await getJson<{ amount_due: string }>(page, apiPath(id, `invoicing/invoices/${secondInvoice.id}/`)); expect(remaining.amount_due).toMatch(/^46(?:\.0+)?$/);
  });
  await test.step('second paiement et soldes exacts', async () => {
    const pay = await paymentFromInvoice(page, id, secondInvoice.id, '46');
    await page.getByLabel('Montant à allouer 1', { exact: true }).fill('46');
    await submit(page, apiPath(id, `invoicing/payments/${pay.id}/allocate/`), page.getByRole('button', { name: 'Confirmer les allocations', exact: true }));
    for (const obj of [firstInvoice, secondInvoice]) {
      const result = await getJson<{ payment_status: string; amount_due: string }>(page, apiPath(id, `invoicing/invoices/${obj.id}/`)); expect(result.payment_status).toBe('paid'); expect(result.amount_due).toMatch(/^0(?:\.0+)?$/);
    }
  });
  await test.step('clôture commerciale après règlement et reprise motivée', async () => {
    await page.goto(root + `/ventes/${sale.id}`);
    const closed = await submit<{ closure_version: number; status: string }>(page, apiPath(id, `sales/orders/${sale.id}/complete/`), page.getByRole('button', { name: 'Clôturer la commande', exact: true }));
    expect(closed.status).toBe('completed'); expect(closed.closure_version).toBe(1);
    await page.getByLabel('Motif de reprise', { exact: true }).fill('Contrôle commercial E2E');
    const resumed = await submit<{ closure_version: number; status: string }>(page, apiPath(id, `sales/orders/${sale.id}/resume/`), page.getByRole('button', { name: 'Reprendre la commande', exact: true }));
    expect(resumed.status).toBe('confirmed'); expect(resumed.closure_version).toBe(2);
    await submit(page, apiPath(id, `sales/orders/${sale.id}/complete/`), page.getByRole('button', { name: 'Clôturer la commande', exact: true }));
    await expect(page.locator('.page-heading .status-badge')).toHaveText('Terminée');
    await expect(page.getByLabel('Motif de reprise', { exact: true })).toHaveValue('');
    await expect(page.getByRole('link', { name: 'Facturer la commande', exact: true })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath('commande-cloturee.png'), fullPage: true });
  });
  await test.step('PDF réellement téléchargé', async () => {
    await page.goto(root + `/factures/${firstInvoice.id}`);
    const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Télécharger le PDF', exact: true }).click()]);
    expect(download.suggestedFilename()).toBe(firstInvoice.reference + '.pdf');
    const output = testInfo.outputPath('facture.pdf'); await download.saveAs(output);
    const data = await readFile(output); expect(data.subarray(0,5).toString()).toBe('%PDF-'); expect(data.length).toBeGreaterThan(1000);
  });
  await test.step('dashboard réel et captures desktop/mobile/thème', async () => {
    const response = page.waitForResponse(response => new URL(response.url()).pathname === apiPath(id, 'dashboard/') && response.request().method() === 'GET');
    await page.goto(root + '/tableau-de-bord');
    const data = await (await response).json() as { sections: { invoicing: { totals: { currency_code: string; net: string }[]; unpaid_count: number } } };
    expect(data.sections.invoicing.totals.find(row => row.currency_code === 'EUR')?.net).toMatch(/^96(?:\.0+)?$/); expect(data.sections.invoicing.unpaid_count).toBe(0);
    await expect(page.getByRole('table', { name: 'Montants mensuels exacts' })).toBeVisible(); await page.screenshot({ path: testInfo.outputPath('dashboard-desktop.png'), fullPage: true });
    await page.getByRole('button', { name: 'Activer le thème sombre', exact: true }).click(); await expect(page.locator('html')).toHaveClass(/dark/);
    await page.setViewportSize({ width: 390, height: 844 }); await page.screenshot({ path: testInfo.outputPath('dashboard-mobile-dark.png'), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    await page.getByRole('button', { name: 'Activer le thème clair', exact: true }).click(); await page.setViewportSize({ width: 1440, height: 1000 });
  });
  await test.step('deux entreprises et refus de document étranger', async () => {
    await page.goto('/administration/entreprise/nouvelle'); const other = await createCompany(page, 'E2E Autre société');
    await enable(page, other.id, 'contacts', 'Contacts');
    const foreign = await page.request.get(apiPath(other.id, `reference/partners/${contact.id}/`)); expect(foreign.status()).toBe(404);
    const list = await getJson<{ count: number }>(page, apiPath(other.id, 'reference/partners/')); expect(list.count).toBe(0);
    await page.getByLabel('Entreprise active', { exact: true }).selectOption(id); await expect(page).toHaveURL(new RegExp(id));
    await page.goto(root + '/contacts'); await expect(page.getByRole('link', { name: 'Contact E2E', exact: true })).toBeVisible();
  });
  await test.step('module désactivé et CSRF réel', async () => {
    await page.goto(root + '/modules'); const card = page.locator('.module-grid > section').filter({ has: page.getByRole('heading', { name: 'CRM', exact: true }) });
    await submit(page, apiPath(id, 'modules/crm/disable/'), card.getByRole('button', { name: 'Désactiver', exact: true }));
    await page.goto(root + '/crm'); await expect(page.getByRole('heading', { name: 'Module désactivé', exact: true })).toBeVisible();
    expect((await page.request.get(apiPath(id, 'crm/leads/'))).status()).toBe(403);
    expect((await page.request.post(apiPath(id, 'modules/crm/enable/'), { data: {} })).status()).toBe(403);
  });
  await test.step('déconnexion et reconnexion au compte réel', async () => {
    await page.getByRole('button', { name: 'Se déconnecter', exact: true }).click(); await expect(page).toHaveURL('/login');
    await page.getByLabel('E-mail', { exact: true }).fill(email); await page.getByLabel('Mot de passe', { exact: true }).fill(password);
    await submit(page, '/api/v1/auth/login/', page.getByRole('button', { name: 'Se connecter', exact: true }));
    await expect(page).toHaveURL(new RegExp(id));
  });
  expect(browserErrors).toEqual([]);
});

test('un autre compte ne peut pas atteindre les données de la première société', async ({ browser, page, baseURL }) => {
  page.on('dialog', dialog => dialog.accept());
  const owner = await signup(page, 'isolation-source'); await enable(page, owner.company.id, 'contacts', 'Contacts'); const contact = await partner(page, owner.company.id, 'Contact privé E2E');
  const context = await browser.newContext({ baseURL }); const outsiderPage = await context.newPage();
  try {
    const outsider = await signup(outsiderPage, 'isolation-cible'); await enable(outsiderPage, outsider.company.id, 'contacts', 'Contacts');
    expect((await outsiderPage.request.get(apiPath(owner.company.id, `reference/partners/${contact.id}/`))).status()).toBe(403);
    expect((await outsiderPage.request.get(apiPath(outsider.company.id, `reference/partners/${contact.id}/`))).status()).toBe(404);
    await outsiderPage.goto(companyPath(owner.company.id) + '/contacts'); await expect(outsiderPage.getByText('Accès interdit à cette entreprise ou permission insuffisante.')).toBeVisible();
  } finally { await context.close(); }
});
