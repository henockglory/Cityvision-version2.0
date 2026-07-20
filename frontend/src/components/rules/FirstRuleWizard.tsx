import { Link } from 'react-router-dom';
import { Camera, Bell, Workflow, ArrowRight, AlertTriangle } from 'lucide-react';
import { useDashboardSummary, useAlerts, useRules, useCameras } from '@/hooks/api/queries';

export default function FirstRuleWizard() {
  const summary = useDashboardSummary();
  const { data: cameras = [] } = useCameras();
  const { data: rules = [] } = useRules();
  const { data: alerts = [] } = useAlerts();

  const openAlerts = alerts.filter((a) => !a.acknowledged).length;
  const inactiveRules = rules.filter((r) => !r.enabled).length;
  const offlineCameras = cameras.filter((c) => c.status === 'offline').length;

  const steps = [
    {
      done: cameras.length > 0,
      label: 'Ajouter une caméra',
      to: '/cameras',
      icon: Camera,
    },
    {
      done: rules.some((r) => r.enabled),
      label: 'Configurer une règle',
      to: '/rules',
      icon: Workflow,
    },
    {
      done: openAlerts === 0 && alerts.length > 0,
      label: 'Acquitter les alertes',
      to: '/alerts',
      icon: Bell,
    },
  ];

  if ((summary.data?.cameras_total ?? 0) > 0 && rules.length > 0 && openAlerts === 0) return null;

  return (
    <div className="cv-card p-5 mb-6 border-cv-accent/20">
      <h2 className="font-display text-lg font-semibold mb-3">Assistant de configuration</h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        {steps.map((step) => (
          <Link
            key={step.to}
            to={step.to}
            className={`flex items-center gap-3 p-3 rounded-lg border transition-colors ${
              step.done ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-cv-border hover:border-cv-accent/30'
            }`}
          >
            <step.icon className={`w-5 h-5 ${step.done ? 'text-emerald-500' : 'text-cv-accent'}`} />
            <span className="text-sm font-medium">{step.label}</span>
            {!step.done && <ArrowRight className="w-4 h-4 ml-auto text-cv-muted" />}
          </Link>
        ))}
      </div>
      {(offlineCameras > 0 || inactiveRules > 0 || openAlerts > 0) && (
        <div className="flex flex-wrap gap-3 text-xs">
          {offlineCameras > 0 && (
            <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
              <AlertTriangle className="w-3.5 h-3.5" />
              {offlineCameras} caméra(s) offline
            </span>
          )}
          {inactiveRules > 0 && (
            <span className="text-cv-muted">{inactiveRules} règle(s) inactive(s)</span>
          )}
          {openAlerts > 0 && (
            <Link to="/alerts" className="text-cv-accent underline">
              {openAlerts} alerte(s) non acquittée(s)
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
