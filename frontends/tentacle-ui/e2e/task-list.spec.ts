import { test } from '@playwright/test';
import { TaskListPage } from './pages/tasks.page';
import { NavigationPage } from './pages/navigation.page';

/**
 * Task List Page — Verifies the task list page structure.
 *
 * Ported from: tests/e2e/scenarios/browser/test_task_list.sh
 */
test.describe('Task List Page', () => {
  test('tasks page loads with My Tasks title', async ({ page }) => {
    const tasks = new TaskListPage(page);
    await tasks.goto();
    await tasks.expectLoaded();
  });

  test('CREATE button is present', async ({ page }) => {
    const tasks = new TaskListPage(page);
    await tasks.goto();
    await tasks.expectCreateButton();
  });

  test('filter chips are visible', async ({ page }) => {
    const tasks = new TaskListPage(page);
    await tasks.goto();
    await tasks.expectFilterChips();
  });

  test('sidebar navigation alongside tasks', async ({ page }) => {
    const tasks = new TaskListPage(page);
    const nav = new NavigationPage(page);
    await tasks.goto();
    await nav.expectSidebarVisible();
  });

  test('FluxOS branding in navbar', async ({ page }) => {
    const tasks = new TaskListPage(page);
    const nav = new NavigationPage(page);
    await tasks.goto();
    await nav.expectBranding();
  });
});
