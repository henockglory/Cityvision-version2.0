import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp, FlaskConical } from 'lucide-react';
import type { ConditionNode } from '@/lib/conditionTree';
import { buildScenariosFromTree, simulateScenarios } from '@/lib/conditionSimulator';

interface ConditionLogicSimulatorProps {
  tree: ConditionNode;
}

export default function ConditionLogicSimulator({ tree }: ConditionLogicSimulatorProps) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);

  const lang = i18n.language.startsWith('en') ? 'en' : 'fr';
  const scenarios = buildScenariosFromTree(tree, t, lang);
  if (scenarios.length === 0) return null;

  const rows = simulateScenarios(tree, scenarios, t);

  return (
    <div className="rounded-xl border border-cv-border/60 bg-cv-deep/30 overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-cv-accent/5 transition-colors"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-cv-text">
          <FlaskConical className="w-4 h-4 text-cv-accent" />
          {t('rules.studio.simulator.toggle')}
        </span>
        {open ? <ChevronUp className="w-4 h-4 text-cv-muted" /> : <ChevronDown className="w-4 h-4 text-cv-muted" />}
      </button>
      {open && (
        <div className="px-4 pb-4 overflow-x-auto">
          <p className="text-xs text-cv-muted mb-3">{t('rules.studio.simulator.hint')}</p>
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="text-cv-muted border-b border-cv-border/50">
                <th className="text-left py-2 pr-3 font-medium">{t('rules.studio.simulator.colScenario')}</th>
                <th className="text-left py-2 pr-3 font-medium w-24">{t('rules.studio.simulator.colResult')}</th>
                <th className="text-left py-2 font-medium">{t('rules.studio.simulator.colWhy')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-cv-border/30 last:border-0">
                  <td className="py-2.5 pr-3 text-cv-text align-top">{row.label}</td>
                  <td className="py-2.5 pr-3 align-top">
                    <span
                      className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold ${
                        row.matches
                          ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                          : 'bg-cv-border/30 text-cv-muted border border-cv-border/50'
                      }`}
                    >
                      {row.matches ? t('rules.studio.simulator.yes') : t('rules.studio.simulator.no')}
                    </span>
                  </td>
                  <td className="py-2.5 text-cv-muted align-top leading-relaxed">{row.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
