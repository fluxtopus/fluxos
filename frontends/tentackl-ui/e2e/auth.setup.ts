import { test as setup, expect } from '@playwright/test';

const authFile = 'e2e/.auth/admin.json';

setup('authenticate as admin', async ({ page }) => {
  await page.goto('/auth/login');

  await page.getByLabel(/email/i).fill('admin@fluxtopus.com');
  await page.getByLabel(/password/i).fill('AiosAdmin123!');
  await page.getByRole('button', { name: /sign in/i }).click();

  // Wait for redirect away from login
  await expect(page).not.toHaveURL(/\/auth\/login/);

  // Verify we're logged in by checking for sidebar nav
  await expect(
    page.getByRole('link', { name: /inbox/i }).first(),
  ).toBeVisible({ timeout: 10000 });

  await page.context().storageState({ path: authFile });
});
