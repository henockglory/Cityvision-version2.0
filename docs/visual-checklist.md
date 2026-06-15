# Visual Checklist — Citévision v2 (50 points)

## Layout global
1. Navbar alignée horizontalement (hauteur fixe)
2. Sidebar largeur constante, items espacés 8px grid
3. MainContent padding symétrique (24px)
4. HologramBackground visible sans gêner la lisibilité
5. Pas de débordement horizontal sur 1920px
6. Pas de débordement sur 1366px
7. Scroll vertical fluide sur pages longues
8. Z-index correct (modales > navbar > background)

## Typographie
9. Titres PageHeader cohérents (taille/poids)
10. Labels formulaires alignés
11. Texte muted lisible en dark et light
12. Font mono pour IPs et codes
13. Pas de texte tronqué sans tooltip

## Couleurs et thèmes
14. Thème dark: bleu foncé + noir cyberpunk
15. Thème light: contraste suffisant
16. Toggle thème fonctionnel
17. Accent cohérent sur boutons primaires
18. Badges sévérité distincts
19. États hover/focus visibles
20. Pas d'emoji dans l'UI

## Icones
21. Lucide stroke-only (pas de fill coloré)
22. Tailles icônes 16/20/24px cohérentes
23. Icônes alignées verticalement avec texte
24. Logo oeil premium visible navbar/login

## Composants
25. cv-card border-radius uniforme
26. cv-btn-primary/secondary hauteur égale
27. cv-input largeur 100% dans formulaires
28. EmptyState centré avec CTA
29. ErrorState avec bouton retry
30. LoadingState spinner centré
31. StatCard grille dashboard alignée
32. SeverityBadge padding symétrique

## Pages critiques
33. Login: centré, logo, champs alignés
34. Setup wizard: étapes numérotées
35. Dashboard: stats vides = 0 (pas fictif)
36. Cameras: wizard 4 étapes lisible
37. Alerts: liste vide propre
38. Rules: builder sans chevauchement
39. ZoneEditor: canvas ratio correct
40. Settings: sections espacées
41. Audit: tableau colonnes alignées
42. SystemHealth: métriques lisibles

## Sons et onboarding
43. Clic robotique (mute toggle)
44. Détection sonore sur alerte WS
45. Skip tour visible et fonctionnel
46. Tour driver.js sans chevauchement bloquant

## Responsive
47. Sidebar repliée ou scroll mobile
48. Grille caméras 1/2/3 colonnes
49. Wizard utilisable sur tablette
50. Navbar actions accessibles petit écran

## Exécution
- Capturer chaque page en light et dark
- Noter PASS/FAIL par point dans test-report.md
