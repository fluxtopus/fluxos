import { test, expect } from '@playwright/test';
import { NavigationPage } from './pages/navigation.page';

/**
 * Dark Mode Toggle — Verifies the dark mode toggle works.
 *
 * Ported from: tests/e2e/scenarios/browser/test_dark_mode.sh
 */
test.describe('Dark Mode Toggle', () => {
  test('toggle button present in light mode', async ({ page }) => {
    await page.goto('/inbox');
    await expect(
      page.getByRole('button', { name: /switch to dark mode/i }),
    ).toBeVisible();
  });

  test('switch to dark mode', async ({ page }) => {
    await page.goto('/inbox');
    await page
      .getByRole('button', { name: /switch to dark mode/i })
      .click();
    await expect(
      page.getByRole('button', { name: /switch to light mode/i }),
    ).toBeVisible();
  });

  test('switch back to light mode', async ({ page }) => {
    await page.goto('/inbox');

    // Toggle to dark
    await page
      .getByRole('button', { name: /switch to dark mode/i })
      .click();
    await expect(
      page.getByRole('button', { name: /switch to light mode/i }),
    ).toBeVisible();

    // Toggle back to light
    await page
      .getByRole('button', { name: /switch to light mode/i })
      .click();
    await expect(
      page.getByRole('button', { name: /switch to dark mode/i }),
    ).toBeVisible();
  });

  test('page still functional after toggle', async ({ page }) => {
    const nav = new NavigationPage(page);
    await page.goto('/inbox');

    // Toggle dark mode
    await page
      .getByRole('button', { name: /switch to dark mode/i })
      .click();

    // Nav should still work
    await nav.expectSidebarVisible();

    // Toggle back
    await page
      .getByRole('button', { name: /switch to light mode/i })
      .click();
  });
});
