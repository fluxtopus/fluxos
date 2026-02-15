import { type Page, expect } from '@playwright/test';

export class AgentsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/agents');
  }

  async expectLoaded() {
    await expect(this.page.getByText('AGENTS', { exact: true }).first()).toBeVisible();
  }

  async expectCreateButton() {
    await expect(this.page.getByText('CREATE', { exact: true }).first()).toBeVisible();
  }

  async expectRefreshButton() {
    await expect(this.page.getByText('REFRESH', { exact: true }).first()).toBeVisible();
  }

  async expectStatsCards() {
    await expect(this.page.getByText('YOUR AGENTS')).toBeVisible();
  }

  async expectAgentListOrEmpty() {
    await expect(
      this.page
        .getByText('NAME', { exact: true })
        .or(this.page.getByText('No agents found'))
    ).toBeVisible();
  }
}
