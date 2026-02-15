import { test } from '@playwright/test';
import { InboxPage } from './pages/inbox.page';

/**
 * Inbox Messaging — Verifies the inbox conversation flow.
 *
 * Ported from: tests/e2e/scenarios/browser/test_inbox_messaging.sh
 *
 * Each run sends a unique timestamped message. Messages accumulate
 * but don't interfere with each other.
 */
test.describe('Inbox Messaging', () => {
  const uniqueMsg = `E2E inbox test ${Date.now()}`;

  test('inbox page loads', async ({ page }) => {
    const inbox = new InboxPage(page);
    await inbox.goto();
    await inbox.expectLoaded();
  });

  test('conversation list visible', async ({ page }) => {
    const inbox = new InboxPage(page);
    await inbox.goto();
    await inbox.expectListContent();
  });

  test('start new conversation shows message input', async ({ page }) => {
    const inbox = new InboxPage(page);
    await inbox.goto();
    await inbox.startNewChat();
    await inbox.expectMessageInput();
  });

  test('send message and see conversation active', async ({ page }) => {
    const inbox = new InboxPage(page);
    await inbox.goto();
    await inbox.startNewChat();
    await inbox.sendMessage(uniqueMsg);
    await inbox.expectConversationActive();
  });
});
