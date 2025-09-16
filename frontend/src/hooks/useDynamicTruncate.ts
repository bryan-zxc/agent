'use client';

import { useState, useRef, useEffect, useCallback } from 'react';

interface UseDynamicTruncateOptions {
  minChars?: number;       // Minimum characters to always show
  fontSize?: number;       // Font size in pixels for width calculation
  fontFamily?: string;     // Font family for accurate measurement
  debounceMs?: number;     // Debounce delay in milliseconds
  getReservedWidth?: (parentElement: HTMLElement) => number; // Custom function to calculate reserved width
}

interface UseDynamicTruncateReturn {
  parentRef: React.RefObject<HTMLElement>;
  textRef: React.RefObject<HTMLElement>;
  truncatedText: string;
  isTruncated: boolean;
}

/**
 * Custom hook for dynamically truncating text based on parent container width
 * Measures the parent container and calculates space available for text
 */
export const useDynamicTruncate = (
  text: string,
  options: UseDynamicTruncateOptions = {}
): UseDynamicTruncateReturn => {
  const {
    minChars = 3,
    fontSize = 14,
    fontFamily = 'system-ui, -apple-system, sans-serif',
    debounceMs = 50,
    getReservedWidth
  } = options;

  const [truncatedText, setTruncatedText] = useState(text);
  const [isTruncated, setIsTruncated] = useState(false);
  const parentRef = useRef<HTMLElement>(null);
  const textRef = useRef<HTMLElement>(null);
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

  // Calculate reserved width from actual DOM elements
  const calculateReservedWidth = useCallback((parentElement: HTMLElement): number => {
    if (getReservedWidth) {
      return getReservedWidth(parentElement);
    }

    // Default calculation: sum up all non-text elements' widths
    let reserved = 0;
    const children = Array.from(parentElement.children);

    children.forEach(child => {
      // Skip the text element itself
      if (child === textRef.current || child.contains(textRef.current)) {
        return;
      }

      // Add width of other elements
      const rect = child.getBoundingClientRect();
      reserved += rect.width;
    });

    // Add gaps (flex gap or margins)
    const computedStyle = window.getComputedStyle(parentElement);
    const gap = parseFloat(computedStyle.gap) || 0;
    const childCount = children.filter(c => c !== textRef.current && !c.contains(textRef.current)).length;
    reserved += gap * Math.max(0, childCount); // Gaps between elements

    // Add padding
    const paddingLeft = parseFloat(computedStyle.paddingLeft) || 0;
    const paddingRight = parseFloat(computedStyle.paddingRight) || 0;
    reserved += paddingLeft + paddingRight;

    return reserved;
  }, [getReservedWidth]);

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
    if (!parentRef.current) return;

    // Clear existing timer
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    // Set new debounced update
    debounceTimerRef.current = setTimeout(() => {
      const parent = parentRef.current;
      if (!parent) return;

      // Get parent's actual width
      const parentRect = parent.getBoundingClientRect();
      const parentWidth = parentRect.width;

      // Calculate reserved width from actual elements
      const reserved = calculateReservedWidth(parent);

      // Available width for text
      const availableWidth = Math.max(0, parentWidth - reserved);

      if (availableWidth > 0) {
        truncateToFit(availableWidth);
      }
    }, debounceMs);
  }, [truncateToFit, calculateReservedWidth, debounceMs]);

  // Set up ResizeObserver on parent
  useEffect(() => {
    if (!parentRef.current) return;

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(parentRef.current);

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

  // Also observe text element in case it gets added/removed from DOM
  useEffect(() => {
    if (!textRef.current || !parentRef.current) return;

    // Trigger recalculation when text element is ready
    handleResize();
  }, [handleResize]);

  return {
    parentRef: parentRef as React.RefObject<HTMLElement>,
    textRef: textRef as React.RefObject<HTMLElement>,
    truncatedText,
    isTruncated
  };
};