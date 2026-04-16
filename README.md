# Easycash Tracker

Scraper personnel de suivi de prix sur **Easycash.fr** (catégorie jeu vidéo), avec interface web locale et alertes Discord.

## Installation

Prérequis : Python 3.11+ (testé sur 3.13).

```bash
cd C:\Users\chartdy\Desktop\Perso\Scraper

# Créer le venv
py -m venv .venv

# Activer (Git Bash)
source .venv/Scripts/activate
# Activer (PowerShell)
# .\.venv\Scripts\Activate.ps1

# Installer les dépendances
pip install -r requirements.txt

# Copier la config
cp .env.example .env
# Puis éditer .env (notamment DISCORD_WEBHOOK_URL si besoin)
```

## Commandes CLI (phase 1)

Initialiser la base de données :

```bash
python -m scraper.cli init-db
```

Lister les catégories JV connues :

```bash
python -m scraper.cli categories
```

Lancer un scraping de test sur une catégorie :

```bash
python -m scraper.cli fetch jeux-video --pages 3
python -m scraper.cli fetch consoles/sony --pages 2
```

Lister les derniers articles vus :

```bash
python -m scraper.cli list --limit 20
```

## Structure

```
scraper/
├── config.py              # Config via pydantic-settings
├── cli.py                 # CLI Typer
├── core/
│   ├── client.py          # Client HTTP async (httpx) rate-limité
│   ├── parser.py          # Extraction dataLayer GTM
│   └── categories.py      # Catégories JV Easycash
├── db/
│   ├── models.py          # SQLAlchemy 2.0
│   ├── session.py
│   └── repository.py
└── services/
    └── scraper_service.py # Orchestration fetch → parse → save

tests/
├── fixtures/              # HTML figé pour tests non-régression
└── test_parser.py
```

## Limitations connues (cf. investigation phase 0)

Easycash n'expose **pas** sur le web public l'état (TBE/BE/Correct), le magasin ni le commentaire vendeur par exemplaire — `bons-plans.easycash.fr` est une vitrine catalogue à prix de référence. Le scraper suit donc : **prix catalogue, présence/disparition, nouveaux produits**. Pas d'état ni de magasin.
