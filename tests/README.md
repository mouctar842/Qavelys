# Tests transversaux

Tests unitaires et d’intégration proches du code : backend/tests et les dossiers de tests des applications Django, frontend/src/*.test.tsx.

Les tests navigateur réels sont dans `frontend/e2e/erp.spec.ts`. Depuis la racine Windows : `./infrastructure/e2e.ps1`. Le lanceur crée une base PostgreSQL dédiée et utilise les ports 8001/5174 ; il conserve les données et le rapport dans `.local/e2e-runs/<identifiant>`. Il refuse de réutiliser une base existante. Aucun backend simulé. Consulter `docs/e2e-acceptance.md` pour le contrat et `docs/progress.md` pour les résultats effectivement exécutés.
