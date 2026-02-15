'use client';

import React, { useState } from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';

interface YamlDiffViewerProps {
  oldYaml: string;
  newYaml: string;
  oldTitle?: string;
  newTitle?: string;
}

export const YamlDiffViewer: React.FC<YamlDiffViewerProps> = ({
  oldYaml,
  newYaml,
  oldTitle = 'Original',
  newTitle = 'Updated',
}) => {
  const [splitView, setSplitView] = useState(true);

  // Custom styles for dark mode support
  const customStyles = {
    variables: {
      dark: {
        diffViewerBackground: '#1f2937',
        diffViewerColor: '#f3f4f6',
        addedBackground: '#065f461a',
        addedColor: '#34d399',
        removedBackground: '#7f1d1d1a',
        removedColor: '#f87171',
        wordAddedBackground: '#065f4633',
        wordRemovedBackground: '#7f1d1d33',
        addedGutterBackground: '#065f4633',
        removedGutterBackground: '#7f1d1d33',
        gutterBackground: '#111827',
        gutterBackgroundDark: '#0d1117',
        highlightBackground: '#3b82f61a',
        highlightGutterBackground: '#3b82f633',
        codeFoldGutterBackground: '#374151',
        codeFoldBackground: '#1f2937',
        emptyLineBackground: '#1f2937',
        gutterColor: '#6b7280',
        addedGutterColor: '#34d399',
        removedGutterColor: '#f87171',
        codeFoldContentColor: '#9ca3af',
        diffViewerTitleBackground: '#111827',
        diffViewerTitleColor: '#f3f4f6',
        diffViewerTitleBorderColor: '#374151',
      },
      light: {
        diffViewerBackground: '#ffffff',
        diffViewerColor: '#1f2937',
        addedBackground: '#dcfce7',
        addedColor: '#166534',
        removedBackground: '#fee2e2',
        removedColor: '#991b1b',
        wordAddedBackground: '#bbf7d0',
        wordRemovedBackground: '#fecaca',
        addedGutterBackground: '#dcfce7',
        removedGutterBackground: '#fee2e2',
        gutterBackground: '#f9fafb',
        gutterBackgroundDark: '#f3f4f6',
        highlightBackground: '#dbeafe',
        highlightGutterBackground: '#bfdbfe',
        codeFoldGutterBackground: '#e5e7eb',
        codeFoldBackground: '#f9fafb',
        emptyLineBackground: '#f9fafb',
        gutterColor: '#6b7280',
        addedGutterColor: '#166534',
        removedGutterColor: '#991b1b',
        codeFoldContentColor: '#4b5563',
        diffViewerTitleBackground: '#f9fafb',
        diffViewerTitleColor: '#1f2937',
        diffViewerTitleBorderColor: '#e5e7eb',
      },
    },
    line: {
      padding: '4px 8px',
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
      fontSize: '13px',
    },
    gutter: {
      padding: '4px 8px',
      minWidth: '40px',
    },
  };

  // Detect dark mode
  const isDark = typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
      <div className="flex items-center justify-between p-3 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Comparing Changes
        </h3>
        <button
          onClick={() => setSplitView(!splitView)}
          className="px-3 py-1 text-xs rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        >
          {splitView ? 'Unified View' : 'Split View'}
        </button>
      </div>

      <div className="overflow-auto max-h-[600px]">
        <ReactDiffViewer
          oldValue={oldYaml}
          newValue={newYaml}
          splitView={splitView}
          compareMethod={DiffMethod.LINES}
          useDarkTheme={isDark}
          leftTitle={oldTitle}
          rightTitle={newTitle}
          styles={customStyles}
          showDiffOnly={false}
        />
      </div>
    </div>
  );
};

export default YamlDiffViewer;
