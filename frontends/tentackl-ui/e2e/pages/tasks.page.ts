import { type Page, expect } from '@playwright/test';

export class TaskListPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/tasks');
  }

  async expectLoaded() {
    await expect(
      this.page.getByRole('heading', { name: 'My Tasks' }),
    ).toBeVisible();
  }

  async expectCreateButton() {
    await expect(this.page.getByText('CREATE', { exact: true })).toBeVisible();
  }

  async expectFilterChips() {
    await expect(this.page.getByText('All', { exact: true }).first()).toBeVisible();
  }

  async expectTaskVisible(goalFragment: string) {
    await expect(this.page.getByText(goalFragment).first()).toBeVisible();
  }
}

export class TaskCreationPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/tasks/new');
  }

  async expectLoaded() {
    await expect(
      this.page.getByText('What needs to get done'),
    ).toBeVisible();
  }

  async createTask(goal: string) {
    await this.page
      .getByPlaceholder('Describe your goal...')
      .or(this.page.getByRole('textbox'))
      .fill(goal);
    await this.page.keyboard.press('Enter');
    // Wait for redirect to task detail
    await expect(this.page).toHaveURL(/\/tasks\//, { timeout: 10000 });
  }

  async expectBackToTasksLink() {
    await expect(this.page.getByText('Back to tasks')).toBeVisible();
  }
}

export class TaskDetailPage {
  constructor(private page: Page) {}

  async expectLoaded() {
    await expect(this.page).toHaveURL(/\/tasks\//);
  }

  async expectGoalVisible(goalFragment: string) {
    await expect(this.page.getByText(goalFragment).first()).toBeVisible();
  }

  async expectStatusIndicator() {
    await expect(
      this.page.getByText(/planning|running|ready|completed|failed|steps/i).first(),
    ).toBeVisible();
  }

  async expectBackLink() {
    await expect(this.page.getByText('Back to tasks')).toBeVisible();
  }

  async expectTimestamp() {
    await expect(
      this.page.getByText(/created|ago|just now/i).first(),
    ).toBeVisible();
  }
}
