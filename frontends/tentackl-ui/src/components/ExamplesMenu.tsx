import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { 
  PlayIcon,
  CodeBracketIcon,
  ChevronRightIcon,
  BeakerIcon,
  CpuChipIcon,
  GlobeAltIcon,
  ExclamationTriangleIcon,
  CurrencyDollarIcon,
  LightBulbIcon,
  RocketLaunchIcon,
  ComputerDesktopIcon,
  ChatBubbleLeftRightIcon
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import api from '../services/api';
import { useWorkflowStore } from '../store/workflowStore';

interface Example {
  id: string;
  name: string;
  description: string;
  icon: React.ElementType;
  script: string;
}

const examples: Example[] = [
  {
    id: 'viz',
    name: 'Visualization Demo',
    description: 'Simple workflow with real-time progress updates',
    icon: BeakerIcon,
    script: 'visualization_demo.py'
  },
  {
    id: '1',
    name: 'Simple Data Processing',
    description: 'Basic 3-stage sequential pipeline with CSV processing',
    icon: CodeBracketIcon,
    script: 'run_example.py'
  },
  {
    id: '2',
    name: 'Parallel Web Scraping',
    description: 'Concurrent scraping with shared resources',
    icon: GlobeAltIcon,
    script: 'run_example.py'
  },
  {
    id: '3',
    name: 'ML Training Pipeline',
    description: 'Resource-intensive ML workflow with GPU support',
    icon: CpuChipIcon,
    script: 'run_example.py'
  },
  {
    id: '4',
    name: 'Error Handling & Recovery',
    description: 'Resilient patterns with retries and fallbacks',
    icon: ExclamationTriangleIcon,
    script: 'run_example.py'
  },
  {
    id: 'budget',
    name: 'Budget & Versioning',
    description: 'Cost control and template version management',
    icon: CurrencyDollarIcon,
    script: 'budget_and_versioning_example.py'
  },
  {
    id: 'simple',
    name: 'Simple LLM Demo',
    description: 'Basic LLM agent demonstration',
    icon: LightBulbIcon,
    script: 'simple_llm_demo.py'
  },
  {
    id: 'multi',
    name: 'Multi-LLM Demo',
    description: 'Multiple LLM providers working together',
    icon: BeakerIcon,
    script: 'multi_llm_demo.py'
  },
  {
    id: 'real',
    name: 'Real World Demo',
    description: 'Complete end-to-end application workflow',
    icon: RocketLaunchIcon,
    script: 'real_world_demo.py'
  },
  {
    id: 'browser',
    name: 'Web Browser Workflow',
    description: 'AI-powered web scraping and analysis workflow',
    icon: ComputerDesktopIcon,
    script: 'browser_workflow_demo.py'
  },
  {
    id: 'orchestrator',
    name: 'Event Bus Orchestrator',
    description: 'Interactive chat with workflow orchestrator through event bus',
    icon: ChatBubbleLeftRightIcon,
    script: 'event_bus_orchestrator_demo.py'
  }
];

interface ExamplesMenuProps {
  onWorkflowCreated?: () => void;
}

export const ExamplesMenu: React.FC<ExamplesMenuProps> = ({ onWorkflowCreated }) => {
  const [runningExample, setRunningExample] = useState<string | null>(null);
  const [expandedExample, setExpandedExample] = useState<string | null>(null);
  const { selectWorkflow, fetchWorkflows } = useWorkflowStore();

  const runExample = async (example: Example) => {
    try {
      setRunningExample(example.id);
      toast.loading(`Running ${example.name}...`, { id: example.id });

      // Call the API to run the example
      const response = await api.post('/api/examples/run', {
        script: example.script,
        example_id: example.id
      });

      if (response.data.success) {
        toast.success(`${example.name} completed successfully!`, { id: example.id });
        
        // If a workflow was created, refresh the list and select it
        if (response.data.workflow_id) {
          await fetchWorkflows();
          await selectWorkflow(response.data.workflow_id);
          // Switch to workflows tab
          onWorkflowCreated?.();
        }
      } else {
        toast.error(`Failed to run ${example.name}: ${response.data.error}`, { id: example.id });
      }
    } catch (error: any) {
      console.error('Error running example:', error);
      toast.error(`Error: ${error.message || 'Failed to run example'}`, { id: example.id });
    } finally {
      setRunningExample(null);
    }
  };

  return (
    <div className="p-4">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
        Examples
      </h2>
      <div className="space-y-2">
        {examples.map((example) => {
          const Icon = example.icon;
          const isRunning = runningExample === example.id;
          const isExpanded = expandedExample === example.id;

          return (
            <motion.div
              key={example.id}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 overflow-hidden rounded-md"
            >
              <div
                className="p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                onClick={() => setExpandedExample(isExpanded ? null : example.id)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <Icon className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                    <div>
                      <h3 className="text-sm font-medium text-gray-900 dark:text-white">
                        {example.name}
                      </h3>
                    </div>
                  </div>
                  <ChevronRightIcon
                    className={`w-4 h-4 text-gray-400 dark:text-gray-500 transition-transform ${
                      isExpanded ? 'rotate-90' : ''
                    }`}
                  />
                </div>
              </div>

              {isExpanded && (
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: 'auto' }}
                  exit={{ height: 0 }}
                  className="border-t border-gray-200 dark:border-gray-600"
                >
                  <div className="p-4 bg-gray-50 dark:bg-gray-800">
                    <p className="text-sm text-gray-600 dark:text-gray-300 mb-3">
                      {example.description}
                    </p>
                    <button
                      onClick={() => runExample(example)}
                      disabled={isRunning}
                      className={`flex items-center space-x-2 px-4 py-2 text-sm font-medium transition-all rounded-md border ${
                        isRunning
                          ? 'bg-gray-100 dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-400 dark:text-gray-500 cursor-not-allowed'
                          : 'bg-blue-50 dark:bg-blue-900/30 border-blue-500 dark:border-blue-500 text-blue-700 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/40'
                      }`}
                    >
                      {isRunning ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-2 border-gray-300 dark:border-gray-500 border-t-gray-600 dark:border-t-blue-400"></div>
                          <span>Running...</span>
                        </>
                      ) : (
                        <>
                          <PlayIcon className="w-4 h-4" />
                          <span>Run Example</span>
                        </>
                      )}
                    </button>
                  </div>
                </motion.div>
              )}
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};