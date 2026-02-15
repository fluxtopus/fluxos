import { test, expect } from '@playwright/test';
import { TaskCreationPage, TaskListPage } from './pages/tasks.page';

/**
 * Task Creation — Verifies creating a new task via /tasks/new.
 *
 * Ported from: tests/e2e/scenarios/browser/test_task_creation.sh
 *
 * Each run creates a unique timestamped task. They accumulate
 * but don't interfere with each other.
 */
test.describe('Task Creation', () => {
  const uniqueGoal = `E2E browser test ${Date.now()} — summarize results`;

  test('new task page loads with heading', async ({ page }) => {
    const creation = new TaskCreationPage(page);
    await creation.goto();
    await creation.expectLoaded();
  });

  test('create task and redirect to detail', async ({ page }) => {
    const creation = new TaskCreationPage(page);
    await creation.goto();
    await creation.createTask(uniqueGoal);
    await expect(page).toHaveURL(/\/tasks\//);
  });

  test('created task appears in task list', async ({ page }) => {
    // First create a task
    const creation = new TaskCreationPage(page);
    await creation.goto();
    await creation.createTask(uniqueGoal);

    // Then check the list
    const list = new TaskListPage(page);
    await list.goto();
    await list.expectTaskVisible('E2E browser test');
  });

  test('back to tasks link on new page', async ({ page }) => {
    const creation = new TaskCreationPage(page);
    await creation.goto();
    await creation.expectBackToTasksLink();
  });
});
