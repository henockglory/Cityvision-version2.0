# Frontend — CitéVision v2

SPA React + TypeScript, design dark premium avec Tailwind CSS et Vite.

## Stack

| Composant | Version |
|-----------|---------|
| React | 18 |
| TypeScript | 5.x |
| Vite | 6.x |
| Tailwind CSS | 3.x |
| React Query | 5.x (TanStack) |
| Zustand | 5.x (état global) |
| React Router | 6.x |
| react-i18next | FR/EN |

## Structure

```
frontend/src/
├── api/              ← Client HTTP (axios)
├── components/
│   ├── layout/       ← AppLayout, Navbar, Sidebar, MainContent
│   ├── rules/        ← RuleFlowBuilder, RuleCatalogPanel
│   ├── evidence/     ← EvidenceMedia, EvidenceLightbox
│   └── ui/           ← Composants réutilisables (Modal, PageShell, StatCard…)
├── hooks/
│   ├── api/          ← React Query queries/mutations
│   └── use*.ts       ← Hooks utilitaires
├── i18n/             ← Traductions FR/EN
├── pages/            ← Dashboard, Cameras, Alerts, Events, Rules, Settings…
├── routes/           ← Routing (React Router)
├── stores/           ← Zustand stores (auth, ui)
└── types/            ← Types TypeScript partagés
```

## Démarrage

```bash
cd frontend
npm install
npm run dev       # Dev server → http://localhost:5174
npm run build     # Build de production → dist/
npm run preview   # Preview du build
```

## Variables d'environnement

Créer un fichier `.env` dans `frontend/` (ou à la racine) :

```env
VITE_API_URL=http://localhost:8081
```

## Design System

Les variables CSS et classes Tailwind personnalisées sont dans `src/index.css`.

Couleurs principales :
- `cv-deep` — fond principal
- `cv-surface` — cartes et panneaux
- `cv-accent` — bleu accent (`#3b82f6`)
- `cv-border` — bordures subtiles
