'use client';

import { useState, useMemo, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  XCircleIcon,
  DocumentTextIcon,
  CodeBracketIcon,
  ClipboardDocumentIcon,
  SparklesIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import * as jsYaml from 'js-yaml';
import { useCreateCapability } from '../../../../hooks/useCapabilities';
import type { CreateCapabilityRequest } from '../../../../types/capability';

// Validation types mirroring backend
interface ValidationIssue {
  field: string;
  message: string;
  severity: 'error' | 'warning' | 'info';
  code?: string;
}

interface ParsedCapabilitySpec {
  name?: string;
  agent_type?: string;
  domain?: string;
  task_type?: string;
  description?: string;
  inputs?: Record<string, unknown>;
  outputs?: Record<string, unknown>;
  [key: string]: unknown;
}

interface ValidationResult {
  isValid: boolean;
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
  info: ValidationIssue[];
  parsedSpec: ParsedCapabilitySpec | null;
}

// Valid values (matching backend)
const VALID_TASK_TYPES = [
  'general',
  'reasoning',
  'creative',
  'web_research',
  'analysis',
  'content_writing',
  'data_processing',
  'automation',
  'communication',
];

const VALID_INPUT_TYPES = ['string', 'integer', 'number', 'boolean', 'array', 'object', 'any'];

const VALID_DOMAINS = [
  'content',
  'research',
  'analytics',
  'automation',
  'communication',
  'integration',
  'utility',
  'data',
  'finance',
  'marketing',
];

const VALID_SPEED_VALUES = ['fast', 'medium', 'slow'];
const VALID_COST_VALUES = ['low', 'medium', 'high'];

// Client-side YAML validation
function validateCapabilityYaml(yamlString: string): ValidationResult {
  const result: ValidationResult = {
    isValid: true,
    errors: [],
    warnings: [],
    info: [],
    parsedSpec: null,
  };

  const addError = (field: string, message: string, code?: string) => {
    result.errors.push({ field, message, severity: 'error', code });
    result.isValid = false;
  };

  const addWarning = (field: string, message: string, code?: string) => {
    result.warnings.push({ field, message, severity: 'warning', code });
  };

  const addInfo = (field: string, message: string, code?: string) => {
    result.info.push({ field, message, severity: 'info', code });
  };

  // Parse YAML using js-yaml
  let parsed: ParsedCapabilitySpec;
  try {
    parsed = jsYaml.load(yamlString) as ParsedCapabilitySpec;
    result.parsedSpec = parsed;
  } catch (e) {
    addError('yaml', `Invalid YAML syntax: ${(e as Error).message}`, 'YAML_SYNTAX');
    return result;
  }

  if (!parsed || typeof parsed !== 'object') {
    addError('root', 'YAML specification must be an object', 'NOT_OBJECT');
    return result;
  }

  // Required fields
  if (!parsed.agent_type) {
    addError('agent_type', 'Missing required field: agent_type', 'MISSING_AGENT_TYPE');
  }
  if (!parsed.system_prompt) {
    addError('system_prompt', 'Missing required field: system_prompt', 'MISSING_SYSTEM_PROMPT');
  }
  if (parsed.inputs === undefined) {
    addError('inputs', 'Missing required field: inputs', 'MISSING_INPUTS');
  } else if (typeof parsed.inputs !== 'object' || Array.isArray(parsed.inputs)) {
    addError('inputs', 'inputs must be an object with input field definitions', 'INPUTS_NOT_OBJECT');
  }

  // Validate agent_type format
  const agentType = parsed.agent_type as string;
  if (agentType) {
    if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(agentType)) {
      addError(
        'agent_type',
        'agent_type must start with a letter and contain only alphanumeric characters and underscores',
        'INVALID_AGENT_TYPE_FORMAT'
      );
    }
    if (agentType.length > 100) {
      addError('agent_type', 'agent_type must be 100 characters or less', 'AGENT_TYPE_TOO_LONG');
    }
    if (agentType !== agentType.toLowerCase()) {
      addWarning('agent_type', 'agent_type should be lowercase (snake_case recommended)', 'AGENT_TYPE_NOT_LOWERCASE');
    }
  }

  // Validate name
  const name = parsed.name;
  if (name !== undefined) {
    if (typeof name !== 'string') {
      addError('name', 'name must be a string', 'NAME_NOT_STRING');
    } else if (name.length > 200) {
      addError('name', 'name must be 200 characters or less', 'NAME_TOO_LONG');
    }
  }

  // Validate task_type
  const taskType = parsed.task_type as string;
  if (taskType) {
    if (typeof taskType !== 'string') {
      addError('task_type', 'task_type must be a string', 'TASK_TYPE_NOT_STRING');
    } else if (!VALID_TASK_TYPES.includes(taskType)) {
      addError('task_type', `Invalid task_type '${taskType}'. Valid values: ${VALID_TASK_TYPES.join(', ')}`, 'INVALID_TASK_TYPE');
    }
  }

  // Validate domain
  const domain = parsed.domain as string;
  if (domain) {
    if (typeof domain !== 'string') {
      addError('domain', 'domain must be a string', 'DOMAIN_NOT_STRING');
    } else if (!VALID_DOMAINS.includes(domain)) {
      addWarning('domain', `Unknown domain '${domain}'. Known domains: ${VALID_DOMAINS.join(', ')}`, 'UNKNOWN_DOMAIN');
    }
  }

  // Validate inputs
  const inputs = parsed.inputs as Record<string, unknown>;
  if (inputs && typeof inputs === 'object' && !Array.isArray(inputs)) {
    for (const [inputName, inputDef] of Object.entries(inputs)) {
      if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(inputName)) {
        addError(
          `inputs.${inputName}`,
          `Input name '${inputName}' must start with a letter and contain only alphanumeric characters and underscores`,
          'INVALID_INPUT_NAME'
        );
      }

      if (typeof inputDef !== 'object' || inputDef === null || Array.isArray(inputDef)) {
        addError(`inputs.${inputName}`, `Input '${inputName}' definition must be an object`, 'INPUT_NOT_OBJECT');
        continue;
      }

      const def = inputDef as Record<string, unknown>;
      const inputType = def.type as string;
      if (!inputType) {
        addError(`inputs.${inputName}.type`, `Input '${inputName}' missing required 'type' field`, 'MISSING_INPUT_TYPE');
      } else if (!VALID_INPUT_TYPES.includes(inputType)) {
        addError(
          `inputs.${inputName}.type`,
          `Input '${inputName}' has invalid type '${inputType}'. Valid types: ${VALID_INPUT_TYPES.join(', ')}`,
          'INVALID_INPUT_TYPE'
        );
      }

      if (def.required !== undefined && typeof def.required !== 'boolean') {
        addError(`inputs.${inputName}.required`, `Input '${inputName}' required field must be a boolean`, 'REQUIRED_NOT_BOOLEAN');
      }

      if (!def.description) {
        addInfo(`inputs.${inputName}.description`, `Input '${inputName}' should have a description for documentation`, 'MISSING_INPUT_DESCRIPTION');
      }
    }
  }

  // Validate outputs
  const outputs = parsed.outputs as Record<string, unknown>;
  if (outputs && typeof outputs === 'object' && !Array.isArray(outputs)) {
    for (const [outputName, outputDef] of Object.entries(outputs)) {
      if (!/^[a-zA-Z][a-zA-Z0-9_]*$/.test(outputName)) {
        addError(
          `outputs.${outputName}`,
          `Output name '${outputName}' must start with a letter and contain only alphanumeric characters and underscores`,
          'INVALID_OUTPUT_NAME'
        );
      }

      if (typeof outputDef !== 'object' || outputDef === null || Array.isArray(outputDef)) {
        addError(`outputs.${outputName}`, `Output '${outputName}' definition must be an object`, 'OUTPUT_NOT_OBJECT');
        continue;
      }

      const def = outputDef as Record<string, unknown>;
      const outputType = def.type as string;
      if (!outputType) {
        addError(`outputs.${outputName}.type`, `Output '${outputName}' missing required 'type' field`, 'MISSING_OUTPUT_TYPE');
      } else if (!VALID_INPUT_TYPES.includes(outputType)) {
        addError(
          `outputs.${outputName}.type`,
          `Output '${outputName}' has invalid type '${outputType}'. Valid types: ${VALID_INPUT_TYPES.join(', ')}`,
          'INVALID_OUTPUT_TYPE'
        );
      }
    }
  }

  // Validate execution_hints
  const hints = parsed.execution_hints as Record<string, unknown>;
  if (hints && typeof hints === 'object') {
    if (hints.deterministic !== undefined && typeof hints.deterministic !== 'boolean') {
      addError('execution_hints.deterministic', 'deterministic must be a boolean', 'DETERMINISTIC_NOT_BOOLEAN');
    }
    if (hints.speed !== undefined && !VALID_SPEED_VALUES.includes(hints.speed as string)) {
      addError('execution_hints.speed', `Invalid speed value. Valid values: ${VALID_SPEED_VALUES.join(', ')}`, 'INVALID_SPEED_VALUE');
    }
    if (hints.cost !== undefined && !VALID_COST_VALUES.includes(hints.cost as string)) {
      addError('execution_hints.cost', `Invalid cost value. Valid values: ${VALID_COST_VALUES.join(', ')}`, 'INVALID_COST_VALUE');
    }
    if (hints.max_tokens !== undefined && typeof hints.max_tokens !== 'number') {
      addError('execution_hints.max_tokens', 'max_tokens must be a number', 'MAX_TOKENS_NOT_NUMBER');
    }
    if (hints.temperature !== undefined && typeof hints.temperature !== 'number') {
      addError('execution_hints.temperature', 'temperature must be a number', 'TEMPERATURE_NOT_NUMBER');
    }
  }

  // Recommended fields
  if (!parsed.name) {
    addInfo('name', "Recommended field 'name' is not defined", 'MISSING_NAME');
  }
  if (!parsed.description) {
    addInfo('description', "Recommended field 'description' is not defined", 'MISSING_DESCRIPTION');
  }
  if (!parsed.domain) {
    addInfo('domain', "Recommended field 'domain' is not defined", 'MISSING_DOMAIN');
  }
  if (!parsed.outputs) {
    addInfo('outputs', "No outputs defined (capability won't have typed outputs)", 'MISSING_OUTPUTS');
  }

  return result;
}

// Default capability YAML template
const DEFAULT_YAML = `# Capability Definition
# Required fields: agent_type, system_prompt, inputs

agent_type: my_custom_agent
name: My Custom Agent
description: A brief description of what this agent does
domain: utility
task_type: general

system_prompt: |
  You are a helpful assistant that performs a specific task.

  Your goal is to process the input and produce a meaningful output.

  Input: {{ content }}

  Provide your response in a clear and structured format.

inputs:
  content:
    type: string
    required: true
    description: The main content to process

outputs:
  result:
    type: string
    description: The processed output

execution_hints:
  deterministic: false
  speed: medium
  cost: low
  temperature: 0.7

examples:
  - content: "Example input text"
`;

export default function CreateCapabilityPage() {
  const router = useRouter();
  const { create, isLoading, error } = useCreateCapability();

  // Form state
  const [yamlContent, setYamlContent] = useState(DEFAULT_YAML);
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');

  // UI state
  const [showPreview, setShowPreview] = useState(true);
  const [showInputsPreview, setShowInputsPreview] = useState(true);
  const [showOutputsPreview, setShowOutputsPreview] = useState(true);
  const [copiedField, setCopiedField] = useState<string | null>(null);

  // Validation state
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [debouncedYaml, setDebouncedYaml] = useState(yamlContent);

  // Debounce YAML changes for validation
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedYaml(yamlContent);
    }, 300);
    return () => clearTimeout(timer);
  }, [yamlContent]);

  // Validate YAML when debounced value changes
  useEffect(() => {
    if (debouncedYaml.trim()) {
      const result = validateCapabilityYaml(debouncedYaml);
      setValidationResult(result);
    } else {
      setValidationResult(null);
    }
  }, [debouncedYaml]);

  // Handle form submission
  const handleSubmit = async () => {
    if (!validationResult?.isValid) {
      return;
    }

    try {
      const request: CreateCapabilityRequest = {
        spec_yaml: yamlContent,
        tags: tags.length > 0 ? tags : undefined,
      };
      const created = await create(request);
      router.push(`/capabilities/${created.id}`);
    } catch {
      // Error is handled by the hook
    }
  };

  // Handle tag management
  const addTag = () => {
    const tag = tagInput.trim().toLowerCase();
    if (tag && !tags.includes(tag)) {
      setTags([...tags, tag]);
      setTagInput('');
    }
  };

  const removeTag = (tagToRemove: string) => {
    setTags(tags.filter((t) => t !== tagToRemove));
  };

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addTag();
    }
  };

  // Copy to clipboard
  const copyToClipboard = async (text: string, field: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  // Format JSON for display
  const formatJson = (obj: unknown): string => {
    if (!obj || (typeof obj === 'object' && Object.keys(obj as object).length === 0)) {
      return 'No data';
    }
    return JSON.stringify(obj, null, 2);
  };

  // Get parsed spec values for preview
  const parsedSpec = validationResult?.parsedSpec;
  const agentName = parsedSpec?.name || parsedSpec?.agent_type || 'Unnamed';
  const inputsSchema = parsedSpec?.inputs;
  const outputsSchema = parsedSpec?.outputs;

  const errorCount = validationResult?.errors.length || 0;
  const warningCount = validationResult?.warnings.length || 0;
  const infoCount = validationResult?.info.length || 0;

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Link
              href="/capabilities"
              className="p-2 rounded border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
            >
              <ArrowLeftIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
            </Link>
            <div>
              <h1 className="text-2xl font-mono font-bold tracking-wider text-[var(--foreground)]">
                CREATE CAPABILITY
              </h1>
              <p className="text-sm font-mono text-[var(--muted-foreground)] mt-1">
                Define a new custom capability using YAML
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={handleSubmit}
              disabled={isLoading || !validationResult?.isValid}
              className="flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <ArrowPathIcon className="w-4 h-4 animate-spin" />
              ) : (
                <SparklesIcon className="w-4 h-4" />
              )}
              CREATE
            </button>
          </div>
        </div>

        {/* Error from API */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/50 rounded-lg">
            <p className="text-sm font-mono text-red-500">{error.message}</p>
          </div>
        )}

        {/* Main content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left column: YAML Editor */}
          <div className="space-y-6">
            {/* YAML Editor Card */}
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
              <div className="p-4 border-b border-[var(--border)]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CodeBracketIcon className="w-5 h-5 text-[var(--accent)]" />
                    <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                      YAML SPECIFICATION
                    </h2>
                  </div>
                  <button
                    onClick={() => copyToClipboard(yamlContent, 'yaml')}
                    className="p-1.5 rounded border border-[var(--border)] hover:bg-[var(--muted)] transition-colors"
                    title="Copy YAML"
                  >
                    <ClipboardDocumentIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                  </button>
                </div>
                {copiedField === 'yaml' && (
                  <span className="text-xs font-mono text-green-500 mt-1 block">Copied!</span>
                )}
              </div>
              <div className="relative">
                <textarea
                  value={yamlContent}
                  onChange={(e) => setYamlContent(e.target.value)}
                  className="w-full h-[500px] p-4 bg-[#282c34] text-[#abb2bf] font-mono text-sm resize-none focus:outline-none"
                  spellCheck={false}
                  placeholder="Enter your capability YAML specification..."
                />
              </div>
            </div>

            {/* Tags input */}
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
              <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)] mb-3">
                TAGS (Optional)
              </h2>
              <div className="flex flex-wrap gap-2 mb-3">
                {tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 px-2 py-1 text-xs font-mono bg-[var(--muted)] rounded"
                  >
                    {tag}
                    <button
                      onClick={() => removeTag(tag)}
                      className="hover:text-red-500 transition-colors"
                    >
                      <XCircleIcon className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={handleTagKeyDown}
                  placeholder="Add a tag..."
                  className="flex-1 px-3 py-2 text-sm font-mono bg-[var(--background)] border border-[var(--border)] rounded-md text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]"
                />
                <button
                  onClick={addTag}
                  className="px-3 py-2 text-xs font-mono tracking-wider border border-[var(--border)] rounded-md text-[var(--muted-foreground)] hover:bg-[var(--muted)] transition-colors"
                >
                  ADD
                </button>
              </div>
            </div>
          </div>

          {/* Right column: Validation & Preview */}
          <div className="space-y-6">
            {/* Validation Status */}
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                  VALIDATION STATUS
                </h2>
                {validationResult && (
                  <div className="flex items-center gap-3">
                    {errorCount > 0 && (
                      <span className="flex items-center gap-1 text-xs font-mono text-red-500">
                        <XCircleIcon className="w-4 h-4" />
                        {errorCount} error{errorCount !== 1 ? 's' : ''}
                      </span>
                    )}
                    {warningCount > 0 && (
                      <span className="flex items-center gap-1 text-xs font-mono text-yellow-500">
                        <ExclamationTriangleIcon className="w-4 h-4" />
                        {warningCount} warning{warningCount !== 1 ? 's' : ''}
                      </span>
                    )}
                    {infoCount > 0 && (
                      <span className="flex items-center gap-1 text-xs font-mono text-blue-500">
                        <InformationCircleIcon className="w-4 h-4" />
                        {infoCount} suggestion{infoCount !== 1 ? 's' : ''}
                      </span>
                    )}
                    {errorCount === 0 && warningCount === 0 && (
                      <span className="flex items-center gap-1 text-xs font-mono text-green-500">
                        <CheckCircleIcon className="w-4 h-4" />
                        Valid
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Validation issues */}
              {validationResult && (errorCount > 0 || warningCount > 0 || infoCount > 0) && (
                <div className="space-y-2 max-h-[200px] overflow-y-auto">
                  {validationResult.errors.map((issue, i) => (
                    <div key={`err-${i}`} className="flex items-start gap-2 p-2 bg-red-500/10 rounded">
                      <XCircleIcon className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                      <div>
                        <code className="text-xs font-mono text-red-400">{issue.field}</code>
                        <p className="text-xs font-mono text-red-500">{issue.message}</p>
                      </div>
                    </div>
                  ))}
                  {validationResult.warnings.map((issue, i) => (
                    <div key={`warn-${i}`} className="flex items-start gap-2 p-2 bg-yellow-500/10 rounded">
                      <ExclamationTriangleIcon className="w-4 h-4 text-yellow-500 flex-shrink-0 mt-0.5" />
                      <div>
                        <code className="text-xs font-mono text-yellow-400">{issue.field}</code>
                        <p className="text-xs font-mono text-yellow-500">{issue.message}</p>
                      </div>
                    </div>
                  ))}
                  {validationResult.info.map((issue, i) => (
                    <div key={`info-${i}`} className="flex items-start gap-2 p-2 bg-blue-500/10 rounded">
                      <InformationCircleIcon className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" />
                      <div>
                        <code className="text-xs font-mono text-blue-400">{issue.field}</code>
                        <p className="text-xs font-mono text-blue-500">{issue.message}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!validationResult && (
                <p className="text-sm font-mono text-[var(--muted-foreground)]">
                  Enter YAML to see validation results
                </p>
              )}
            </div>

            {/* Preview Card */}
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
              <button
                onClick={() => setShowPreview(!showPreview)}
                className="w-full flex items-center justify-between p-4 hover:bg-[var(--muted)]/50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <DocumentTextIcon className="w-5 h-5 text-[var(--accent)]" />
                  <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                    PREVIEW
                  </h2>
                </div>
                {showPreview ? (
                  <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                ) : (
                  <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                )}
              </button>

              {showPreview && parsedSpec && (
                <div className="p-4 pt-0 space-y-4">
                  {/* Basic Info */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">NAME</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                        {agentName}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">AGENT TYPE</p>
                      <code className="text-xs font-mono bg-[var(--muted)] px-2 py-0.5 rounded mt-1 inline-block">
                        {parsedSpec.agent_type || '-'}
                      </code>
                    </div>
                    <div>
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">DOMAIN</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                        {parsedSpec.domain || '-'}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">TASK TYPE</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                        {parsedSpec.task_type || 'general'}
                      </p>
                    </div>
                  </div>

                  {/* Description */}
                  {parsedSpec.description && (
                    <div>
                      <p className="text-xs font-mono text-[var(--muted-foreground)]">DESCRIPTION</p>
                      <p className="text-sm font-mono text-[var(--foreground)] mt-1">
                        {parsedSpec.description}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Inputs Preview */}
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
              <button
                onClick={() => setShowInputsPreview(!showInputsPreview)}
                className="w-full flex items-center justify-between p-4 hover:bg-[var(--muted)]/50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <DocumentTextIcon className="w-5 h-5 text-[var(--accent)]" />
                  <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                    INPUT SCHEMA
                  </h2>
                  {inputsSchema && (
                    <span className="text-xs font-mono text-[var(--muted-foreground)]">
                      ({Object.keys(inputsSchema).length} field{Object.keys(inputsSchema).length !== 1 ? 's' : ''})
                    </span>
                  )}
                </div>
                {showInputsPreview ? (
                  <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                ) : (
                  <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                )}
              </button>

              {showInputsPreview && (
                <div className="px-4 pb-4">
                  <div className="relative">
                    <button
                      onClick={() => copyToClipboard(formatJson(inputsSchema), 'inputs')}
                      className="absolute top-2 right-2 p-1.5 bg-[var(--card)] border border-[var(--border)] rounded hover:bg-[var(--muted)] transition-colors z-10"
                      title="Copy"
                    >
                      <ClipboardDocumentIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                    </button>
                    {copiedField === 'inputs' && (
                      <span className="absolute top-2 right-12 text-xs font-mono text-green-500">Copied!</span>
                    )}
                    <pre className="p-4 bg-[var(--muted)] rounded-lg overflow-auto max-h-48 text-xs font-mono text-[var(--foreground)]">
                      {formatJson(inputsSchema)}
                    </pre>
                  </div>
                </div>
              )}
            </div>

            {/* Outputs Preview */}
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg overflow-hidden">
              <button
                onClick={() => setShowOutputsPreview(!showOutputsPreview)}
                className="w-full flex items-center justify-between p-4 hover:bg-[var(--muted)]/50 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <DocumentTextIcon className="w-5 h-5 text-[var(--accent)]" />
                  <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)]">
                    OUTPUT SCHEMA
                  </h2>
                  {outputsSchema && (
                    <span className="text-xs font-mono text-[var(--muted-foreground)]">
                      ({Object.keys(outputsSchema).length} field{Object.keys(outputsSchema).length !== 1 ? 's' : ''})
                    </span>
                  )}
                </div>
                {showOutputsPreview ? (
                  <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                ) : (
                  <ChevronRightIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                )}
              </button>

              {showOutputsPreview && (
                <div className="px-4 pb-4">
                  <div className="relative">
                    <button
                      onClick={() => copyToClipboard(formatJson(outputsSchema), 'outputs')}
                      className="absolute top-2 right-2 p-1.5 bg-[var(--card)] border border-[var(--border)] rounded hover:bg-[var(--muted)] transition-colors z-10"
                      title="Copy"
                    >
                      <ClipboardDocumentIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
                    </button>
                    {copiedField === 'outputs' && (
                      <span className="absolute top-2 right-12 text-xs font-mono text-green-500">Copied!</span>
                    )}
                    <pre className="p-4 bg-[var(--muted)] rounded-lg overflow-auto max-h-48 text-xs font-mono text-[var(--foreground)]">
                      {formatJson(outputsSchema)}
                    </pre>
                  </div>
                </div>
              )}
            </div>

            {/* Help Section */}
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
              <h2 className="text-sm font-mono font-bold tracking-wider text-[var(--foreground)] mb-3">
                YAML REFERENCE
              </h2>
              <div className="space-y-2 text-xs font-mono text-[var(--muted-foreground)]">
                <p><strong className="text-[var(--foreground)]">Required:</strong> agent_type, system_prompt, inputs</p>
                <p><strong className="text-[var(--foreground)]">Recommended:</strong> name, description, domain, outputs</p>
                <p><strong className="text-[var(--foreground)]">Valid domains:</strong> {VALID_DOMAINS.join(', ')}</p>
                <p><strong className="text-[var(--foreground)]">Valid task_types:</strong> {VALID_TASK_TYPES.join(', ')}</p>
                <p><strong className="text-[var(--foreground)]">Valid input types:</strong> {VALID_INPUT_TYPES.join(', ')}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
