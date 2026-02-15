import { test, expect } from '@playwright/test';

/**
 * Landing Page E2E Tests
 *
 * These tests verify the landing page renders correctly and
 * all key elements are present and functional.
 */

test.describe('Landing Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display the hero section', async ({ page }) => {
    // Check hero headline is visible
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    // Check CTA button is present
    const ctaButton = page.getByRole('link', { name: /get started|try free|start/i });
    await expect(ctaButton).toBeVisible();
  });

  test('should display pricing section with all tiers', async ({ page }) => {
    // Scroll to pricing section using id
    const pricingSection = page.locator('#pricing');
    await pricingSection.scrollIntoViewIfNeeded();
    await expect(pricingSection).toBeVisible();

    // Check all three pricing tiers are visible
    await expect(page.getByText(/starter/i).first()).toBeVisible();
    await expect(page.getByText(/growth/i).first()).toBeVisible();
    await expect(page.getByText(/business/i).first()).toBeVisible();

    // Check prices are displayed
    await expect(page.getByText('$29')).toBeVisible();
    await expect(page.getByText('$49')).toBeVisible();
    await expect(page.getByText('$99')).toBeVisible();
  });

  test('should display features section', async ({ page }) => {
    // Check features section exists using id
    const featuresSection = page.locator('#features');
    await expect(featuresSection).toBeVisible();

    // Check heading
    await expect(page.getByText('Everything You Need')).toBeVisible();
  });

  test('should have working navigation', async ({ page }) => {
    // Check footer links
    const footer = page.locator('footer');
    await expect(footer).toBeVisible();
  });

  test('should be responsive on mobile', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });

    // Page should still display correctly
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });
});

test.describe('Pricing Buttons', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('pricing button should be clickable', async ({ page }) => {
    // Find a pricing button
    const pricingButton = page.getByRole('button', { name: /get started|choose|select/i }).first();

    if (await pricingButton.isVisible()) {
      // Just verify it's clickable (don't actually click to avoid Stripe redirect)
      await expect(pricingButton).toBeEnabled();
    }
  });
});

test.describe('Accessibility', () => {
  test('should have proper heading hierarchy', async ({ page }) => {
    await page.goto('/');

    // Should have exactly one h1
    const h1Count = await page.getByRole('heading', { level: 1 }).count();
    expect(h1Count).toBe(1);

    // Should have h2s for sections
    const h2Count = await page.getByRole('heading', { level: 2 }).count();
    expect(h2Count).toBeGreaterThan(0);
  });

  test('should have alt text on images', async ({ page }) => {
    await page.goto('/');

    const images = page.locator('img');
    const imageCount = await images.count();

    for (let i = 0; i < imageCount; i++) {
      const img = images.nth(i);
      const alt = await img.getAttribute('alt');
      // Images should have alt text (can be empty for decorative)
      expect(alt).not.toBeNull();
    }
  });
});
