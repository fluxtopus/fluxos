import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import * as Dialog from '@radix-ui/react-dialog';
import * as Select from '@radix-ui/react-select';
import * as Tabs from '@radix-ui/react-tabs';
import * as Checkbox from '@radix-ui/react-checkbox';
import * as AlertDialog from '@radix-ui/react-alert-dialog';
import { clsx } from 'clsx';
import yaml from 'js-yaml';
import {
  PlayIcon,
  StopIcon,
  TrashIcon,
  ArrowUpTrayIcon,
  CodeBracketIcon,
  ChartBarIcon,
  ShieldCheckIcon,
  CpuChipIcon,
  RectangleGroupIcon,
  XMarkIcon,
  CheckIcon,
  ChevronDownIcon,
} from '@heroicons/react/24/outline';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { tomorrow } from 'react-syntax-highlighter/dist/esm/styles/prism';
import api from '../../services/api';

interface ConfigurableAgentPanelProps {
  apiBaseUrl?: string;
}

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

interface Agent {
  agent_id: string;
  config_name: string;
  config_version: string;
  state: string;
  capabilities: string[];
  execution_count: number;
  created_at: string;
  parent_id?: string;
}

interface BudgetUsage {
  resource_type: string;
  current: number;
  limit: number;
  percentage: number;
}

const ConfigurableAgentPanel: React.FC<ConfigurableAgentPanelProps> = ({
  apiBaseUrl = '/api/v1/configurable-agents',
}) => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // Create agent dialog
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [configYaml, setConfigYaml] = useState('');
  const [enableBudget, setEnableBudget] = useState(true);
  const [enableState, setEnableState] = useState(true);
  
  // Execute task dialog
  const [executeDialogOpen, setExecuteDialogOpen] = useState(false);
  const [taskJson, setTaskJson] = useState('');
  const [executionResult, setExecutionResult] = useState<any>(null);
  
  // Delete confirmation
  const [deleteAgentId, setDeleteAgentId] = useState<string | null>(null);
  
  // Agent details
  const [agentState, setAgentState] = useState<any>(null);
  const [agentBudget, setAgentBudget] = useState<BudgetUsage[]>([]);
  // Workflow Runner form
  const [runnerSpecPath, setRunnerSpecPath] = useState('src/workflows/weather_orchestrator.yaml');
  const [runnerEventJson, setRunnerEventJson] = useState('{"event_type":"weather.update","location":"Porto","precipitation_probability":85,"severity":"high","affected_hours":[18,19]}');
  const [runnerLoading, setRunnerLoading] = useState(false);
  const [runnerError, setRunnerError] = useState<string | null>(null);
  const [runnerSuccess, setRunnerSuccess] = useState<string | null>(null);

  // Sample configurations
  const sampleConfigs = {
    dataAnalyzer: `name: data-analyzer
type: analyzer
version: 1.0.0
description: Analyzes data and provides insights

capabilities:
  - tool: data_transform
    config:
      operations: ["filter", "aggregate"]
  - tool: validator

prompt_template: |
  Analyze the following data:
  Type: {data_type}
  Content: {content}
  
  Provide analysis in JSON format.

execution_strategy: sequential

state_schema:
  required: ["data_type", "content"]
  output: ["analysis", "confidence"]

resources:
  model: gpt-3.5-turbo
  max_tokens: 1000
  timeout: 60

success_metrics:
  - metric: confidence
    threshold: 0.7
    operator: gte`,
    
    codeReviewer: `name: code-reviewer
type: validator
version: 1.0.0
description: Reviews code for quality

capabilities:
  - tool: file_read
    sandbox: true
  - tool: validator

prompt_template: |
  Review the code:
  {code}
  
  Provide review in JSON format.

execution_strategy: sequential

state_schema:
  required: ["language", "code"]
  output: ["issues", "score"]

resources:
  model: gpt-4
  max_tokens: 2000

success_metrics:
  - metric: score
    threshold: 80
    operator: gte`,
  };

  useEffect(() => {
    loadAgents();
  }, []);

  useEffect(() => {
    if (selectedAgent) {
      loadAgentDetails(selectedAgent.agent_id);
    }
  }, [selectedAgent]);

  const loadAgents = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/agents/registry`);
      if (!response.ok) {
        throw new Error(`Failed to fetch agents: ${response.statusText}`);
      }

      const data = await response.json();

      // Transform API response to match Agent interface
      const transformedAgents: Agent[] = data.agents.map((apiAgent: any) => ({
        agent_id: apiAgent.id,
        config_name: apiAgent.name,
        config_version: apiAgent.version,
        state: apiAgent.is_active ? 'idle' : 'inactive',
        capabilities: apiAgent.tags || [],
        execution_count: apiAgent.usage_count || 0,
        created_at: apiAgent.created_at,
      }));

      setAgents(transformedAgents);
    } catch (err) {
      console.error('Error loading agents:', err);
      setError('Failed to load agents');
    }
  };

  const startWorkflowRunner = async () => {
    setRunnerLoading(true);
    setRunnerError(null);
    setRunnerSuccess(null);
    try {
      let data: any = {};
      try { data = JSON.parse(runnerEventJson); } catch { throw new Error('Invalid event JSON'); }
      const res = await api.post('/api/workflows/runner/start', { spec_path: runnerSpecPath, event_type: data.event_type || 'runner.start', data });
      const body = res.data;
      setRunnerSuccess(`Started workflow ${body.workflow_id} (status=${body.status})`);
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || String(e);
      setRunnerError(msg);
    } finally {
      setRunnerLoading(false);
    }
  };

  const loadAgentDetails = async (agentId: string) => {
    try {
      // Mock agent state
      setAgentState({
        data_type: 'sales_metrics',
        content: 'Q4 data',
        analysis: 'Positive growth trend',
        confidence: 0.85,
      });

      // Mock budget usage
      setAgentBudget([
        { resource_type: 'llm_calls', current: 5, limit: 100, percentage: 5 },
        { resource_type: 'llm_tokens', current: 2500, limit: 10000, percentage: 25 },
        { resource_type: 'llm_cost', current: 0.05, limit: 1.0, percentage: 5 },
      ]);
    } catch (err) {
      setError('Failed to load agent details');
    }
  };

  const createAgent = async () => {
    setLoading(true);
    setError(null);

    try {
      // Parse YAML to get agent name
      const config = yaml.load(configYaml) as any;

      const response = await fetch(`${API_BASE_URL}/api/agents/registry`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: config.name || 'unnamed-agent',
          yaml_content: configYaml,
          description: config.description,
          version: config.version,
          tags: config.capabilities?.map((c: any) => typeof c === 'string' ? c : c.tool) || [],
          category: config.type || 'custom',
          created_by: 'ui',
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to create agent');
      }

      const result = await response.json();
      setSuccess(result.message || 'Agent created successfully!');
      setCreateDialogOpen(false);
      setConfigYaml('');

      // Reload agents list
      await loadAgents();
    } catch (err: any) {
      if (err.name === 'YAMLException') {
        setError(`Invalid YAML: ${err.message}`);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  };

  const executeTask = async () => {
    if (!selectedAgent) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const task = JSON.parse(taskJson);
      
      const response = await fetch(`${apiBaseUrl}/${selectedAgent.agent_id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task }),
      });

      if (!response.ok) throw new Error('Failed to execute task');
      
      const result = await response.json();
      setExecutionResult(result);
      setSuccess('Task executed successfully!');
      
      // Reload agent details
      loadAgentDetails(selectedAgent.agent_id);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const deleteAgent = async (agentId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/agents/registry/${agentId}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Deleted from UI' }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to delete agent');
      }

      setAgents(agents.filter(a => a.agent_id !== agentId));
      if (selectedAgent?.agent_id === agentId) {
        setSelectedAgent(null);
      }
      setSuccess('Agent deprecated successfully!');
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setConfigYaml(content);
    };
    reader.readAsText(file);
  };

  const getCapabilityIcon = (cap: string) => {
    switch (cap) {
      case 'data_transform':
        return <ChartBarIcon className="w-4 h-4" />;
      case 'validator':
        return <ShieldCheckIcon className="w-4 h-4" />;
      case 'file_read':
        return <CodeBracketIcon className="w-4 h-4" />;
      default:
        return <CpuChipIcon className="w-4 h-4" />;
    }
  };

  return (
    <div className="p-6">
      <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-6">
        Configurable Agents
      </h1>

      {error && (
        <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-lg flex items-center justify-between">
          <p className="text-red-800 dark:text-red-200">{error}</p>
          <button
            onClick={() => setError(null)}
            className="text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>
      )}

      {success && (
        <div className="mb-4 p-4 bg-green-50 dark:bg-green-900/20 border border-green-300 dark:border-green-700 rounded-lg flex items-center justify-between">
          <p className="text-green-800 dark:text-green-200">{success}</p>
          <button
            onClick={() => setSuccess(null)}
            className="text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-300"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Workflow Runner Card */}
        <div className="lg:col-span-1">
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-4 mb-6 rounded-lg">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Run Workflow Spec</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Execute a YAML workflow spec via the Workflow Runner.</p>
            {runnerError && <div className="text-xs bg-red-50 dark:bg-red-900/20 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-200 p-2 mb-2 rounded">{runnerError}</div>}
            {runnerSuccess && <div className="text-xs bg-green-50 dark:bg-green-900/20 border border-green-300 dark:border-green-700 text-green-700 dark:text-green-200 p-2 mb-2 rounded">{runnerSuccess}</div>}
            <div className="space-y-2">
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Spec Path</label>
                <input value={runnerSpecPath} onChange={e => setRunnerSpecPath(e.target.value)} className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-300 rounded focus:outline-none focus:border-blue-500 dark:focus:border-blue-400" />
              </div>
              <div>
                <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">Event JSON</label>
                <textarea value={runnerEventJson} onChange={e => setRunnerEventJson(e.target.value)} className="w-full h-24 px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 font-mono text-xs text-gray-900 dark:text-gray-300 rounded focus:outline-none focus:border-blue-500 dark:focus:border-blue-400" />
              </div>
              <div className="mt-2">
                <button onClick={startWorkflowRunner} disabled={runnerLoading} className="px-3 py-2 bg-blue-50 dark:bg-blue-900/30 border border-blue-500 dark:border-blue-500 text-blue-700 dark:text-blue-400 disabled:opacity-50 rounded-md hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-all">
                  {runnerLoading ? 'Starting…' : 'Start Workflow'}
                </button>
              </div>
            </div>
          </div>
        </div>
        {/* Agent List */}
        <div className="lg:col-span-1">
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg rounded-lg">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Agents</h2>
              <Dialog.Root open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                <Dialog.Trigger asChild>
                  <button className="px-3 py-1 bg-blue-50 dark:bg-blue-900/30 border border-blue-500 dark:border-blue-500 text-blue-700 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-all text-sm rounded-md">
                    Create Agent
                  </button>
                </Dialog.Trigger>
                <Dialog.Portal>
                  <Dialog.Overlay className="fixed inset-0 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
                  <Dialog.Content className="fixed left-[50%] top-[50%] max-h-[85vh] w-[90vw] max-w-[650px] translate-x-[-50%] translate-y-[-50%] rounded-lg bg-white dark:bg-gray-800 p-6 shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]">
                    <Dialog.Title className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
                      Create Configurable Agent
                    </Dialog.Title>
                    
                    <div className="overflow-y-auto max-h-[calc(85vh-200px)]">
                      <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Load Sample Config
                        </label>
                        <Select.Root onValueChange={(value: string) => setConfigYaml(sampleConfigs[value as keyof typeof sampleConfigs])}>
                          <Select.Trigger className="inline-flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm gap-2 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600">
                            <Select.Value placeholder="Select a sample..." />
                            <Select.Icon>
                              <ChevronDownIcon className="h-4 w-4" />
                            </Select.Icon>
                          </Select.Trigger>
                          <Select.Portal>
                            <Select.Content className="overflow-hidden bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700">
                              <Select.Viewport className="p-1">
                                <Select.Item value="dataAnalyzer" className="relative flex items-center px-8 py-2 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-700 data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-700 cursor-pointer">
                                  <Select.ItemText>Data Analyzer</Select.ItemText>
                                </Select.Item>
                                <Select.Item value="codeReviewer" className="relative flex items-center px-8 py-2 text-sm rounded hover:bg-gray-100 dark:hover:bg-gray-700 data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-700 cursor-pointer">
                                  <Select.ItemText>Code Reviewer</Select.ItemText>
                                </Select.Item>
                              </Select.Viewport>
                            </Select.Content>
                          </Select.Portal>
                        </Select.Root>
                      </div>

                      <div className="mb-4">
                        <input
                          accept=".yaml,.yml,.json"
                          style={{ display: 'none' }}
                          id="config-file-upload"
                          type="file"
                          onChange={handleFileUpload}
                        />
                        <label htmlFor="config-file-upload">
                          <button
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center justify-center gap-2"
                            onClick={() => document.getElementById('config-file-upload')?.click()}
                          >
                            <ArrowUpTrayIcon className="w-5 h-5" />
                            Upload Config File
                          </button>
                        </label>
                      </div>

                      <div className="mb-4">
                        <textarea
                          value={configYaml}
                          onChange={(e) => setConfigYaml(e.target.value)}
                          placeholder="Paste YAML or JSON configuration here..."
                          className="w-full h-64 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono text-sm"
                        />
                      </div>

                      <div className="space-y-3">
                        <label className="flex items-center gap-2">
                          <Checkbox.Root
                            checked={enableBudget}
                            onCheckedChange={(checked: boolean) => setEnableBudget(checked)}
                            className="h-4 w-4 rounded border border-gray-300 dark:border-gray-600 data-[state=checked]:bg-primary-600 data-[state=checked]:border-primary-600"
                          >
                            <Checkbox.Indicator>
                              <CheckIcon className="h-3 w-3 text-white" />
                            </Checkbox.Indicator>
                          </Checkbox.Root>
                          <span className="text-sm text-gray-700 dark:text-gray-300">
                            Enable Budget Control
                          </span>
                        </label>
                        <label className="flex items-center gap-2">
                          <Checkbox.Root
                            checked={enableState}
                            onCheckedChange={(checked: boolean) => setEnableState(checked)}
                            className="h-4 w-4 rounded border border-gray-300 dark:border-gray-600 data-[state=checked]:bg-primary-600 data-[state=checked]:border-primary-600"
                          >
                            <Checkbox.Indicator>
                              <CheckIcon className="h-3 w-3 text-white" />
                            </Checkbox.Indicator>
                          </Checkbox.Root>
                          <span className="text-sm text-gray-700 dark:text-gray-300">
                            Enable State Persistence
                          </span>
                        </label>
                      </div>
                    </div>

                    <div className="mt-6 flex justify-end gap-3">
                      <Dialog.Close asChild>
                        <button className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">
                          Cancel
                        </button>
                      </Dialog.Close>
                      <button
                        onClick={createAgent}
                        disabled={!configYaml || loading}
                        className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                      >
                        {loading ? (
                          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                        ) : (
                          'Create'
                        )}
                      </button>
                    </div>
                  </Dialog.Content>
                </Dialog.Portal>
              </Dialog.Root>
            </div>
            <div className="p-4 space-y-2">
              {agents.map((agent) => (
                <motion.div
                  key={agent.agent_id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={clsx(
                    'p-3 rounded-lg cursor-pointer transition-all',
                    selectedAgent?.agent_id === agent.agent_id
                      ? 'bg-primary-50 dark:bg-primary-900/20 border-2 border-primary-500'
                      : 'bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 border-2 border-transparent'
                  )}
                  onClick={() => setSelectedAgent(agent)}
                >
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="font-medium text-gray-900 dark:text-white">
                        {agent.config_name}
                      </h3>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {agent.agent_id}
                      </p>
                      <div className="flex gap-2 mt-2">
                        <span className={clsx(
                          'px-2 py-1 text-xs rounded-full',
                          agent.state === 'idle'
                            ? 'bg-gray-200 text-gray-800 dark:bg-gray-600 dark:text-gray-200'
                            : 'bg-blue-200 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                        )}>
                          {agent.state}
                        </span>
                        <span className="px-2 py-1 text-xs bg-gray-200 dark:bg-gray-600 text-gray-800 dark:text-gray-200 rounded-full">
                          v{agent.config_version}
                        </span>
                      </div>
                    </div>
                    <AlertDialog.Root>
                      <AlertDialog.Trigger asChild>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteAgentId(agent.agent_id);
                          }}
                          className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/20"
                        >
                          <TrashIcon className="w-4 h-4 text-red-600 dark:text-red-400" />
                        </button>
                      </AlertDialog.Trigger>
                      <AlertDialog.Portal>
                        <AlertDialog.Overlay className="fixed inset-0 bg-black/50" />
                        <AlertDialog.Content className="fixed left-[50%] top-[50%] max-w-md translate-x-[-50%] translate-y-[-50%] rounded-lg bg-white dark:bg-gray-800 p-6 shadow-xl">
                          <AlertDialog.Title className="text-lg font-medium text-gray-900 dark:text-white">
                            Delete Agent
                          </AlertDialog.Title>
                          <AlertDialog.Description className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                            Are you sure you want to delete agent {agent.agent_id}? This action cannot be undone.
                          </AlertDialog.Description>
                          <div className="mt-4 flex justify-end gap-3">
                            <AlertDialog.Cancel asChild>
                              <button className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors">
                                Cancel
                              </button>
                            </AlertDialog.Cancel>
                            <AlertDialog.Action asChild>
                              <button
                                onClick={() => deleteAgent(agent.agent_id)}
                                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                              >
                                Delete
                              </button>
                            </AlertDialog.Action>
                          </div>
                        </AlertDialog.Content>
                      </AlertDialog.Portal>
                    </AlertDialog.Root>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </div>

        {/* Agent Details */}
        <div className="lg:col-span-2">
          {selectedAgent ? (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg rounded-lg">
              <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center">
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {selectedAgent.config_name}
                </h2>
                <Dialog.Root open={executeDialogOpen} onOpenChange={setExecuteDialogOpen}>
                  <Dialog.Trigger asChild>
                    <button className="flex items-center gap-2 px-4 py-2 bg-green-50 dark:bg-green-900/30 border border-green-500 dark:border-green-500 text-green-700 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/40 transition-all rounded-md">
                      <PlayIcon className="w-4 h-4" />
                      Execute Task
                    </button>
                  </Dialog.Trigger>
                  <Dialog.Portal>
                    <Dialog.Overlay className="fixed inset-0 bg-black/50" />
                    <Dialog.Content className="fixed left-[50%] top-[50%] max-h-[85vh] w-[90vw] max-w-[650px] translate-x-[-50%] translate-y-[-50%] rounded-lg bg-white dark:bg-gray-800 p-6 shadow-xl">
                      <Dialog.Title className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
                        Execute Task
                      </Dialog.Title>
                      
                      <div className="overflow-y-auto max-h-[calc(85vh-200px)]">
                        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                          Enter task data that matches the agent's state schema:
                        </p>

                        <textarea
                          value={taskJson}
                          onChange={(e) => setTaskJson(e.target.value)}
                          placeholder={'{\n  "data_type": "sales_metrics",\n  "content": "Q4 revenue data..."\n}'}
                          className="w-full h-48 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono text-sm mb-4"
                        />

                        {executionResult && (
                          <div className="mt-4">
                            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                              Execution Result:
                            </h3>
                            <div className="rounded-lg overflow-hidden">
                              <SyntaxHighlighter language="json" style={tomorrow}>
                                {JSON.stringify(executionResult, null, 2)}
                              </SyntaxHighlighter>
                            </div>
                          </div>
                        )}
                      </div>

                      <div className="mt-6 flex justify-end gap-3">
                        <Dialog.Close asChild>
                          <button
                            onClick={() => {
                              setExecutionResult(null);
                              setTaskJson('');
                            }}
                            className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                          >
                            Close
                          </button>
                        </Dialog.Close>
                        <button
                          onClick={executeTask}
                          disabled={!taskJson || loading}
                          className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          {loading ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                          ) : (
                            'Execute'
                          )}
                        </button>
                      </div>
                    </Dialog.Content>
                  </Dialog.Portal>
                </Dialog.Root>
              </div>

              {/* Tabs */}
              <Tabs.Root value={activeTab} onValueChange={setActiveTab}>
                <Tabs.List className="flex border-b dark:border-gray-700">
                  <Tabs.Trigger 
                    value="overview" 
                    className="px-6 py-3 text-sm font-medium border-b-2 transition-colors data-[state=active]:border-primary-500 data-[state=active]:text-primary-600 dark:data-[state=active]:text-primary-400 data-[state=inactive]:border-transparent data-[state=inactive]:text-gray-500 hover:text-gray-700 dark:data-[state=inactive]:text-gray-400 dark:hover:text-gray-200"
                  >
                    Overview
                  </Tabs.Trigger>
                  <Tabs.Trigger 
                    value="state"
                    className="px-6 py-3 text-sm font-medium border-b-2 transition-colors data-[state=active]:border-primary-500 data-[state=active]:text-primary-600 dark:data-[state=active]:text-primary-400 data-[state=inactive]:border-transparent data-[state=inactive]:text-gray-500 hover:text-gray-700 dark:data-[state=inactive]:text-gray-400 dark:hover:text-gray-200"
                  >
                    State
                  </Tabs.Trigger>
                  <Tabs.Trigger 
                    value="budget"
                    className="px-6 py-3 text-sm font-medium border-b-2 transition-colors data-[state=active]:border-primary-500 data-[state=active]:text-primary-600 dark:data-[state=active]:text-primary-400 data-[state=inactive]:border-transparent data-[state=inactive]:text-gray-500 hover:text-gray-700 dark:data-[state=inactive]:text-gray-400 dark:hover:text-gray-200"
                  >
                    Budget
                  </Tabs.Trigger>
                  <Tabs.Trigger 
                    value="capabilities"
                    className="px-6 py-3 text-sm font-medium border-b-2 transition-colors data-[state=active]:border-primary-500 data-[state=active]:text-primary-600 dark:data-[state=active]:text-primary-400 data-[state=inactive]:border-transparent data-[state=inactive]:text-gray-500 hover:text-gray-700 dark:data-[state=inactive]:text-gray-400 dark:hover:text-gray-200"
                  >
                    Capabilities
                  </Tabs.Trigger>
                </Tabs.List>

                <div className="p-6">
                  <Tabs.Content value="overview">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Agent ID</p>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {selectedAgent.agent_id}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Version</p>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {selectedAgent.config_version}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Executions</p>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {selectedAgent.execution_count}
                        </p>
                      </div>
                      <div>
                        <p className="text-sm text-gray-500 dark:text-gray-400">Created</p>
                        <p className="font-medium text-gray-900 dark:text-white">
                          {new Date(selectedAgent.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  </Tabs.Content>

                  <Tabs.Content value="state">
                    {agentState && (
                      <div className="rounded-lg overflow-hidden">
                        <SyntaxHighlighter language="json" style={tomorrow}>
                          {JSON.stringify(agentState, null, 2)}
                        </SyntaxHighlighter>
                      </div>
                    )}
                  </Tabs.Content>

                  <Tabs.Content value="budget">
                    <div className="overflow-x-auto">
                      <table className="min-w-full">
                        <thead>
                          <tr className="border-b dark:border-gray-700">
                            <th className="px-4 py-2 text-left text-sm font-medium text-gray-700 dark:text-gray-300">
                              Resource
                            </th>
                            <th className="px-4 py-2 text-left text-sm font-medium text-gray-700 dark:text-gray-300">
                              Usage
                            </th>
                            <th className="px-4 py-2 text-left text-sm font-medium text-gray-700 dark:text-gray-300">
                              Limit
                            </th>
                            <th className="px-4 py-2 text-left text-sm font-medium text-gray-700 dark:text-gray-300">
                              Percentage
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {agentBudget.map((usage) => (
                            <tr key={usage.resource_type} className="border-b dark:border-gray-700">
                              <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                                {usage.resource_type}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                                {usage.current}
                              </td>
                              <td className="px-4 py-3 text-sm text-gray-900 dark:text-white">
                                {usage.limit}
                              </td>
                              <td className="px-4 py-3">
                                <div className="flex items-center gap-2">
                                  <div className="w-24 bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                                    <div
                                      className="bg-primary-600 h-2 rounded-full"
                                      style={{ width: `${usage.percentage}%` }}
                                    />
                                  </div>
                                  <span className="text-sm text-gray-900 dark:text-white">
                                    {usage.percentage.toFixed(1)}%
                                  </span>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Tabs.Content>

                  <Tabs.Content value="capabilities">
                    <div className="flex flex-wrap gap-2">
                      {selectedAgent.capabilities.map((cap) => (
                        <span
                          key={cap}
                          className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded-full text-sm"
                        >
                          {getCapabilityIcon(cap)}
                          {cap}
                        </span>
                      ))}
                    </div>
                  </Tabs.Content>
                </div>
              </Tabs.Root>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg p-12 rounded-lg">
              <p className="text-center text-gray-500 dark:text-gray-400">
                Select an agent to view details
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ConfigurableAgentPanel;
