'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Image from 'next/image';
import { useExtendedBrainTheme } from './ArticleLayout';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Renders markdown content with extended brain article styling
 * Supports light/dark mode theming via ExtendedBrainThemeContext
 */
export function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  const { isLightMode } = useExtendedBrainTheme();

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Headings
          h1: ({ children }) => (
            <h1
              className={`text-3xl md:text-4xl font-bold mb-8 mt-12 first:mt-0 transition-colors duration-300 ${
                isLightMode ? 'text-[oklch(0.15_0.02_260)]' : 'text-[oklch(0.95_0.01_90)]'
              }`}
            >
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2
              className={`text-2xl md:text-3xl font-bold mb-6 mt-10 transition-colors duration-300 ${
                isLightMode ? 'text-[oklch(0.15_0.02_260)]' : 'text-[oklch(0.95_0.01_90)]'
              }`}
            >
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3
              className={`text-xl md:text-2xl font-semibold mb-4 mt-8 transition-colors duration-300 ${
                isLightMode ? 'text-[oklch(0.20_0.02_260)]' : 'text-[oklch(0.90_0.01_90)]'
              }`}
            >
              {children}
            </h3>
          ),

          // Paragraphs - unwrap images to avoid <figure> inside <p> hydration error
          p: ({ children, node }) => {
            // Check if the only child is an image (figure element)
            const childArray = React.Children.toArray(children);
            const hasOnlyImage =
              childArray.length === 1 &&
              React.isValidElement(childArray[0]) &&
              (childArray[0].type === 'img' ||
                (typeof childArray[0].type === 'function' &&
                  childArray[0].props?.node?.tagName === 'img'));

            // If paragraph only contains an image, return children directly (unwrapped)
            if (hasOnlyImage) {
              return <>{children}</>;
            }

            return (
              <p
                className={`text-lg leading-relaxed mb-4 transition-colors duration-300 ${
                  isLightMode ? 'text-[oklch(0.30_0.01_260)]' : 'text-[oklch(0.7_0.01_260)]'
                }`}
              >
                {children}
              </p>
            );
          },

          // Strong/Bold
          strong: ({ children }) => (
            <strong
              className={`font-semibold ${
                isLightMode ? 'text-[oklch(0.20_0.02_260)]' : 'text-[oklch(0.85_0.01_90)]'
              }`}
            >
              {children}
            </strong>
          ),

          // Emphasis/Italic
          em: ({ children }) => (
            <em
              className={`italic ${
                isLightMode ? 'text-[oklch(0.35_0.01_260)]' : 'text-[oklch(0.65_0.01_260)]'
              }`}
            >
              {children}
            </em>
          ),

          // Links
          a: ({ href, children }) => (
            <a
              href={href}
              className={`underline decoration-1 underline-offset-2 transition-colors ${
                isLightMode
                  ? 'text-[oklch(0.35_0.20_180)] hover:text-[oklch(0.25_0.25_180)]'
                  : 'text-[oklch(0.65_0.25_180)] hover:text-[oklch(0.75_0.25_180)]'
              }`}
              target={href?.startsWith('http') ? '_blank' : undefined}
              rel={href?.startsWith('http') ? 'noopener noreferrer' : undefined}
            >
              {children}
            </a>
          ),

          // Blockquotes
          blockquote: ({ children }) => (
            <blockquote
              className={`my-8 pl-6 border-l-4 transition-colors duration-300 ${
                isLightMode
                  ? 'border-[oklch(0.35_0.20_180)] bg-[oklch(0.96_0.01_260)]'
                  : 'border-[oklch(0.65_0.25_180)] bg-[oklch(0.12_0.02_260)]'
              } py-4 pr-4 rounded-r-lg`}
            >
              <div
                className={`italic ${
                  isLightMode ? 'text-[oklch(0.35_0.01_260)]' : 'text-[oklch(0.65_0.01_260)]'
                }`}
              >
                {children}
              </div>
            </blockquote>
          ),

          // Lists
          ul: ({ children }) => (
            <ul
              className={`list-disc list-inside my-4 space-y-2 ${
                isLightMode ? 'text-[oklch(0.30_0.01_260)]' : 'text-[oklch(0.7_0.01_260)]'
              }`}
            >
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol
              className={`list-decimal list-inside my-4 space-y-2 ${
                isLightMode ? 'text-[oklch(0.30_0.01_260)]' : 'text-[oklch(0.7_0.01_260)]'
              }`}
            >
              {children}
            </ol>
          ),
          li: ({ children }) => <li className="text-lg leading-relaxed">{children}</li>,

          // Code blocks
          code: ({ className, children, ...props }) => {
            const isInline = !className;
            if (isInline) {
              return (
                <code
                  className={`px-1.5 py-0.5 rounded font-mono text-sm ${
                    isLightMode
                      ? 'bg-[oklch(0.92_0.01_260)] text-[oklch(0.35_0.15_180)]'
                      : 'bg-[oklch(0.15_0.02_260)] text-[oklch(0.65_0.20_180)]'
                  }`}
                  {...props}
                >
                  {children}
                </code>
              );
            }

            return (
              <code
                className={`block p-4 rounded-lg overflow-x-auto font-mono text-sm ${
                  isLightMode
                    ? 'bg-[oklch(0.92_0.01_260)] text-[oklch(0.25_0.02_260)]'
                    : 'bg-[oklch(0.10_0.02_260)] text-[oklch(0.80_0.01_90)]'
                }`}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre
              className={`my-6 rounded-lg overflow-hidden ${
                isLightMode ? 'bg-[oklch(0.92_0.01_260)]' : 'bg-[oklch(0.10_0.02_260)]'
              }`}
            >
              {children}
            </pre>
          ),

          // Images
          img: ({ src, alt }) => {
            if (!src) return null;

            // Check if it's a CDN URL (external) or local
            const isExternal = src.startsWith('http');

            if (isExternal) {
              return (
                <figure className="my-8">
                  <div className="relative w-full aspect-video rounded-lg overflow-hidden">
                    <Image
                      src={src}
                      alt={alt || ''}
                      fill
                      className="object-cover"
                      sizes="(max-width: 768px) 100vw, 768px"
                    />
                  </div>
                  {alt && (
                    <figcaption
                      className={`text-center mt-3 text-sm ${
                        isLightMode ? 'text-[oklch(0.45_0.01_260)]' : 'text-[oklch(0.55_0.01_260)]'
                      }`}
                    >
                      {alt}
                    </figcaption>
                  )}
                </figure>
              );
            }

            // For local images, use regular img tag
            return (
              <figure className="my-8">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={src}
                  alt={alt || ''}
                  className="w-full rounded-lg"
                />
                {alt && (
                  <figcaption
                    className={`text-center mt-3 text-sm ${
                      isLightMode ? 'text-[oklch(0.45_0.01_260)]' : 'text-[oklch(0.55_0.01_260)]'
                    }`}
                  >
                    {alt}
                  </figcaption>
                )}
              </figure>
            );
          },

          // Horizontal rule
          hr: () => (
            <hr
              className={`my-12 border-t ${
                isLightMode ? 'border-[oklch(0.85_0.01_260)]' : 'border-[oklch(0.25_0.02_260)]'
              }`}
            />
          ),

          // Tables
          table: ({ children }) => (
            <div className="my-8 overflow-x-auto">
              <table
                className={`w-full border-collapse ${
                  isLightMode ? 'border-[oklch(0.85_0.01_260)]' : 'border-[oklch(0.25_0.02_260)]'
                }`}
              >
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th
              className={`px-4 py-2 text-left font-semibold border ${
                isLightMode
                  ? 'bg-[oklch(0.94_0.01_260)] border-[oklch(0.85_0.01_260)] text-[oklch(0.20_0.02_260)]'
                  : 'bg-[oklch(0.12_0.02_260)] border-[oklch(0.25_0.02_260)] text-[oklch(0.90_0.01_90)]'
              }`}
            >
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td
              className={`px-4 py-2 border ${
                isLightMode
                  ? 'border-[oklch(0.85_0.01_260)] text-[oklch(0.30_0.01_260)]'
                  : 'border-[oklch(0.25_0.02_260)] text-[oklch(0.7_0.01_260)]'
              }`}
            >
              {children}
            </td>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
