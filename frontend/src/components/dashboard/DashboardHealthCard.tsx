'use client';

type HealthStatus = 'healthy' | 'warning' | 'error';

interface DashboardHealthCardProps {
  status: HealthStatus;
  drift: number;
  window: 'closed' | 'open';
  timezone: string;
}

const statusClass: Record<HealthStatus, string> = {
  healthy: 'text-emerald-600 bg-emerald-50 border-emerald-200 dark:text-emerald-400 dark:bg-emerald-900/20 dark:border-emerald-800',
  warning: 'text-amber-600 bg-amber-50 border-amber-200 dark:text-amber-400 dark:bg-amber-900/20 dark:border-amber-800',
  error: 'text-rose-600 bg-rose-50 border-rose-200 dark:text-rose-400 dark:bg-rose-900/20 dark:border-rose-800',
};

export function DashboardHealthCard({ status, drift, window, timezone }: DashboardHealthCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-slate-900 dark:text-white">Dashboard Health</p>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${statusClass[status]}`}>
          {status}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-slate-600 dark:text-slate-300">
        <div>
          <p className="text-slate-400">Drift</p>
          <p className="font-semibold">{drift.toFixed(3)}%</p>
        </div>
        <div>
          <p className="text-slate-400">Window</p>
          <p className="font-semibold">{window}</p>
        </div>
        <div>
          <p className="text-slate-400">Timezone</p>
          <p className="font-semibold">{timezone}</p>
        </div>
      </div>
    </div>
  );
}

