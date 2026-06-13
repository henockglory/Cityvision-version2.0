import { useState } from 'react';
import { Stage, Layer, Line, Circle, Rect } from 'react-konva';
import type { KonvaEventObject } from 'konva/lib/Node';
import { useTranslation } from 'react-i18next';
import { Plus, Trash2, Save, Square, Pentagon, PenTool } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import EmptyState from '@/components/EmptyState';
import { useSound } from '@/hooks/useSound';
import type { Zone } from '@/types';

const STAGE_WIDTH = 800;
const STAGE_HEIGHT = 450;

export default function ZoneEditor() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const [zones, setZones] = useState<Zone[]>([]);
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [tool, setTool] = useState<'select' | 'rect' | 'polygon'>('select');
  const [drawing, setDrawing] = useState<number[]>([]);

  const handleStageClick = (e: KonvaEventObject<MouseEvent>) => {
    if (tool !== 'polygon') return;
    const stage = e.target.getStage();
    if (!stage) return;
    const pos = stage.getPointerPosition();
    if (!pos) return;
    playClick();
    setDrawing((prev) => [...prev, pos.x, pos.y]);
  };

  const addRectZone = () => {
    playClick();
    const id = `z${Date.now()}`;
    setZones((prev) => [
      ...prev,
      { id, name: `Zone ${prev.length + 1}`, points: [50, 50, 200, 50, 200, 150, 50, 150], color: '#00D4FF', cameraId: '' },
    ]);
    setSelectedZone(id);
  };

  const deleteZone = () => {
    if (!selectedZone) return;
    playClick();
    setZones((prev) => prev.filter((z) => z.id !== selectedZone));
    setSelectedZone(null);
  };

  const finishPolygon = () => {
    if (drawing.length < 6) return;
    playClick();
    const id = `z${Date.now()}`;
    setZones((prev) => [
      ...prev,
      { id, name: `Zone ${prev.length + 1}`, points: drawing, color: '#00D4FF', cameraId: '' },
    ]);
    setDrawing([]);
    setSelectedZone(id);
    setTool('select');
  };

  return (
    <div>
      <PageHeader
        title={t('zoneEditor.title')}
        actions={
          <div className="flex gap-2">
            <button type="button" onClick={addRectZone} className="cv-btn-secondary text-xs">
              <Plus className="w-3 h-3" />
              {t('zoneEditor.addZone')}
            </button>
            <button type="button" onClick={deleteZone} disabled={!selectedZone} className="cv-btn-secondary text-xs">
              <Trash2 className="w-3 h-3" />
              {t('zoneEditor.deleteZone')}
            </button>
            <button type="button" onClick={() => playClick()} className="cv-btn-primary text-xs">
              <Save className="w-3 h-3" />
              {t('zoneEditor.save')}
            </button>
          </div>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-3 cv-card p-4 overflow-hidden">
          <div className="flex gap-2 mb-4">
            <span className="text-xs text-cv-muted uppercase tracking-wider">{t('zoneEditor.tools')}</span>
            {[
              { id: 'select' as const, icon: Square },
              { id: 'rect' as const, icon: Square },
              { id: 'polygon' as const, icon: Pentagon },
            ].map((btn) => (
              <button
                key={btn.id}
                type="button"
                onClick={() => { playClick(); setTool(btn.id); }}
                className={`cv-btn-ghost p-2 ${tool === btn.id ? 'text-cv-accent bg-cv-accent/10' : ''}`}
              >
                <btn.icon className="w-4 h-4" />
              </button>
            ))}
            {tool === 'polygon' && drawing.length >= 6 && (
              <button type="button" onClick={finishPolygon} className="cv-btn-secondary text-xs ml-auto">
                Finish polygon
              </button>
            )}
          </div>

          <div className="rounded-lg overflow-hidden border border-cv-border bg-cv-deep">
            <Stage
              width={STAGE_WIDTH}
              height={STAGE_HEIGHT}
              onClick={handleStageClick}
              className="mx-auto"
            >
              <Layer>
                <Rect x={0} y={0} width={STAGE_WIDTH} height={STAGE_HEIGHT} fill="#050A12" />
                {zones.map((zone) => (
                  <Line
                    key={zone.id}
                    points={zone.points}
                    closed
                    stroke={zone.id === selectedZone ? '#00D4FF' : zone.color}
                    strokeWidth={zone.id === selectedZone ? 2 : 1}
                    fill={`${zone.color}22`}
                    onClick={() => { playClick(); setSelectedZone(zone.id); }}
                  />
                ))}
                {drawing.length > 0 && (
                  <>
                    <Line points={drawing} stroke="#00D4FF" strokeWidth={1} />
                    {drawing.reduce<number[][]>((acc, _, i) => {
                      if (i % 2 === 0) acc.push([drawing[i], drawing[i + 1]]);
                      return acc;
                    }, []).map(([x, y], i) => (
                      <Circle key={i} x={x} y={y} radius={4} fill="#00D4FF" />
                    ))}
                  </>
                )}
              </Layer>
            </Stage>
          </div>
        </div>

        <div className="cv-card p-4">
          {zones.length === 0 ? (
            <EmptyState title={t('zoneEditor.empty')} hint={t('zoneEditor.emptyHint')} icon={PenTool} />
          ) : (
            <div className="space-y-2">
              {zones.map((zone) => (
                <button
                  key={zone.id}
                  type="button"
                  onClick={() => { playClick(); setSelectedZone(zone.id); }}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedZone === zone.id ? 'border-cv-accent bg-cv-accent/10' : 'border-cv-border hover:border-cv-accent/30'
                  }`}
                >
                  <p className="font-medium text-sm">{zone.name}</p>
                  <p className="text-xs text-cv-muted">{zone.points.length / 2} points</p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
