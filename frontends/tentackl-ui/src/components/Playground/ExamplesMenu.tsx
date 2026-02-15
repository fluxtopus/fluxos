import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ExampleWorkflow } from '../../services/playgroundApi';

interface ExamplesMenuProps {
  examples: ExampleWorkflow[];
  onSelectExample: (example: ExampleWorkflow) => void;
  onBuildWorkflow: (example: ExampleWorkflow) => void;
}

const categoryIcons: Record<string, React.ReactNode> = {
  // Starter - Play/Start icon
  starter: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  // Data - Chart/bars
  data: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  ),
  // Dev - Code brackets
  dev: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
    </svg>
  ),
  // Finance - Currency/dollar
  finance: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  ),
  // Marketing - Megaphone/speaker
  marketing: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5.882V19.24a1.76 1.76 0 01-3.417.592l-2.147-6.15M18 13a3 3 0 100-6M5.436 13.683A4.001 4.001 0 017 6h1.832c4.1 0 7.625-1.234 9.168-3v14c-1.543-1.766-5.067-3-9.168-3H7a3.988 3.988 0 01-1.564-.317z" />
    </svg>
  ),
  // Lifestyle - Sun/sparkle
  lifestyle: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
    </svg>
  ),
  // Advanced - Lightning bolt
  advanced: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
  // News (legacy) - Newspaper
  news: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
    </svg>
  ),
  // Research (legacy) - Search
  research: (
    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
    </svg>
  ),
};

export const ExamplesMenu: React.FC<ExamplesMenuProps> = ({
  examples,
  onSelectExample,
  onBuildWorkflow,
}) => {
  const [selectedExample, setSelectedExample] = useState<ExampleWorkflow | null>(null);
  const [mounted, setMounted] = useState(false);

  // Ensure portal only renders on client
  useEffect(() => {
    setMounted(true);
  }, []);

  // Separate basic and advanced examples
  const basicExamples = examples.filter(e => e.category !== 'advanced');
  const advancedExamples = examples.filter(e => e.category === 'advanced');

  const handleExampleClick = (example: ExampleWorkflow) => {
    setSelectedExample(example);
  };

  const handleBuild = () => {
    if (selectedExample) {
      onSelectExample(selectedExample);
      onBuildWorkflow(selectedExample);
      setSelectedExample(null);
    }
  };

  const handleClose = () => {
    setSelectedExample(null);
  };

  const renderExample = (example: ExampleWorkflow) => (
    <button
      key={example.id}
      type="button"
      onClick={() => handleExampleClick(example)}
      className="text-left p-3 rounded border border-[oklch(0.22_0.03_260)] bg-[oklch(0.12_0.02_260/0.5)] hover:border-[oklch(0.65_0.25_180/0.5)] hover:bg-[oklch(0.65_0.25_180/0.1)] transition-all duration-300 group tactical-hover"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 rounded border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260)] text-[oklch(0.65_0.25_180)] group-hover:border-[oklch(0.65_0.25_180/0.5)] group-hover:shadow-[0_0_10px_oklch(0.65_0.25_180/0.2)] transition-all duration-300">
          {categoryIcons[example.category] || (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-mono text-xs tracking-wider text-[oklch(0.95_0.01_90)] group-hover:text-[oklch(0.65_0.25_180)] transition-colors uppercase">
            {example.name}
          </h4>
          <p className="mt-1 text-[10px] text-[oklch(0.58_0.01_260)] line-clamp-2">
            {example.description}
          </p>
        </div>
      </div>
    </button>
  );

  return (
    <>
      <div className="rounded-lg border border-[oklch(0.22_0.03_260)] bg-[oklch(0.12_0.02_260/0.8)] backdrop-blur-md overflow-hidden">
        {/* Header */}
        <div className="px-4 py-2 border-b border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260/0.5)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[oklch(0.75_0.2_85)]" />
            <span className="font-mono text-xs tracking-wider text-[oklch(0.75_0.2_85)] uppercase">
              EXAMPLE WORKFLOWS
            </span>
          </div>
          <span className="font-mono text-[10px] text-[oklch(0.58_0.01_260)]">
            {examples.length} AVAILABLE
          </span>
        </div>

        {/* Basic Examples */}
        <div className="p-3 pb-2">
          <div className="flex flex-col gap-2">
            {basicExamples.map(renderExample)}
          </div>
        </div>

        {/* Advanced Examples Section */}
        {advancedExamples.length > 0 && (
          <div className="border-t border-[oklch(0.22_0.03_260)]">
            <div className="px-4 py-2 bg-[oklch(0.65_0.25_180/0.1)] flex items-center gap-2">
              <svg className="h-4 w-4 text-[oklch(0.65_0.25_180)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <span className="font-mono text-[10px] tracking-[0.2em] text-[oklch(0.65_0.25_180)] uppercase">
                ADVANCED // MULTI-LLM & PARALLEL
              </span>
            </div>
            <div className="p-3 pt-2">
              <div className="flex flex-col gap-2">
                {advancedExamples.map(renderExample)}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Example Preview Modal - rendered via portal */}
      {mounted && createPortal(
        <AnimatePresence>
          {selectedExample && (
            <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
              {/* Backdrop */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={handleClose}
                className="absolute inset-0 bg-[oklch(0_0_0/0.7)] backdrop-blur-sm"
              />

              {/* Modal */}
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                transition={{ type: 'spring', damping: 25, stiffness: 300 }}
                className="relative w-full max-w-[600px] max-h-[80vh] bg-[oklch(0.1_0.02_260)] border border-[oklch(0.65_0.25_180)] rounded-xl shadow-2xl flex flex-col overflow-hidden"
              >
                {/* Modal Header */}
                <div className="px-6 py-4 border-b border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260)] flex items-center gap-3">
                  <div className="p-2 rounded border border-[oklch(0.65_0.25_180/0.5)] bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.65_0.25_180)]">
                    {categoryIcons[selectedExample.category] || (
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                    )}
                  </div>
                  <div className="flex-1">
                    <h3 className="font-mono text-sm tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                      {selectedExample.name}
                    </h3>
                    <p className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] uppercase">
                      {selectedExample.category} workflow
                    </p>
                  </div>
                  <button
                    onClick={handleClose}
                    className="p-2 rounded hover:bg-[oklch(0.2_0.02_260)] transition-colors"
                  >
                    <svg className="w-5 h-5 text-[oklch(0.5_0.01_260)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                {/* Modal Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-4">
                  {/* Description */}
                  <div>
                    <h4 className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase mb-2">
                      What this workflow does
                    </h4>
                    <p className="font-mono text-sm text-[oklch(0.8_0.01_260)] leading-relaxed">
                      {selectedExample.description}
                    </p>
                  </div>

                  {/* Prompt Preview */}
                  <div>
                    <h4 className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase mb-2">
                      Prompt
                    </h4>
                    <div className="rounded border border-[oklch(0.22_0.03_260)] bg-[oklch(0.06_0.01_260)] p-4 max-h-[200px] overflow-y-auto">
                      <p className="font-mono text-xs text-[oklch(0.75_0.01_260)] leading-relaxed whitespace-pre-wrap">
                        {selectedExample.prompt}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Modal Footer */}
                <div className="px-6 py-4 border-t border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260)] flex items-center gap-3">
                  <button
                    onClick={handleClose}
                    className="flex-1 px-4 py-3 font-mono text-xs tracking-wider uppercase border border-[oklch(0.3_0.02_260)] bg-[oklch(0.12_0.02_260)] text-[oklch(0.6_0.01_260)] rounded hover:border-[oklch(0.4_0.02_260)] hover:text-[oklch(0.8_0.01_260)] transition-all"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleBuild}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-3 font-mono text-xs tracking-wider uppercase rounded border bg-[oklch(0.65_0.25_180/0.2)] border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180/0.3)] hover:shadow-[0_0_20px_oklch(0.65_0.25_180/0.3)] transition-all"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    Build Workflow
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </>
  );
};

export default ExamplesMenu;
