'use client';

import { formatDistanceToNow } from 'date-fns';
import {
  PlayIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  ArrowPathIcon,
  BoltIcon,
} from '@heroicons/react/24/outline';
import type { ActivityItem } from '../../types/task';

interface ActivityFeedProps {
  activities: ActivityItem[];
  maxItems?: number;
}

const activityConfig: Record<ActivityItem['type'], {
  icon: typeof PlayIcon;
  className: string;
}> = {
  started: {
    icon: PlayIcon,
    className: 'text-[oklch(0.65_0.25_180)] bg-[oklch(0.65_0.25_180/0.1)]',
  },
  progress: {
    icon: ArrowPathIcon,
    className: 'text-[oklch(0.65_0.25_180)] bg-[oklch(0.65_0.25_180/0.1)]',
  },
  completed: {
    icon: CheckCircleIcon,
    className: 'text-[oklch(0.78_0.22_150)] bg-[oklch(0.7_0.2_150/0.1)]',
  },
  decision: {
    icon: ClockIcon,
    className: 'text-[oklch(0.7_0.2_60)] bg-[oklch(0.7_0.2_60/0.1)]',
  },
  error: {
    icon: ExclamationTriangleIcon,
    className: 'text-[oklch(0.65_0.25_27)] bg-[oklch(0.65_0.25_27/0.1)]',
  },
  recovery: {
    icon: BoltIcon,
    className: 'text-[oklch(0.7_0.2_60)] bg-[oklch(0.7_0.2_60/0.1)]',
  },
};

/**
 * ActivityFeed - Shows a timeline of high-level events.
 * Not execution logs. User-facing activity that matters.
 */
export function ActivityFeed({ activities, maxItems = 20 }: ActivityFeedProps) {
  const displayedActivities = activities.slice(-maxItems).reverse();

  if (activities.length === 0) {
    return (
      <div className="text-center py-8 text-[var(--muted-foreground)] text-sm">
        No activity yet
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {displayedActivities.map((activity, idx) => {
        const config = activityConfig[activity.type];
        const Icon = config.icon;
        const isLatest = idx === 0;

        return (
          <div
            key={activity.id}
            className={`flex items-start gap-3 ${isLatest ? '' : 'opacity-70'}`}
          >
            <div className={`
              flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center
              ${config.className}
            `}>
              <Icon className={`w-4 h-4 ${activity.type === 'progress' ? 'animate-spin' : ''}`} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-[var(--foreground)] text-body">
                {activity.message}
              </p>
              <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                {formatDistanceToNow(new Date(activity.timestamp), { addSuffix: true })}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
