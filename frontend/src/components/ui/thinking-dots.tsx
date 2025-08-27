'use client';

import { useEffect, useState } from 'react';

export function ThinkingDots() {
  const [dots, setDots] = useState('.');

  useEffect(() => {
    const interval = setInterval(() => {
      setDots(current => {
        if (current === '.') return '..';
        if (current === '..') return '...';
        return '.';
      });
    }, 500);

    return () => clearInterval(interval);
  }, []);

  return <span>{dots}</span>;
}