'use client';

import { formatDistanceToNow } from 'date-fns';
import {
  DocumentTextIcon,
  PhotoIcon,
  DocumentArrowDownIcon,
  BellIcon,
  TableCellsIcon,
  ArrowTopRightOnSquareIcon,
  ChatBubbleLeftRightIcon,
  StarIcon,
} from '@heroicons/react/24/outline';
import type { Delivery } from '../../types/task';
import { StructuredDataRenderer } from './DataRenderers';
import { isStructuredDataContent } from '../../types/structured-data';

/**
 * Parse timestamp as UTC. Server returns timestamps without 'Z' suffix,
 * which JavaScript interprets as local time. This function ensures UTC interpretation.
 */
function parseAsUTC(timestamp: string): Date {
  // If timestamp doesn't end with Z or timezone offset, append Z to force UTC
  if (!timestamp.endsWith('Z') && !timestamp.match(/[+-]\d{2}:\d{2}$/)) {
    return new Date(timestamp + 'Z');
  }
  return new Date(timestamp);
}

interface DeliveryCardProps {
  delivery: Delivery;
}

const typeConfig: Record<Delivery['type'], {
  icon: typeof DocumentTextIcon;
  label: string;
}> = {
  text: { icon: DocumentTextIcon, label: 'Text' },
  file: { icon: DocumentArrowDownIcon, label: 'File' },
  notification: { icon: BellIcon, label: 'Notification' },
  data: { icon: TableCellsIcon, label: 'Data' },
  image: { icon: PhotoIcon, label: 'Image' },
};

/**
 * Structured item from analysis (e.g., HackerNews story, article, product)
 */
interface StructuredItem {
  title: string;
  score?: number;
  url?: string;
  summary?: string;
  comments?: number;
  metadata?: Record<string, unknown>;
}

/**
 * Structured output format from subagents
 */
interface StructuredOutput {
  status?: 'success' | 'error';
  content?: string;
  findings?: string;
  items?: StructuredItem[];
  key_points?: string[];
  insights?: string[];
  error?: string;
  // Other possible fields
  [key: string]: unknown;
}

/**
 * Extract structured output from delivery content.
 * Backend normalizes outputs, so this just validates the structure.
 */
function parseStructuredOutput(content: unknown): StructuredOutput | null {
  if (typeof content !== 'object' || content === null) {
    return null;
  }

  const obj = content as Record<string, unknown>;

  // Check if it has structured output fields
  if ('content' in obj || 'items' in obj || 'key_points' in obj || 'insights' in obj || 'summary' in obj || 'findings' in obj) {
    return obj as StructuredOutput;
  }

  return null;
}

/**
 * Extract meaningful text from content object
 */
function extractMeaningfulContent(content: unknown): string | null {
  if (typeof content !== 'object' || content === null) {
    return null;
  }

  const obj = content as Record<string, unknown>;

  // Check for HTML content
  if (typeof obj.output === 'string' && obj.output.trim().startsWith('<') && obj.output.includes('html')) {
    return '[HTML content fetched]';
  }

  // Extract meaningful text fields
  if (typeof obj.content === 'string') return obj.content;
  if (typeof obj.summary === 'string') return obj.summary;
  if (typeof obj.findings === 'string') return obj.findings;
  if (typeof obj.result === 'string') return obj.result;
  if (typeof obj.output === 'string') return obj.output;

  return null;
}

/**
 * Extract image URL from content.
 */
function extractImageUrl(content: unknown): string | null {
  if (typeof content === 'string') {
    if (content.match(/\.(png|jpg|jpeg|gif|webp|svg)$/i) || content.startsWith('data:image')) {
      return content;
    }
    return null;
  }

  if (typeof content !== 'object' || content === null) {
    return null;
  }

  const obj = content as Record<string, unknown>;
  const urlFields = ['url', 'image_url', 'src', 'image', 'path', 'image_base64'];

  for (const field of urlFields) {
    const val = obj[field];
    if (typeof val === 'string') {
      if (val.match(/\.(png|jpg|jpeg|gif|webp|svg)$/i) || val.startsWith('data:image') || val.startsWith('http')) {
        return val;
      }
    }
  }

  return null;
}

/**
 * Extract file information from content, including base64 encoded files.
 */
function extractFileInfo(content: unknown, stepName?: string): {
  filename: string;
  url?: string;
  size?: string;
  base64?: string;
  mimeType?: string;
} | null {
  if (typeof content !== 'object' || content === null) {
    return null;
  }

  const obj = content as Record<string, unknown>;

  // Check for base64 encoded PDF
  if (typeof obj.pdf_base64 === 'string') {
    return {
      filename: stepName ? `${stepName}.pdf` : 'document.pdf',
      base64: obj.pdf_base64,
      mimeType: 'application/pdf',
    };
  }

  // Check for generic base64 file
  if (typeof obj.file_base64 === 'string') {
    const mimeType = typeof obj.mime_type === 'string' ? obj.mime_type : 'application/octet-stream';
    const ext = mimeType.split('/')[1] || 'bin';
    return {
      filename: stepName ? `${stepName}.${ext}` : `file.${ext}`,
      base64: obj.file_base64,
      mimeType,
    };
  }

  const file = obj.file as Record<string, unknown> | undefined;

  // Check nested file object first
  if (file && typeof file === 'object') {
    const filename = file.filename || file.name;
    if (typeof filename === 'string') {
      return {
        filename,
        url: typeof file.cdn_url === 'string' ? file.cdn_url : undefined,
        size: typeof file.size === 'string' ? file.size : undefined,
      };
    }
  }

  // Check top-level fields
  const filename = obj.filename || obj.name || obj.file_name;
  if (typeof filename === 'string') {
    return {
      filename,
      url: typeof obj.url === 'string' ? obj.url : undefined,
      size: typeof obj.size === 'string' ? obj.size : undefined,
    };
  }

  return null;
}

/**
 * Create a download link from base64 content.
 */
function downloadBase64File(base64: string, filename: string, mimeType: string) {
  try {
    // Decode base64 to binary
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }

    // Create blob and download
    const blob = new Blob([bytes], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error('Failed to download file:', e);
  }
}

/**
 * Render a single structured item as a card (e.g., HN story, article)
 */
function ItemCard({ item, index }: { item: StructuredItem; index: number }) {
  return (
    <div className="p-4 rounded-lg bg-[var(--muted)]/50 border border-[var(--border)] hover:border-[oklch(0.65_0.25_180/0.3)] transition-colors">
      <div className="flex items-start gap-3">
        {/* Rank number */}
        <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[oklch(0.65_0.25_180/0.15)] text-[oklch(0.65_0.25_180)] text-xs font-medium flex items-center justify-center">
          {index + 1}
        </span>

        <div className="flex-1 min-w-0">
          {/* Title with optional link */}
          <div className="flex items-start gap-2">
            {item.url ? (
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-[var(--foreground)] hover:text-[oklch(0.65_0.25_180)] transition-colors line-clamp-2"
              >
                {item.title}
                <ArrowTopRightOnSquareIcon className="inline-block w-3 h-3 ml-1 opacity-50" />
              </a>
            ) : (
              <span className="text-sm font-medium text-[var(--foreground)] line-clamp-2">
                {item.title}
              </span>
            )}
          </div>

          {/* Summary */}
          {item.summary && (
            <p className="mt-1 text-xs text-[var(--muted-foreground)] line-clamp-2 text-body">
              {item.summary}
            </p>
          )}

          {/* Metadata badges */}
          <div className="mt-2 flex items-center gap-3 text-xs text-[var(--muted-foreground)]">
            {item.score !== undefined && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[oklch(0.8_0.15_80/0.2)] text-[oklch(0.5_0.15_80)]">
                <StarIcon className="w-3 h-3" />
                {item.score.toLocaleString()}
              </span>
            )}
            {item.comments !== undefined && (
              <span className="inline-flex items-center gap-1">
                <ChatBubbleLeftRightIcon className="w-3 h-3" />
                {item.comments.toLocaleString()}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Render key points as a bullet list
 */
function KeyPointsList({ points }: { points: string[] }) {
  return (
    <ul className="space-y-2 mt-3">
      {points.map((point, i) => (
        <li key={i} className="flex items-start gap-2 text-sm text-[var(--foreground)] text-body">
          <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-[oklch(0.65_0.25_180)] mt-2" />
          <span>{point}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * DeliveryCard - Shows a single delivery (result) from execution.
 * Renders structured JSON output beautifully.
 */
export function DeliveryCard({ delivery }: DeliveryCardProps) {
  const config = typeConfig[delivery.type];
  const Icon = config.icon;

  // Check if this is a primary result (text/data) vs supporting (file/notification)
  const isPrimaryResult = delivery.type === 'text' || delivery.type === 'data';

  const renderContent = () => {
    // Check for backend-provided object_type (fast path results, workspace data)
    if (isStructuredDataContent(delivery.content)) {
      return <StructuredDataRenderer content={delivery.content} />;
    }

    // Try to parse as structured output first (items, key_points, insights)
    const structured = parseStructuredOutput(delivery.content);

    switch (delivery.type) {
      case 'text':
      case 'data': {
        if (structured) {
          // Get the main text content from either content or findings
          const mainText = structured.content || structured.findings;

          return (
            <div className="space-y-4">
              {/* Main content text (from content or findings field) */}
              {mainText && (
                <p className="text-sm text-[var(--foreground)] leading-relaxed whitespace-pre-wrap text-body">
                  {mainText}
                </p>
              )}

              {/* Items list (stories, articles, etc.) */}
              {structured.items && structured.items.length > 0 && (
                <div className="space-y-3">
                  {structured.items.map((item, i) => (
                    <ItemCard key={i} item={item} index={i} />
                  ))}
                </div>
              )}

              {/* Key points */}
              {structured.key_points && structured.key_points.length > 0 && (
                <KeyPointsList points={structured.key_points} />
              )}

              {/* Insights */}
              {structured.insights && structured.insights.length > 0 && (
                <div className="pt-3 border-t border-[var(--border)]">
                  <p className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide mb-2">
                    Key Insights
                  </p>
                  <KeyPointsList points={structured.insights} />
                </div>
              )}

              {/* Error state */}
              {structured.status === 'error' && structured.error && (
                <p className="text-sm text-red-500">{structured.error}</p>
              )}
            </div>
          );
        }

        // Fallback for unstructured content - try to extract meaningful text
        const meaningfulText = extractMeaningfulContent(delivery.content);
        if (meaningfulText) {
          return (
            <p className="text-sm text-[var(--foreground)] leading-relaxed whitespace-pre-wrap text-body">
              {meaningfulText}
            </p>
          );
        }

        // Last resort - show as formatted JSON but only if it's reasonably small
        const contentStr = JSON.stringify(delivery.content, null, 2);
        if (contentStr.length > 2000) {
          return (
            <p className="text-sm text-[var(--muted-foreground)]">
              Complex data output (too large to display)
            </p>
          );
        }
        return (
          <pre className="text-xs overflow-x-auto bg-[var(--muted)] p-3 rounded-lg text-[var(--foreground)]">
            {contentStr}
          </pre>
        );
      }

      case 'image': {
        const imageUrl = extractImageUrl(delivery.content);
        if (imageUrl) {
          return (
            <div className="rounded-lg overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={imageUrl}
                alt={delivery.title}
                className="w-full h-auto"
              />
            </div>
          );
        }
        return (
          <p className="text-sm text-[var(--muted-foreground)]">
            Image not available
          </p>
        );
      }

      case 'file': {
        const fileInfo = extractFileInfo(delivery.content, delivery.stepName);
        const hasDownload = fileInfo?.url || fileInfo?.base64;

        return (
          <div className="flex items-center gap-3 p-3 bg-[var(--muted)] rounded-lg">
            <DocumentArrowDownIcon className="w-8 h-8 text-[var(--muted-foreground)]" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-[var(--foreground)] truncate">
                {fileInfo?.filename || 'Download file'}
              </p>
              {fileInfo?.size && (
                <p className="text-xs text-[var(--muted-foreground)]">
                  {fileInfo.size}
                </p>
              )}
            </div>
            {hasDownload && (
              fileInfo.base64 ? (
                <button
                  onClick={() => downloadBase64File(
                    fileInfo.base64!,
                    fileInfo.filename,
                    fileInfo.mimeType || 'application/octet-stream'
                  )}
                  className="px-3 py-1.5 text-xs font-medium text-[oklch(0.65_0.25_180)] bg-[oklch(0.65_0.25_180/0.1)] rounded hover:bg-[oklch(0.65_0.25_180/0.2)] transition-colors"
                >
                  Download
                </button>
              ) : (
                <a
                  href={fileInfo.url}
                  download
                  className="px-3 py-1.5 text-xs font-medium text-[oklch(0.65_0.25_180)] bg-[oklch(0.65_0.25_180/0.1)] rounded hover:bg-[oklch(0.65_0.25_180/0.2)] transition-colors"
                >
                  Download
                </a>
              )
            )}
          </div>
        );
      }

      case 'notification': {
        const structured = parseStructuredOutput(delivery.content);
        return (
          <div className="flex items-center gap-2 text-sm text-[oklch(0.78_0.22_150)]">
            <BellIcon className="w-4 h-4" />
            <span>{structured?.content || 'Notification sent successfully'}</span>
          </div>
        );
      }

      default:
        return (
          <p className="text-sm text-[var(--muted-foreground)]">
            Content available
          </p>
        );
    }
  };

  return (
    <div
      className={`
        rounded-xl overflow-hidden transition-all duration-200
        ${isPrimaryResult
          ? 'border-2 border-[oklch(0.65_0.25_180/0.2)] bg-gradient-to-br from-[var(--card)] to-[oklch(0.65_0.25_180/0.03)] shadow-sm'
          : 'border border-[var(--border)] bg-[var(--card)]'
        }
      `}
    >
      {/* Header - cleaner, more focused */}
      <div className={`
        flex items-center gap-3 px-4 py-3
        ${isPrimaryResult
          ? 'border-b border-[oklch(0.65_0.25_180/0.1)]'
          : 'border-b border-[var(--border)] bg-[var(--muted)]/30'
        }
      `}>
        <div className={`
          w-9 h-9 rounded-xl flex items-center justify-center
          ${isPrimaryResult
            ? 'bg-[oklch(0.65_0.25_180/0.15)]'
            : 'bg-[var(--muted)]'
          }
        `}>
          <Icon className={`
            w-4 h-4
            ${isPrimaryResult ? 'text-[oklch(0.65_0.25_180)]' : 'text-[var(--muted-foreground)]'}
          `} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-[var(--foreground)] truncate">
            {delivery.title}
          </h3>
        </div>
        <span className="text-xs text-[var(--muted-foreground)] tabular-nums">
          {formatDistanceToNow(parseAsUTC(delivery.createdAt), { addSuffix: true })}
        </span>
      </div>

      {/* Content - more breathing room for primary results */}
      <div className={isPrimaryResult ? 'p-5' : 'p-4'}>
        {renderContent()}
      </div>
    </div>
  );
}
