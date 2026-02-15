import { useCallback, useRef, useState } from 'react';
import type {
  PlanningEventType,
  PlanningPhaseItem,
  PlanningProgress,
} from '../types/task';
import type { PlanningEventData } from '../services/taskApi';

const PLANNING_PHASES: { type: PlanningEventType; label: string }[] = [
  { type: 'task.planning.started', label: 'Reading your request' },
  { type: 'task.planning.intent_detected', label: 'Figuring out the best approach' },
  { type: 'task.planning.spec_match', label: 'Looking for shortcuts' },
  { type: 'task.planning.llm_started', label: 'Building your plan' },
  { type: 'task.planning.steps_generated', label: 'Plan drafted' },
  { type: 'task.planning.risk_detection', label: 'Final checks' },
  { type: 'task.planning.completed', label: 'Ready to go' },
];

function buildInitialPhases(): PlanningPhaseItem[] {
  return PLANNING_PHASES.map((p) => ({
    type: p.type,
    label: p.label,
    status: 'pending',
  }));
}

function buildInitialProgress(): PlanningProgress {
  return {
    phases: buildInitialPhases(),
    currentPhase: null,
    stepNames: null,
    stepCount: null,
    error: null,
    isComplete: false,
    isFailed: false,
  };
}

export function usePlanningProgress() {
  const [progress, setProgress] = useState<PlanningProgress>(buildInitialProgress);
  const seenEvents = useRef(new Set<PlanningEventType>());

  const handlePlanningEvent = useCallback((event: PlanningEventData) => {
    const eventType = event.type;

    // Ignore duplicates from stream replay
    if (seenEvents.current.has(eventType)) return;
    seenEvents.current.add(eventType);

    setProgress((prev) => {
      const next = { ...prev, phases: [...prev.phases] };

      // Handle failure
      if (eventType === 'task.planning.failed') {
        const error = (event.data.error as string) || 'Planning failed';
        next.error = error;
        next.isFailed = true;
        next.currentPhase = eventType;
        // Mark all pending phases as failed
        next.phases = next.phases.map((p) =>
          p.status === 'active' ? { ...p, status: 'failed' } : p
        );
        return next;
      }

      // Handle completion
      if (eventType === 'task.planning.completed') {
        next.isComplete = true;
        next.currentPhase = eventType;
        // Mark all remaining pending/active as done
        next.phases = next.phases.map((p) =>
          p.status === 'pending' || p.status === 'active'
            ? { ...p, status: 'done' }
            : p
        );
        return next;
      }

      // Handle fast_path — skip ahead to completion-like state
      if (eventType === 'task.planning.fast_path') {
        next.currentPhase = eventType;
        // Mark all phases as done
        next.phases = next.phases.map((p) => ({ ...p, status: 'done' }));
        next.isComplete = true;
        return next;
      }

      // Handle retry (special — update detail on llm_started)
      if (eventType === 'task.planning.llm_retry') {
        const attempt = event.data.attempt as number;
        const maxRetries = event.data.max_retries as number;
        next.phases = next.phases.map((p) =>
          p.type === 'task.planning.llm_started'
            ? { ...p, detail: `Retry ${attempt}/${maxRetries}` }
            : p
        );
        return next;
      }

      // Extract step info from steps_generated
      if (eventType === 'task.planning.steps_generated') {
        next.stepNames = (event.data.step_names as string[]) || null;
        next.stepCount = (event.data.step_count as number) || null;
      }

      // Extract detail from intent_detected
      if (eventType === 'task.planning.intent_detected') {
        const detail = event.data.detail as string | undefined;
        if (detail) {
          const phaseIdx = next.phases.findIndex((p) => p.type === eventType);
          if (phaseIdx >= 0) {
            next.phases[phaseIdx] = { ...next.phases[phaseIdx], detail };
          }
        }
      }

      // Extract detail from spec_match
      if (eventType === 'task.planning.spec_match') {
        const confidence = event.data.confidence as number | undefined;
        if (confidence !== undefined) {
          const phaseIdx = next.phases.findIndex((p) => p.type === eventType);
          if (phaseIdx >= 0) {
            next.phases[phaseIdx] = {
              ...next.phases[phaseIdx],
              detail: `${Math.round(confidence * 100)}% match`,
            };
          }
        }
      }

      // Update phase statuses: mark this phase active, mark all prior as done
      next.currentPhase = eventType;
      const currentIdx = next.phases.findIndex((p) => p.type === eventType);
      if (currentIdx >= 0) {
        next.phases = next.phases.map((p, i) => {
          if (i < currentIdx && p.status !== 'done') return { ...p, status: 'done' };
          if (i === currentIdx) return { ...p, status: 'active' };
          return p;
        });
      }

      return next;
    });
  }, []);

  const reset = useCallback(() => {
    seenEvents.current.clear();
    setProgress(buildInitialProgress());
  }, []);

  return { progress, handlePlanningEvent, reset };
}
