'use client';

import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeHighlight from 'rehype-highlight';
import rehypeKatex from 'rehype-katex';

interface RichMarkdownRendererProps {
  content: string;
  className?: string;
}

interface MermaidDiagramProps {
  chart: string;
}

const MermaidDiagram: React.FC<MermaidDiagramProps> = ({ chart }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string>('');

  useEffect(() => {
    const renderMermaid = async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        
        mermaid.initialize({
          startOnLoad: false,
          theme: 'dark',
          securityLevel: 'loose',
          themeVariables: {
            darkMode: true,
            background: 'transparent',
            primaryColor: '#3b82f6',
            primaryTextColor: '#e5e7eb',
            primaryBorderColor: '#6b7280',
            lineColor: '#6b7280',
            secondaryColor: '#374151',
            tertiaryColor: '#1f2937'
          }
        });

        const id = `mermaid-${Math.random().toString(36).substring(2, 9)}`;
        const { svg } = await mermaid.render(id, chart);
        setSvg(svg);
      } catch (error) {
        console.error('Error rendering mermaid diagram:', error);
        setError(`Error rendering diagram: ${error}`);
      }
    };

    renderMermaid();
  }, [chart]);

  if (error) {
    return (
      <div className="my-4 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
        <pre className="text-red-400 text-sm">{error}</pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-4 p-4 bg-gray-100 dark:bg-gray-800 rounded-lg">
        <div className="animate-pulse text-sm text-gray-500 dark:text-gray-400">Rendering diagram...</div>
      </div>
    );
  }

  return (
    <div 
      className="my-4 flex justify-center"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
};

export const RichMarkdownRenderer: React.FC<RichMarkdownRendererProps> = ({ 
  content, 
  className = '' 
}) => {
  return (
    <div className={`prose dark:prose-invert max-w-none text-sm leading-relaxed ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeHighlight, rehypeKatex]}
        components={{
          // Enhanced pre blocks - let highlight.js handle colors
          pre({ children }) {
            return (
              <pre className="p-4 rounded-lg overflow-x-auto text-sm my-4">
                {children}
              </pre>
            );
          },
          
          // Custom code block handling for mermaid
          code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';
            
            if (!inline && language === 'mermaid') {
              return <MermaidDiagram chart={String(children).replace(/\n$/, '')} />;
            }
            
            if (inline) {
              return (
                <code className="bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded text-sm font-mono" {...props}>
                  {children}
                </code>
              );
            }
            
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          
          // Enhanced blockquotes
          blockquote({ children }) {
            return (
              <blockquote className="border-l-4 border-primary/30 pl-4 italic text-gray-500 dark:text-gray-400 my-4 bg-gray-100 dark:bg-gray-800/30 py-2 rounded-r">
                {children}
              </blockquote>
            );
          },
          
          // Enhanced tables with better styling
          table({ children }) {
            return (
              <div className="overflow-x-auto my-4">
                <table className="min-w-full border border-border rounded-lg bg-card">
                  {children}
                </table>
              </div>
            );
          },
          
          thead({ children }) {
            return (
              <thead className="bg-gray-100 dark:bg-gray-800">
                {children}
              </thead>
            );
          },
          
          th({ children }) {
            return (
              <th className="border border-border px-4 py-3 text-left font-semibold">
                {children}
              </th>
            );
          },
          
          td({ children }) {
            return (
              <td className="border border-border px-4 py-2">
                {children}
              </td>
            );
          },
          
          // Enhanced headers with better spacing
          h1({ children }) {
            return (
              <h1 className="text-2xl font-bold mt-8 mb-4 first:mt-0 pb-2 border-b border-border">
                {children}
              </h1>
            );
          },
          
          h2({ children }) {
            return (
              <h2 className="text-xl font-bold mt-6 mb-3 pb-1 border-b border-border/50">
                {children}
              </h2>
            );
          },
          
          h3({ children }) {
            return (
              <h3 className="text-lg font-bold mt-5 mb-2">
                {children}
              </h3>
            );
          },
          
          h4({ children }) {
            return (
              <h4 className="text-base font-semibold mt-4 mb-2">
                {children}
              </h4>
            );
          },
          
          // Enhanced lists with better spacing
          ul({ children }) {
            return (
              <ul className="my-4 space-y-2 ml-6 list-disc marker:text-primary">
                {children}
              </ul>
            );
          },
          
          ol({ children }) {
            return (
              <ol className="my-4 space-y-2 ml-6 list-decimal marker:text-primary">
                {children}
              </ol>
            );
          },
          
          li({ children }) {
            return (
              <li className="leading-relaxed">
                {children}
              </li>
            );
          },
          
          // Enhanced links with security
          a({ href, children }) {
            return (
              <a 
                href={href} 
                className="text-primary hover:text-primary/80 underline underline-offset-2 transition-colors" 
                target="_blank" 
                rel="noopener noreferrer"
              >
                {children}
              </a>
            );
          },
          
          // Task list support (GitHub flavored markdown)
          input({ type, checked, ...props }) {
            if (type === 'checkbox') {
              return (
                <input 
                  type="checkbox" 
                  checked={checked} 
                  disabled 
                  className="mr-2 accent-primary" 
                  {...props} 
                />
              );
            }
            return <input type={type} {...props} />;
          },
          
          // Horizontal rules
          hr() {
            return <hr className="my-8 border-t border-border" />;
          },
          
          // Enhanced paragraphs
          p({ children }) {
            return (
              <p className="mb-4 leading-relaxed">
                {children}
              </p>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};