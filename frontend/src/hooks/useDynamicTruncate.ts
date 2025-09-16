'use client';

import { useState, useRef, useEffect, useCallback } from 'react';

interface UseDynamicTruncateOptions {
  reservedWidth?: number;  // Width reserved for other elements (icons, padding, etc.)
  minChars?: number;       // Minimum characters to always show
  fontSize?: number;       // Font size in pixels for width calculation
  fontFamily?: string;     // Font family for accurate measurement
  debounceMs?: number;     // Debounce delay in milliseconds
}

interface UseDynamicTruncateReturn {
  ref: React.RefObject<HTMLElement>;
  truncatedText: string;
  isTruncated: boolean;
}

/**
 * Custom hook for dynamically truncating text based on container width
 * Automatically adjusts truncation when container is resized
 */
export const useDynamicTruncate = (
  text: string,
  options: UseDynamicTruncateOptions = {}
): UseDynamicTruncateReturn => {
  const {
    reservedWidth = 0,
    minChars = 3,
    fontSize = 14,
    fontFamily = 'system-ui, -apple-system, sans-serif',
    debounceMs = 100
  } = options;

  const [truncatedText, setTruncatedText] = useState(text);
  const [isTruncated, setIsTruncated] = useState(false);
  const containerRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Create canvas for text measurement
  useEffect(() => {
    if (typeof window !== 'undefined' && !canvasRef.current) {
      canvasRef.current = document.createElement('canvas');
    }
  }, []);

  // Calculate text width using canvas
  const measureText = useCallback((str: string): number => {
    if (!canvasRef.current) return 0;

    const context = canvasRef.current.getContext('2d');
    if (!context) return 0;

    context.font = `${fontSize}px ${fontFamily}`;
    return context.measureText(str).width;
  }, [fontSize, fontFamily]);

  // Truncate text to fit within available width
  const truncateToFit = useCallback((availableWidth: number) => {
    if (!text) {
      setTruncatedText('');
      setIsTruncated(false);
      return;
    }

    const ellipsis = '...';
    const ellipsisWidth = measureText(ellipsis);
    const maxTextWidth = availableWidth - ellipsisWidth;

    // Check if text fits without truncation
    const fullTextWidth = measureText(text);
    if (fullTextWidth <= availableWidth) {
      setTruncatedText(text);
      setIsTruncated(false);
      return;
    }

    // Binary search for optimal truncation point
    let left = minChars;
    let right = text.length;
    let bestFit = minChars;

    while (left <= right) {
      const mid = Math.floor((left + right) / 2);
      const testText = text.substring(0, mid);
      const testWidth = measureText(testText);

      if (testWidth <= maxTextWidth) {
        bestFit = mid;
        left = mid + 1;
      } else {
        right = mid - 1;
      }
    }

    // Apply truncation
    const truncated = text.substring(0, bestFit) + ellipsis;
    setTruncatedText(truncated);
    setIsTruncated(true);
  }, [text, measureText, minChars]);

  // Handle resize with debouncing
  const handleResize = useCallback(() => {
    if (!containerRef.current) return;

    // Clear existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Set new debounced update
    debounceTimerRef.current = setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;

      const computedStyle = window.getComputedStyle(container);
      const paddingLeft = parseFloat(computedStyle.paddingLeft) || 0;
      const paddingRight = parseFloat(computedStyle.paddingRight) || 0;

      const availableWidth = container.clientWidth - paddingLeft - paddingRight - reservedWidth;

      if (availableWidth > 0) {
        truncateToFit(availableWidth);
      }
    }, debounceMs);
  }, [truncateToFit, reservedWidth, debounceMs]);

  // Set up ResizeObserver
  useEffect(() => {
    if (!containerRef.current) return;

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(containerRef.current);

    // Initial calculation
    handleResize();

    return () => {
      resizeObserver.disconnect();
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, [handleResize]);

  // Recalculate when text changes
  useEffect(() => {
    handleResize();
  }, [text, handleResize]);

  return {
    ref: containerRef as React.RefObject<HTMLElement>,
    truncatedText,
    isTruncated
  };
};