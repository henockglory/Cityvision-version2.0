import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import ModalPortal from '@/components/ui/ModalPortal';
import ZoneEditor from '@/pages/ZoneEditor';

interface DemoZoneEditorModalProps {
  open: boolean;
  onClose: () => void;
  cameraId?: string;
  streamSrc?: string;
}

export default function DemoZoneEditorModal({
  open,
  onClose,
  cameraId,
  streamSrc,
}: DemoZoneEditorModalProps) {
  const { t } = useTranslation();

  if (!open) return null;

  return (
    <ModalPortal>
      <div
        className="cv-modal-overlay fixed inset-0 z-[120] flex flex-col bg-black/70 p-2 md:p-4"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
        role="presentation"
      >
        <div className="cv-card cv-demo-zone-modal flex flex-col w-full max-w-6xl mx-auto h-[95vh] overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-cv-border shrink-0">
            <h2 className="font-display text-lg font-semibold">{t('demoCenter.zoneModalTitle')}</h2>
            <button type="button" onClick={onClose} className="cv-btn-ghost p-2" aria-label={t('common.close')}>
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="flex-1 overflow-auto p-4">
            <ZoneEditor
              embedded
              fixedCameraId={cameraId}
              fixedStreamSrc={streamSrc}
              onClose={onClose}
            />
          </div>
        </div>
      </div>
    </ModalPortal>
  );
}
