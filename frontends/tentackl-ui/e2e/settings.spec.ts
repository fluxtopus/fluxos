import { test } from '@playwright/test';
import { SettingsPage } from './pages/settings.page';

/**
 * Settings Page — Verifies the settings page structure and sub-navigation.
 *
 * Ported from: tests/e2e/scenarios/browser/test_settings_page.sh
 */
test.describe('Settings Page', () => {
  test('settings page loads with heading', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    await settings.expectLoaded();
  });

  test('settings sub-navigation visible', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    await settings.expectSubNav();
  });

  test('account tab shows personal info form', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.goto();
    await settings.expectAccountTab();
  });

  test('preferences tab shows learned preferences', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.gotoPreferences();
    await settings.expectPreferencesTab();
  });

  test('integrations tab shows external services', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.gotoIntegrations();
    await settings.expectIntegrationsTab();
  });

  test('triggers tab shows event triggers', async ({ page }) => {
    const settings = new SettingsPage(page);
    await settings.gotoTriggers();
    await settings.expectTriggersTab();
  });
});
