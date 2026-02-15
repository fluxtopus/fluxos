import { test } from '@playwright/test';
import { TaskCreationPage, TaskDetailPage } from './pages/tasks.page';

/**
 * Task Detail — Verifies the task detail view after creation.
 *
 * Ported from: tests/e2e/scenarios/browser/test_task_detail.sh
 */
test.describe('Task Detail', () => {
  const uniqueGoal = `E2E detail test ${Date.now()} — verify task page`;

  test('create task and land on detail page', async ({ page }) => {
    const creation = new TaskCreationPage(page);
    const detail = new TaskDetailPage(page);
    await creation.goto();
    await creation.createTask(uniqueGoal);
    await detail.expectLoaded();
  });

  test('task goal visible as heading', async ({ page }) => {
    const creation = new TaskCreationPage(page);
    const detail = new TaskDetailPage(page);
    await creation.goto();
    await creation.createTask(uniqueGoal);
    await detail.expectGoalVisible('E2E detail test');
  });

  test('status indicator present', async ({ page }) => {
    const creation = new TaskCreationPage(page);
    const detail = new TaskDetailPage(page);
    await creation.goto();
    await creation.createTask(uniqueGoal);
    await detail.expectStatusIndicator();
  });

  test('back to tasks link visible', async ({ page }) => {
    const creation = new TaskCreationPage(page);
    const detail = new TaskDetailPage(page);
    await creation.goto();
    await creation.createTask(uniqueGoal);
    await detail.expectBackLink();
  });

  test('creation timestamp shown', async ({ page }) => {
    const creation = new TaskCreationPage(page);
    const detail = new TaskDetailPage(page);
    await creation.goto();
    await creation.createTask(uniqueGoal);
    await detail.expectTimestamp();
  });
});
