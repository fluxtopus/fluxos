'use client';

import { use } from 'react';
import { TaskDetail } from '../../../../components/Task/TaskDetail';

interface PageProps {
  params: Promise<{ taskId: string }>;
}

/**
 * Task detail page.
 * Shows the full view of a single task with live updates.
 */
export default function TaskPage({ params }: PageProps) {
  const { taskId } = use(params);

  return <TaskDetail taskId={taskId} />;
}
