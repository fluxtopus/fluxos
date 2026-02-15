import { type Page, expect } from '@playwright/test';

export class SettingsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/settings');
  }

  async expectLoaded() {
    await expect(
      this.page.getByRole('heading', { name: /settings/i }).or(
        this.page.getByText('Settings', { exact: true }),
      ),
    ).toBeVisible();
  }

  async expectSubNav() {
    await expect(this.page.getByText('ACCOUNT', { exact: true })).toBeVisible();
    await expect(this.page.getByText('PREFERENCES', { exact: true })).toBeVisible();
    await expect(this.page.getByText('INTEGRATIONS', { exact: true })).toBeVisible();
  }

  async expectAccountTab() {
    await expect(this.page.getByText('Personal Info')).toBeVisible();
    await expect(this.page.getByText('FIRST NAME')).toBeVisible();
    await expect(this.page.getByText('LAST NAME')).toBeVisible();
    await expect(this.page.getByRole('button', { name: /save/i }).first()).toBeVisible();
  }

  async gotoPreferences() {
    await this.page.goto('/settings/preferences');
  }

  async expectPreferencesTab() {
    await expect(
      this.page.getByText(/learned from your decisions|preferences/i).first(),
    ).toBeVisible();
  }

  async gotoIntegrations() {
    await this.page.goto('/settings/integrations');
  }

  async expectIntegrationsTab() {
    await expect(
      this.page.getByText(/external service|integrations|discord|create/i).first(),
    ).toBeVisible();
  }

  async gotoTriggers() {
    await this.page.goto('/settings/triggers');
  }

  async expectTriggersTab() {
    await expect(
      this.page.getByText(/event triggers|triggers/i).first(),
    ).toBeVisible();
  }
}
