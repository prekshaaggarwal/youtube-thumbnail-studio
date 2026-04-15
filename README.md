# YouTube Thumbnail Studio

[![CI: GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)](.github/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-ML-F7931E?logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)
[![SQLite](https://img.shields.io/badge/SQLite-DB-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Pillow](https://img.shields.io/badge/Pillow-Image_Processing-3776AB)](https://python-pillow.org/)

**End-to-end thumbnail optimization studio for YouTube creators:** collect channel history, train a thumbnail-aware model with optional Studio analytics, score or A/B-test thumbnails, and ship designs through a **local web app** (auth, reporting, visual editor, and free AI composer).

> **Interview angle:** This project demonstrates ownership across the full ML product lifecycle: data ingestion, feature engineering, model training, inference, web UX, auth, persistence, testing, and CI.

---

## Try It Now

- **Live Demo:** [https://youtube-thumbnail-studio.onrender.com](https://youtube-thumbnail-studio.onrender.com)
- **GitHub:** [https://github.com/prekshaaggarwal/youtube-thumbnail-studio](https://github.com/prekshaaggarwal/youtube-thumbnail-studio)

---

## What This Project Does

YouTube Thumbnail Studio is an end-to-end ML + web app that helps creators improve thumbnail decisions with a practical workflow:

- create thumbnail concepts,
- score a design,
- compare two versions (A/B),
- and iterate quickly in one interface.

---

## Core Features

- **Create your thumbnail** (visual editor with image background support, autosave, undo/redo, and keyboard shortcuts)
- **Thumbnail Rater** (predictive scoring)
- **A/B Tester** (head-to-head comparison and recommendation)
- **AI Creator** (fast concept generation)
- **Auth + Workspace** (email/password, optional Google OAuth, project/report flows)

---

## Screenshots

![Dashboard and workspace overview](docs/screenshots/dashboard-overview.png)
![Create your thumbnail editor](docs/screenshots/create-thumbnail-editor.png)
![A/B tester](docs/screenshots/ab-test-result.png)
![AI creator generated thumbnail](docs/screenshots/ai-creator-output.png)

---

## Run Locally

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8080/`.

---

## Deploy (Render)

This repo includes `render.yaml` for blueprint deployment.

1. Push code to GitHub.
2. In Render: **New +** -> **Blueprint**.
3. Select this repo and deploy.

Render runs:

`gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`

Health check:

`/health`

---

## Tech Stack

- Python, Flask
- scikit-learn, pandas, numpy
- SQLite
- Pillow
- GitHub Actions (CI)

---

## Testing

```bash
python -m pytest tests/ -v
```

---

## License

MIT — see [LICENSE](LICENSE).
