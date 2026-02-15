import { type Page, expect } from '@playwright/test';

export class LoginPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto('/auth/login');
  }

  async expectLoaded() {
    await expect(
      this.page.getByRole('heading', { name: 'Welcome Back' }),
    ).toBeVisible();
    await expect(this.page.getByLabel(/email/i)).toBeVisible();
    await expect(this.page.getByLabel(/password/i)).toBeVisible();
  }

  async login(email: string, password: string) {
    await this.page.getByLabel(/email/i).fill(email);
    await this.page.getByLabel(/password/i).fill(password);
    await this.page.getByRole('button', { name: /sign in/i }).click();
    await expect(this.page).not.toHaveURL(/\/auth\/login/, { timeout: 10000 });
  }

  async expectLoggedIn() {
    await expect(
      this.page.getByRole('link', { name: /inbox/i }).first(),
    ).toBeVisible({ timeout: 10000 });
  }

  async logout() {
    // Open user dropdown
    await this.page
      .getByText('admin@fluxtopus.com')
      .or(this.page.getByRole('button', { name: /admin/i }))
      .first()
      .click();
    await this.page.waitForTimeout(500);

    // Click sign out
    await this.page
      .getByText('SIGN OUT', { exact: true })
      .or(this.page.getByText('Sign out', { exact: true }))
      .click();

    await expect(this.page).toHaveURL(/\/auth\/login/, { timeout: 10000 });
  }

  async expectSessionPersisted() {
    await this.page.reload();
    await this.expectLoggedIn();
  }
}
