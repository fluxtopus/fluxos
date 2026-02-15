import { test, expect } from '@playwright/test';
import { LoginPage } from './pages/login.page';

/**
 * Login Flow — Verifies the complete login lifecycle.
 *
 * Ported from: tests/e2e/scenarios/browser/test_login_flow.sh
 *
 * This test uses its own auth (not the shared storageState) because
 * it needs to test the login/logout cycle from scratch.
 */
test.describe('Login Flow', () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test('login page renders with form fields', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.expectLoaded();
  });

  test('submit credentials and reach dashboard', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.login('admin@fluxtopus.com', 'AiosAdmin123!');
    await login.expectLoggedIn();
  });

  test('session persists across reload', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.login('admin@fluxtopus.com', 'AiosAdmin123!');
    await login.expectSessionPersisted();
  });

  test('logout returns to login page', async ({ page }) => {
    const login = new LoginPage(page);
    await login.goto();
    await login.login('admin@fluxtopus.com', 'AiosAdmin123!');
    await login.logout();
    await login.expectLoaded();
  });
});
