import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink } from 'lucide-react';
import PageHeader from '@/components/ui/PageHeader';

export type DocDocId = 'overview' | 'architectures';

const DOC_SRC: Record<DocDocId, { src: string; titleKey: string; titleFallback: string }> = {
  overview: {
    src: '/docs/architectures/overview.html',
    titleKey: 'nav.docsOverview',
    titleFallback: 'Overview',
  },
  architectures: {
    src: '/docs/architectures/index.html',
    titleKey: 'nav.docsArchitectures',
    titleFallback: 'Architectures',
  },
};

interface DocumentationFrameProps {
  doc: DocDocId;
}

export default function DocumentationFrame({ doc }: DocumentationFrameProps) {
  const { t } = useTranslation();
  const meta = useMemo(() => DOC_SRC[doc], [doc]);
  const title = t(meta.titleKey, meta.titleFallback);

  return (
    <div className="flex flex-col gap-3">
      <PageHeader
        title={title}
        actions={
          <a
            href={meta.src}
            target="_blank"
            rel="noreferrer"
            className="cv-btn-secondary text-xs inline-flex items-center gap-1.5"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            {t('nav.docsOpenNewTab', 'Ouvrir dans un onglet')}
          </a>
        }
      />
      <div className="cv-card overflow-hidden border-cv-border/60">
        <iframe
          title={title}
          src={meta.src}
          className="w-full border-0 bg-white"
          style={{ height: 'calc(100vh - 9.5rem)', minHeight: 520 }}
        />
      </div>
    </div>
  );
}
