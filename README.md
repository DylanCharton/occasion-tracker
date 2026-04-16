# Easycash Tracker

Outil personnel d'**agrégation et de suivi des prix** sur [Easycash.fr](https://www.easycash.fr) (marché de l'occasion jeux vidéo).

Collecte les articles du catalogue, historise les prix et envoie des alertes Discord en cas de baisse.

## Fonctionnalités

- **Collecte du catalogue** — Récupère les articles par plateforme (PS5, PS4, Switch, DS, 3DS, ...)
- **Historique des prix** — Chaque passage enregistre un snapshot ; les courbes sont visibles dans l'interface
- **Watchlist** — Suis les articles qui t'intéressent avec des seuils d'alerte personnalisés
- **Alertes Discord** — Notification automatique quand un prix descend sous ton seuil
- **Recherches sauvegardées** — Enregistre des filtres de recherche et reçois une alerte quand un nouvel article correspond
- **Planificateur intégré** — Rafraîchissement automatique à intervalle configurable, tant que l'app tourne
- **Interface web locale** — Dashboard, recherche, watchlist, alertes, paramètres (Streamlit)

## Quick Setup

### Prérequis

- **Python 3.11+** ([python.org](https://www.python.org/downloads/))
- **Windows 10/11** (testé sur Windows 11)

### Installation

```
git clone <repo> C:\Users\<toi>\Desktop\Perso\Scraper
cd C:\Users\<toi>\Desktop\Perso\Scraper
```

Ou double-clic sur **`setup.bat`** qui fait tout automatiquement, ou manuellement :

```bash
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m scraper.cli init-db
copy .env.example .env
```

### Configuration (optionnel)

Édite `.env` pour activer les alertes Discord :

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123.../abc...
```

Pour créer un webhook : Paramètres serveur Discord > Intégrations > Webhooks > Nouveau.

### Lancement

Double-clic sur **`run.bat`** ou :

```bash
.venv\Scripts\activate
streamlit run streamlit_app.py
```

L'interface s'ouvre automatiquement dans le navigateur sur `http://localhost:8501`.

## Utilisation

### Première collecte

1. Sur le **Dashboard**, sélectionne tes plateformes (PS5, PS4, Switch, DS, 3DS...)
2. Clique **Lancer l'analyse** — la collecte complète prend quelques minutes
3. Les articles apparaissent dans **Recherche**

### Suivi des prix

1. **Recherche** — Filtre par mots-clés, plateforme, prix max
2. Clique **Suivre** sur un article pour l'ajouter à la **Watchlist**
3. Dans le détail d'un article, configure les **seuils d'alerte** (% de baisse ou prix cible)

### Automatisation

1. Va dans **Paramètres** > ajoute une tâche planifiée (ex: toutes les 6h, 2 pages)
2. Le planificateur tourne en arrière-plan tant que l'application est ouverte
3. Les baisses détectées déclenchent automatiquement une notification Discord

## Commandes CLI

```bash
python -m scraper.cli full               # Analyse complète (toutes plateformes)
python -m scraper.cli full --jeux-only    # Jeux vidéo uniquement
python -m scraper.cli fetch jeux-video    # Collecte rapide d'une catégorie
python -m scraper.cli list --limit 20     # Derniers articles en base
python -m scraper.cli categories          # Catégories disponibles
python -m scraper.cli init-db             # Initialiser la base de données
```

## Stack technique

| Composant | Technologie |
|---|---|
| Interface web | Streamlit |
| Graphiques | Plotly |
| Base de données | SQLite (via SQLAlchemy 2.0) |
| Client HTTP | httpx (async, HTTP/2) |
| Notifications | discord-webhook |
| Planificateur | APScheduler |
| Parsing HTML | selectolax |
| Config | pydantic-settings + .env |

## Limitations connues

L'**état du produit** (Très bon / Bon / Correct), le **magasin** et le **commentaire vendeur** ne sont pas exposés par Easycash sur le web public. L'outil suit les **prix catalogue**, la **présence/disparition** des articles et détecte les **baisses de prix**.
