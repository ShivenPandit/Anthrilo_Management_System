'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

interface StatCardProps {
  title: string;
  value: string | number;
  icon?: React.ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'purple' | 'indigo' | 'emerald';
}

const gradients: Record<string, string> = {
  blue: 'from-blue-500/10 to-indigo-500/10 dark:from-blue-500/20 dark:to-indigo-500/20',
  green: 'from-emerald-500/10 to-teal-500/10 dark:from-emerald-500/20 dark:to-teal-500/20',
  yellow: 'from-amber-500/10 to-orange-500/10 dark:from-amber-500/20 dark:to-orange-500/20',
  red: 'from-rose-500/10 to-red-500/10 dark:from-rose-500/20 dark:to-red-500/20',
  purple: 'from-violet-500/10 to-purple-500/10 dark:from-violet-500/20 dark:to-purple-500/20',
  indigo: 'from-indigo-500/10 to-blue-500/10 dark:from-indigo-500/20 dark:to-blue-500/20',
  emerald: 'from-emerald-500/10 to-green-500/10 dark:from-emerald-500/20 dark:to-green-500/20',
};

const iconColors: Record<string, string> = {
  blue: 'bg-blue-500/15 text-blue-600 dark:text-blue-400',
  green: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  yellow: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  red: 'bg-rose-500/15 text-rose-600 dark:text-rose-400',
  purple: 'bg-violet-500/15 text-violet-600 dark:text-violet-400',
  indigo: 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400',
  emerald: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
};

export function StatCard({ title, value, icon, trend, color = 'blue' }: StatCardProps) {
  return (
    <div className={`card bg-gradient-to-br ${gradients[color]} hover:scale-[1.02] transition-all duration-300`}>
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-500 dark:text-slate-400 truncate">{title}</p>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1.5 truncate">{value}</p>
          {trend && (
            <p className={`text-xs mt-1.5 font-semibold flex items-center gap-1 ${trend.isPositive ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'
              }`}>
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                {trend.isPositive
                  ? <path fillRule="evenodd" d="M12 7a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0V8.414l-4.293 4.293a1 1 0 01-1.414 0L8 10.414l-4.293 4.293a1 1 0 01-1.414-1.414l5-5a1 1 0 011.414 0L11 10.586 14.586 7H12z" clipRule="evenodd" />
                  : <path fillRule="evenodd" d="M12 13a1 1 0 100 2h5a1 1 0 001-1V9a1 1 0 10-2 0v2.586l-4.293-4.293a1 1 0 00-1.414 0L8 9.586 3.707 5.293a1 1 0 00-1.414 1.414l5 5a1 1 0 001.414 0L11 9.414 14.586 13H12z" clipRule="evenodd" />
                }
              </svg>
              {Math.abs(trend.value)}%
            </p>
          )}
        </div>
        {icon && (
          <div className={`${iconColors[color]} p-3 rounded-xl text-2xl flex-shrink-0`}>
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  message?: string;
}

export function LoadingSpinner({ size = 'md', message }: LoadingSpinnerProps) {
  const sizeClasses = { sm: 'w-5 h-5', md: 'w-10 h-10', lg: 'w-14 h-14' };
  return (
    <div className="flex flex-col items-center justify-center py-10 sm:py-16">
      <div className={`${sizeClasses[size]} border-[3px] border-slate-200 dark:border-slate-700 border-t-primary-500 rounded-full animate-spin`}></div>
      {message && <p className="mt-3 sm:mt-4 text-sm text-slate-500 dark:text-slate-400 text-center px-4">{message}</p>}
    </div>
  );
}

// Progress Loader

export interface ProgressStage { at: number; label: string; }

interface ProgressLoaderProps {
  loading: boolean;
  stages?: ProgressStage[];
  skeletonRows?: number;
  progressPercent?: number;
  progressLabel?: string;
}

const DEFAULT_STAGES: ProgressStage[] = [
  { at: 0, label: 'Connecting to Unicommerce…' },
  { at: 12, label: 'Initializing export job…' },
  { at: 30, label: 'Fetching data…' },
  { at: 55, label: 'Processing results…' },
  { at: 75, label: 'Building report…' },
  { at: 92, label: 'Finalizing…' },
];

export function ProgressLoader({
  loading,
  stages,
  skeletonRows = 5,
  progressPercent,
  progressLabel,
}: ProgressLoaderProps) {
  const [progress, setProgress] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const resetRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stageList = stages ?? DEFAULT_STAGES;
  const isControlled = typeof progressPercent === 'number';

  useEffect(() => {
    if (resetRef.current) {
      clearTimeout(resetRef.current);
      resetRef.current = null;
    }

    if (isControlled) {
      const next = Math.max(0, Math.min(100, Number(progressPercent) || 0));
      setProgress(next);
      return () => {
        if (timerRef.current) clearInterval(timerRef.current);
        if (resetRef.current) clearTimeout(resetRef.current);
      };
    }

    if (loading) {
      setProgress(0);
      let p = 0;
      timerRef.current = setInterval(() => {
        const inc = p < 30 ? 3 : p < 60 ? 1.5 : p < 80 ? 0.6 : 0.2;
        p = Math.min(p + inc, 92);
        setProgress(p);
      }, 400);
    } else {
      if (timerRef.current) clearInterval(timerRef.current);
      setProgress((prev) => {
        if (prev <= 0) return prev;
        resetRef.current = setTimeout(() => setProgress(0), 500);
        return 100;
      });
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (resetRef.current) clearTimeout(resetRef.current);
    };
  }, [isControlled, loading, progressPercent]);

  if (!loading && progress === 0) return null;

  const stageLabel = progressLabel || stageList.slice().reverse().find(s => progress >= s.at)?.label || '';

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-sm p-6 space-y-4"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {stageLabel}
        </span>
        <span className="text-sm font-bold text-primary-600 dark:text-primary-400 tabular-nums">
          {Math.round(progress)}%
        </span>
      </div>
      <div className="h-2.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-primary-500 to-primary-600"
          initial={{ width: 0 }}
          animate={{ width: `${progress}%` }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
        />
      </div>
      {loading && skeletonRows > 0 && (
        <div className="space-y-2 pt-1">
          {Array.from({ length: skeletonRows }).map((_, i) => (
            <div key={i} className="h-8 bg-slate-100 dark:bg-slate-800/60 rounded animate-pulse"
              style={{ opacity: 1 - i * 0.14 }} />
          ))}
        </div>
      )}
    </motion.div>
  );
}

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  icon?: React.ReactNode;
}

export function EmptyState({ title, description, action, icon }: EmptyStateProps) {
  return (
    <div className="text-center py-12 sm:py-16 px-4">
      {icon && <div className="flex justify-center mb-4 text-slate-300 dark:text-slate-600 text-5xl">{icon}</div>}
      <h3 className="text-base font-semibold text-slate-900 dark:text-white mb-1">{title}</h3>
      {description && <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">{description}</p>}
      {action && <button onClick={action.onClick} className="btn btn-primary">{action.label}</button>}
    </div>
  );
}

interface PageHeaderProps {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export function PageHeader({ title, description, action }: PageHeaderProps) {
  return (
    <div className="mb-5 sm:mb-7 lg:mb-8 flex flex-col gap-4 sm:gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl sm:text-2xl lg:text-3xl 2xl:text-4xl font-bold text-slate-900 dark:text-white break-words">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>}
      </div>
      {action && (
        <button onClick={action.onClick} className="btn btn-primary w-full sm:w-auto sm:flex-shrink-0">
          {action.label}
        </button>
      )}
    </div>
  );
}

interface ErrorPanelProps {
  message: string;
}

export function ErrorPanel({ message }: ErrorPanelProps) {
  return (
    <div className="card bg-rose-50 dark:bg-rose-900/20 border-rose-200 dark:border-rose-800/50 mb-4">
      <div className="flex items-start sm:items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-rose-100 dark:bg-rose-900/40 flex items-center justify-center flex-shrink-0">
          <svg className="w-4 h-4 text-rose-600 dark:text-rose-400" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
        </div>
        <p className="text-sm text-rose-700 dark:text-rose-300 break-words">{message}</p>
      </div>
    </div>
  );
}
