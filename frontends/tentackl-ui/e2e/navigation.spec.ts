import { test, expect } from '@playwright/test';
import { NavigationPage } from './pages/navigation.page';
import { TaskListPage } from './pages/tasks.page';

/**
 * Sidebar Navigation — Verifies navigating between sections.
 *
 * Ported from: tests/e2e/scenarios/browser/test_navigation.sh
 */
test.describe('Sidebar Navigation', () => {
  test('sidebar nav items visible', async ({ page }) => {
    const nav = new NavigationPage(page);
    await page.goto('/inbox');
    await nav.expectSidebarVisible();
  });

  test('navigate to TASKS', async ({ page }) => {
    const nav = new NavigationPage(page);
    const tasks = new TaskListPage(page);
    await page.goto('/inbox');
    await nav.navigateTo('tasks');
    await expect(page).toHaveURL(/\/tasks/);
    await tasks.expectLoaded();
  });

  test('navigate to INBOX', async ({ page }) => {
    const nav = new NavigationPage(page);
    await page.goto('/tasks');
    await nav.navigateTo('inbox');
    await expect(page).toHaveURL(/\/inbox/);
  });

  test('navigate to AUTOMATIONS', async ({ page }) => {
    const nav = new NavigationPage(page);
    await page.goto('/inbox');
    await nav.navigateTo('automations');
    await expect(page).toHaveURL(/\/automations/);
    await expect(
      page.getByRole('heading', { name: /automations/i }),
    ).toBeVisible();
  });

  test('navigate to SETTINGS', async ({ page }) => {
    const nav = new NavigationPage(page);
    await page.goto('/inbox');
    await nav.navigateTo('settings');
    await expect(page).toHaveURL(/\/settings/);
    await expect(
      page.getByRole('heading', { name: /settings/i }),
    ).toBeVisible();
  });

  test('navigate back to TASKS from settings', async ({ page }) => {
    const nav = new NavigationPage(page);
    const tasks = new TaskListPage(page);
    await page.goto('/settings');
    await nav.navigateTo('tasks');
    await tasks.expectLoaded();
  });

  test('AIOS branding visible throughout', async ({ page }) => {
    const nav = new NavigationPage(page);
    await page.goto('/inbox');
    await nav.expectBranding();
  });
});
