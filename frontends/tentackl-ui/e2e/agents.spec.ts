import { test } from '@playwright/test';
import { AgentsPage } from './pages/agents.page';

/**
 * Agents Page — Verifies the agents management page structure.
 *
 * Ported from: tests/e2e/scenarios/browser/test_agents_page.sh
 */
test.describe('Agents Page', () => {
  test('agents page loads with title', async ({ page }) => {
    const agents = new AgentsPage(page);
    await agents.goto();
    await agents.expectLoaded();
  });

  test('CREATE button present', async ({ page }) => {
    const agents = new AgentsPage(page);
    await agents.goto();
    await agents.expectCreateButton();
  });

  test('REFRESH button present', async ({ page }) => {
    const agents = new AgentsPage(page);
    await agents.goto();
    await agents.expectRefreshButton();
  });

  test('stats cards visible', async ({ page }) => {
    const agents = new AgentsPage(page);
    await agents.goto();
    await agents.expectStatsCards();
  });

  test('agent list or empty state', async ({ page }) => {
    const agents = new AgentsPage(page);
    await agents.goto();
    await agents.expectAgentListOrEmpty();
  });
});
