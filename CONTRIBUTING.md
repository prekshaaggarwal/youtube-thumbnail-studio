# Contributing

Thanks for your interest in improving **YouTube Thumbnail Studio**.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
pip install pytest
```

## Run locally

```bash
python app.py
```

Open `http://127.0.0.1:8080/`.

## Before opening a PR

- Run tests:

```bash
python -m pytest tests/ -v
```

- Keep changes focused and documented.
- Avoid committing secrets (`.env`, keys, credentials).

## Commit style

- Use clear, action-oriented commit messages.
- Prefer small, reviewable commits over one large commit.
