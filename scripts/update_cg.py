name: Sync Inara Community Goals

on:
  schedule:
    # Esegue il controllo ogni 3 ore
    - cron: '0 */3 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  update-community-goals:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests beautifulsoup4

      - name: Fetch and parse Inara Community Goals
        run: python scripts/update_cg.py

      - name: Commit and push if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add community-goals.json
          if ! git diff --cached --quiet; then
            git commit -m "chore(cg): update active community goals from Inara"
            git push
          else
            echo "Nessun cambiamento nei Community Goal."
          fi

community-goals
[
  {
    "title": "Nessun Community Goal attivo al momento",
    "status": "STANDBY",
    "systems": [
      "Galassia"
    ],
    "description": "Il feed automatico è collegato a Inara. Quando verrà avviato un nuovo Community Goal attivo comparirà automaticamente in questa sezione.",
    "rewards": "Crediti e ricompense in base al tier raggiunto."
  }
]
