import { test } from '@playwright/test';
import { AutomationsPage } from './pages/automations.page';

/**
 * Automations Page — Verifies the automations management page.
 *
 * Ported from: tests/e2e/scenarios/browser/test_automations_page.sh
 */
test.describe('Automations Page', () => {
  test('automations page loads with title', async ({ page }) => {
    const automations = new AutomationsPage(page);
    await automations.goto();
    await automations.expectLoaded();
  });

  test('automation content structure visible', async ({ page }) => {
    const automations = new AutomationsPage(page);
    await automations.goto();
    await automations.expectContent();
  });

  test('refresh button present', async ({ page }) => {
    const automations = new AutomationsPage(page);
    await automations.goto();
    await automations.expectRefreshButton();
  });

  test('automation cards or empty state', async ({ page }) => {
    const automations = new AutomationsPage(page);
    await automations.goto();
    await automations.expectCardsOrEmpty();
  });
});
