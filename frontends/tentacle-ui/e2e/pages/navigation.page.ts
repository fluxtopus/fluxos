import { type Page, expect } from '@playwright/test';

export class NavigationPage {
  constructor(private page: Page) {}

  async expectSidebarVisible() {
    // At least 2 of the 4 main nav items should be visible
    const items = ['INBOX', 'TASKS', 'AUTOMATIONS', 'SETTINGS'];
    let visibleCount = 0;

    for (const item of items) {
      const locator = this.page.getByRole('link', { name: new RegExp(item, 'i') });
      if ((await locator.count()) > 0 && (await locator.first().isVisible())) {
        visibleCount++;
      }
    }

    expect(visibleCount).toBeGreaterThanOrEqual(2);
  }

  async navigateTo(section: string) {
    const upper = section.toUpperCase();
    await this.page
      .getByRole('link', { name: new RegExp(upper, 'i') })
      .first()
      .click();
    await this.page.waitForURL(`**/${section.toLowerCase()}**`, { timeout: 10000 });
  }

  async expectBranding() {
    await expect(this.page.getByText('FluxOS').first()).toBeVisible();
  }
}
