import { test, expect, type Page, type Locator } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import path from 'node:path';

async function submit<T>(page: Page, pathname: string, button: Locator): Promise<T> {
  const [response] = await Promise.all([page.waitForResponse(row => new URL(row.url()).pathname === pathname && row.request().method() === 'POST', { timeout: 90_000 }), button.click()]);
  expect(response.ok(), await response.text()).toBeTruthy();
  return await response.json() as T;
}

test('logo réellement importé et console plateforme avec suspensions réversibles', async ({ page, browser, baseURL }, testInfo) => {
  const email = `qa-platform-${randomUUID()}@example.invalid`;
  await page.goto('/register');
  await page.getByLabel('Nom complet', { exact: true }).fill('Opérateur E2E logo');
  await page.getByLabel('E-mail', { exact: true }).fill(email);
  await page.getByLabel('Mot de passe', { exact: true }).fill('Qavelys-E2E!2026-Only');
  await submit(page, '/api/v1/auth/register/', page.getByRole('button', { name: 'Créer mon compte', exact: true }));
  const companyName = `E2E Logo ${randomUUID().slice(0, 8)}`;
  await page.getByLabel('Nom de l’entreprise', { exact: true }).fill(companyName);
  await page.getByLabel('Pays (code à 2 lettres)', { exact: true }).fill('FR');
  await page.getByLabel('Devise principale', { exact: true }).fill('EUR');
  const company = await submit<{ id: string }>(page, '/api/v1/companies/', page.getByRole('button', { name: 'Créer mon espace administrateur', exact: true }));
  const root = `/administration/entreprises/${company.id}`;
  await expect(page).toHaveURL(root);
  await page.goto(root + '/parametres');
  await page.getByLabel('Fichier du logo', { exact: true }).setInputFiles(path.resolve('..', '.local', 'e2e-runs', process.env.QAVELYS_E2E_RUN_ID!, 'logo-input.png'));
  const logo = await submit<{ logo_url: string }>(page, `/api/v1/companies/${company.id}/logo/`, page.getByRole('button', { name: 'Importer le logo', exact: true }));
  await expect(page.getByText('Logo enregistré.', { exact: true })).toBeVisible();
  const image = page.getByRole('img', { name: `Logo de ${companyName}`, exact: true });
  await expect(image).toHaveAttribute('src', logo.logo_url);
  await expect.poll(() => image.evaluate((element: HTMLImageElement) => element.complete && element.naturalWidth > 0)).toBe(true);
  const content = await page.request.get(logo.logo_url);
  expect(content.status()).toBe(200); expect(content.headers()['content-type']).toBe('image/png'); expect(content.headers()['cache-control']).toContain('no-store');
  const anonymous = await browser.newContext({ baseURL });
  try { expect((await anonymous.request.get(logo.logo_url)).status()).toBe(403); } finally { await anonymous.close(); }
  // Rôle opérateur accordé par la commande réelle, exclusivement dans la base E2E.
  expect(process.env.QAVELYS_E2E).toBe('1'); expect(process.env.POSTGRES_DB).toMatch(/^qavelys_e2e_/);
  await promisify(execFile)(path.resolve('..', '.venv', 'Scripts', 'python.exe'), [path.resolve('..', 'backend', 'manage.py'), 'grant_platform_admin', email], { timeout: 60_000, windowsHide: true });
  await page.goto('/plateforme');
  await expect(page.getByRole('heading', { name: 'Administration plateforme', exact: true })).toBeVisible();
  await page.getByLabel('Rechercher dans la plateforme', { exact: true }).fill(companyName);
  await page.getByRole('button', { name: `Suspendre ${companyName}`, exact: true }).click();
  await page.getByLabel('Motif du changement', { exact: true }).fill('Contrôle E2E de suspension');
  await submit(page, `/api/v1/platform/companies/${company.id}/suspend/`, page.getByRole('button', { name: 'Confirmer le changement', exact: true }));
  expect((await page.request.get(`/api/v1/companies/${company.id}/context/`)).status()).toBe(403);
  await page.getByRole('button', { name: `Réactiver ${companyName}`, exact: true }).click();
  await page.getByLabel('Motif du changement', { exact: true }).fill('Contrôle E2E de réactivation');
  await submit(page, `/api/v1/platform/companies/${company.id}/activate/`, page.getByRole('button', { name: 'Confirmer le changement', exact: true }));
  expect((await page.request.get(`/api/v1/companies/${company.id}/context/`)).status()).toBe(200);
  await page.getByRole('button', { name: 'Utilisateurs', exact: true }).click();
  await expect(page.getByRole('button', { name: `Désactiver ${email}`, exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Modules', exact: true }).click();
  await expect(page.getByRole('table', { name: 'Modules', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Journal plateforme', exact: true }).click();
  await expect(page.getByRole('cell', { name: 'Entreprise suspendue', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('plateforme-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: testInfo.outputPath('plateforme-mobile.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
