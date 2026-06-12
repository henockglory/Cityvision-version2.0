import { useState, useRef } from 'react';
import { Stage, Layer, Line, Circle, Rect } from 'react-konva';
import type { KonvaEventObject } from 'konva/lib/Node';
import { useTranslation } from 'react-i18next';
import { Plus, Trash2, Save, Square, Pentagon } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';
import { useSound } from '@/hooks/useSound';
import type { Zone } from '@/types';

const STAGE_WIDTH = 800;
const STAGE_HEIGHT = 450;

export default function ZoneEditor() {
  const { t } = useTranslation();
  const { playClick } = useSound();
  const [zones, setZones] = useState<Zone[]>([
    { id: 'z1', name: 'Zone intrusion', points: [100, 100, 300, 100, 300, 250, 100, 250], color: '#00D4FF', cameraId: 'cam-1' },
    { id: 'z2', name: 'Zone parking', points: [400, 150, 650, 150, 650, 350, 400, 350], color: '#FF6B35', cameraId: 'cam-2' },
  ]);
  const [selectedZone, setSelectedZone] = useState<string | null>('z1');
  const [tool, setTool] = useState<'select' | 'rect' | 'polygon'>('select');
  const [drawing, setDrawing] = useState<number[]>([]);
  const stageRef = useRef(null);

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
      { id, name: `Zone ${prev.length + 1}`, points: [50, 50, 200, 50, 200, 150, 50, 150], color: '#00D4FF', cameraId: 'cam-1' },
    ]);
    setSelectedZone(id);
  };

  const deleteZone = () => {
    if (!selectedZone) return;
    playClick();
    setZones((prev) => prev.filter((z) => z.id !== selectedZone));
    setSelectedZone(null);
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
        <div className="lg:col-span-3 cv-card overflow-hidden">
          <div className="bg-cv-deep flex justify-center">
            <Stage
              ref={stageRef}
              width={STAGE_WIDTH}
              height={STAGE_HEIGHT}
              onClick={handleStageClick}
              className="cursor-crosshair"
            >
              <Layer>
                <Rect width={STAGE_WIDTH} height={STAGE_HEIGHT} fill="#050A12" />
                {Array.from({ length: Math.ceil(STAGE_WIDTH / 32) }).map((_, i) => (
                  <Line key={`v${i}`} points={[i * 32, 0, i * 32, STAGE_HEIGHT]} stroke="rgba(0,212,255,0.05)" strokeWidth={1} />
                ))}
                {Array.from({ length: Math.ceil(STAGE_HEIGHT / 32) }).map((_, i) => (
                  <Line key={`h${i}`} points={[0, i * 32, STAGE_WIDTH, i * 32]} stroke="rgba(0,212,255,0.05)" strokeWidth={1} />
                ))}

                {zones.map((zone) => (
                  <Line
                    key={zone.id}
                    points={zone.points}
                    closed
                    fill={`${zone.color}22`}
                    stroke={zone.id === selectedZone ? '#00D4FF' : zone.color}
                    strokeWidth={zone.id === selectedZone ? 2 : 1}
                    onClick={() => { playClick(); setSelectedZone(zone.id); }}
                  />
                ))}

                {drawing.length >= 2 && (
                  <Line points={drawing} stroke="#00D4FF" strokeWidth={1} dash={[4, 4]} />
                )}

                {zones.flatMap((zone) =>
                  zone.points.reduce<number[][]>((acc, _, i) => {
                    if (i % 2 === 0) acc.push([zone.points[i], zone.points[i + 1]]);
                    return acc;
                  }, []).map((pt, i) => (
                    <Circle
                      key={`${zone.id}-${i}`}
                      x={pt[0]}
                      y={pt[1]}
                      radius={4}
                      fill={zone.color}
                      stroke="#fff"
                      strokeWidth={1}
                    />
                  ))
                )}
              </Layer>
            </Stage>
          </div>
        </div>

        <div className="space-y-4">
          <div className="cv-card p-4">
            <h3 className="font-display text-sm font-semibold mb-3">{t('zoneEditor.tools')}</h3>
            <div className="flex flex-col gap-2">
              {[
                { id: 'select' as const, icon: Square, label: 'Sélection' },
                { id: 'rect' as const, icon: Square, label: 'Rectangle' },
                { id: 'polygon' as const, icon: Pentagon, label: 'Polygone' },
              ].map((t_) => (
                <button
                  key={t_.id}
                  type="button"
                  onClick={() => { playClick(); setTool(t_.id); setDrawing([]); }}
                  className={`cv-btn-secondary text-xs justify-start ${tool === t_.id ? 'border-cv-accent/40' : ''}`}
                >
                  <t_.icon className="w-3 h-3" />
                  {t_.label}
                </button>
              ))}
            </div>
          </div>

          <div className="cv-card p-4">
            <h3 className="font-display text-sm font-semibold mb-3">Zones</h3>
            <div className="space-y-2">
              {zones.map((zone) => (
                <button
                  key={zone.id}
                  type="button"
                  onClick={() => { playClick(); setSelectedZone(zone.id); }}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                    selectedZone === zone.id ? 'bg-cv-accent/10 border border-cv-accent/20' : 'hover:bg-cv-accent/5'
                  }`}
                >
                  <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: zone.color }} />
                  {zone.name}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
