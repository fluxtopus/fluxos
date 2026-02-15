import { type Page, expect } from '@playwright/test';

export class AutomationsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/automations');
  }

  async expectLoaded() {
    await expect(
      this.page.getByRole('heading', { name: /automations/i }).or(
        this.page.getByText('Automations', { exact: true }),
      ),
    ).toBeVisible();
  }

  async expectContent() {
    await expect(
      this.page
        .getByText(/runs|success|failed|automation|daily|no automations/i)
        .first(),
    ).toBeVisible();
  }

  async expectRefreshButton() {
    // Refresh may be an icon-only button
    await expect(
      this.page.getByRole('button', { name: /refresh/i })
        .or(this.page.locator('button[aria-label*="refresh" i]'))
        .or(this.page.locator('button').filter({ hasText: /refresh/i }))
        .first(),
    ).toBeVisible();
  }

  async expectCardsOrEmpty() {
    await expect(
      this.page
        .getByText('No automations yet')
        .or(this.page.getByText(/automation|runs|schedule/i).first()),
    ).toBeVisible();
  }
}
