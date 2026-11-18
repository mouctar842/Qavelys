import { test, expect, type Page, type Locator } from '@playwright/test';
import { randomUUID } from 'node:crypto';

async function submit(page: Page, path: string, button: Locator) {
  const [response] = await Promise.all([page.waitForResponse(row => new URL(row.url()).pathname === path && row.request().method() === 'POST'), button.click()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return await response.json() as { id: string; reference: string };
}
async function post(page: Page, path: string, body: unknown) {
  const csrf = await (await page.request.get('/api/v1/auth/csrf/')).json() as { csrfToken: string };
  const response = await page.request.post(path, { data: body, headers: { 'X-CSRFToken': csrf.csrfToken } });
  expect(response.ok(), await response.text()).toBeTruthy(); return await response.json() as { id: string };
}

test('client et fournisseur partagent une identité avec activités et documents préremplis', async ({ page }, info) => {
  page.on('dialog', dialog => void dialog.accept()); const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('/register');
  await page.getByLabel('Nom complet', { exact: true }).fill('Administrateur E2E tiers');
  await page.getByLabel('E-mail', { exact: true }).fill(`qa-partners-${randomUUID()}@example.invalid`);
  await page.getByLabel('Mot de passe', { exact: true }).fill('Qavelys-E2E!2026-Only');
  await page.getByRole('button', { name: 'Créer mon compte', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Créer une entreprise', exact: true })).toBeVisible();
  await page.getByLabel('Nom de l’entreprise', { exact: true }).fill('E2E Relations commerciales');
  await page.getByLabel('Pays (code à 2 lettres)', { exact: true }).fill('FR');
  await page.getByLabel('Devise principale', { exact: true }).fill('EUR');
  await page.getByRole('button', { name: 'Créer mon espace administrateur', exact: true }).click();
  await expect(page).toHaveURL(/\/administration\/entreprises\/[0-9a-f-]+$/);
  const base = new URL(page.url()).pathname; const id = base.split('/').at(-1)!; const api = `/api/v1/companies/${id}/`;
  for (const name of ['Achats', 'Facturation']) {
    await page.goto(`${base}/modules`);
    const card = page.locator('.module-grid > section').filter({ has: page.getByRole('heading', { name, exact: true }) });
    await card.getByRole('button', { name: 'Activer avec ses dépendances', exact: true }).click();
    await expect(card.getByRole('button', { name: 'Désactiver', exact: true })).toBeVisible();
  }
  await page.goto(`${base}/clients/nouveau`);
  await page.getByLabel('Nom', { exact: true }).fill('Partenaire E2E partagé');
  await page.getByLabel('Référence client', { exact: true }).fill('CLI-E2E');
  await page.getByLabel('Adresse de livraison', { exact: true }).fill('Dépôt client Conakry');
  await page.getByLabel('Notes commerciales', { exact: true }).fill('Appeler avant la livraison.');
  const partner = await submit(page, api + 'reference/partners/', page.getByRole('button', { name: 'Enregistrer le client', exact: true }));
  await expect(page.getByRole('heading', { name: 'Partenaire E2E partagé', exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Créer une facture client', exact: true }).click();
  await expect(page.getByLabel('Client facturé', { exact: true })).toHaveValue(partner.id);
  await page.getByLabel('Description 1', { exact: true }).fill('Prestation commerciale réelle E2E');
  await page.getByLabel('Prix unitaire 1', { exact: true }).fill('100');
  const invoice = await submit(page, api + 'invoicing/invoices/', page.getByRole('button', { name: 'Créer le brouillon de facture', exact: true }));
  await submit(page, api + `invoicing/invoices/${invoice.id}/validate/`, page.getByRole('button', { name: 'Valider le document', exact: true }));
  await page.goto(`${base}/clients/${partner.id}`);
  await expect(page.getByRole('link', { name: invoice.reference, exact: true })).toBeVisible();
  await expect(page.getByText('Créances clients (EUR)', { exact: true })).toBeVisible();
  await expect(page.locator('.partner-balances dd').first()).toHaveText('100');
  await page.goto(`${base}/fournisseurs/nouveau`);
  await page.getByLabel('Rechercher dans tous les tiers', { exact: true }).fill('Partenaire E2E');
  await page.getByRole('button', { name: 'Utiliser ce tiers · Partenaire E2E partagé', exact: true }).click();
  await expect(page).toHaveURL(`${base}/fournisseurs/${partner.id}`);
  await page.getByRole('link', { name: 'Modifier le fournisseur', exact: true }).click();
  await page.getByLabel('Référence chez le fournisseur', { exact: true }).fill('SUP-E2E');
  await page.getByLabel('Instructions d’approvisionnement', { exact: true }).fill('Réceptions le matin.');
  await submit(page, api + `reference/partners/${partner.id}/update/`, page.getByRole('button', { name: 'Enregistrer le fournisseur', exact: true }));
  await page.getByRole('link', { name: 'Ouvrir le profil client', exact: true }).click();
  await expect(page.getByText('Dépôt client Conakry', { exact: true })).toBeVisible();
  await expect(page.getByText('Appeler avant la livraison.', { exact: true })).toBeVisible();
  const all = await (await page.request.get(api + 'reference/partners/?kind=all')).json() as { count: number; results: { is_customer: boolean; is_supplier: boolean }[] };
  expect(all.count).toBe(1); expect(all.results[0]).toMatchObject({ is_customer: true, is_supplier: true });
  const units = await (await page.request.get(api + 'reference/units/')).json() as { id: string; symbol: string }[];
  const product = await post(page, api + 'reference/products/', { name: 'Approvisionnement E2E', sku: 'SUP-E2E', type: 'stockable', unit_id: units.find(row => row.symbol === 'u')!.id, sale_price: '70', cost_price: '50' });
  await page.goto(`${base}/fournisseurs/${partner.id}`);
  await page.getByRole('link', { name: 'Créer une commande fournisseur', exact: true }).click();
  await expect(page.getByLabel('Fournisseur', { exact: true })).toHaveValue(partner.id);
  await page.getByLabel('Produit 1', { exact: true }).selectOption(product.id);
  await page.getByLabel('Quantité 1', { exact: true }).fill('2');
  const purchase = await submit(page, api + 'purchases/orders/', page.getByRole('button', { name: 'Enregistrer le brouillon', exact: true }));
  await page.goto(`${base}/fournisseurs/${partner.id}`);
  await expect(page.getByRole('link', { name: purchase.reference, exact: true })).toBeVisible();
  await page.screenshot({ path: info.outputPath('fournisseur-activite.png'), fullPage: true });
  await page.getByRole('link', { name: 'Ouvrir le profil client', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('heading', { name: 'Partenaire E2E partagé', exact: true })).toBeVisible();
  await expect(page.getByText('Créances clients (EUR)', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Activer le thème sombre', exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await page.screenshot({ path: info.outputPath('client-mobile-sombre.png'), fullPage: true });
  expect(errors).toEqual([]);
});
