Replace Your Workflow With This

Create:

.github/workflows/deploy.yml

Put this inside:

name: Build and Deploy

on:
  schedule:
    - cron: "*/15 * * * *"
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Run LMP script
        run: |
          python your_script.py

      - name: Setup Pages
        uses: actions/configure-pages@v4

      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./Realist

      - name: Deploy
        uses: actions/deploy-pages@v4

Replace your_script.py with whatever generates your site.