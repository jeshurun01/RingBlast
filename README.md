# RingBlast

Application Streamlit pour visualiser des plans de forage **iRedes DRPPlan XML** et produire des rapports PDF, tableaux de charge CSV et archives ZIP. Une CLI permet aussi le traitement par lots.

## Windows — double-click to start (recommended)

1. Install **Python 3.12, 64-bit**, including the **Windows Python launcher** (`py`), from [python.org](https://www.python.org/downloads/windows/). A per-user installation is sufficient; do not run RingBlast as administrator. The launcher creates the environment, but does **not** download or install Python itself.
2. Clone this repository (or extract the complete source ZIP) into a writable local folder. For an existing clone, save your local changes before updating it. Do not copy only the `.bat` file or run it inside a ZIP archive.
3. Open the `RingBlast` folder in File Explorer and **double-click `Run_RingBlast.bat`**. No PowerShell commands or environment activation are needed.
4. On the first run, keep the console open while it creates `.venv` with `py -3.12` and installs `requirements.txt`. This needs internet access and may take several minutes. All pip commands use the private environment, not system Python.
5. Open **http://127.0.0.1:8501** if the browser does not open automatically. Keep the console window open while using the app. Press **Ctrl+C** to stop it (confirm the batch termination prompt if Windows asks), or close the console.

For later runs, double-click the same file again. Dependencies are not reinstalled unless `requirements.txt` changes or the environment is recreated. Folder names containing spaces are supported, and a shortcut can start it from another working directory. Keep the launcher inside the repository; create a shortcut rather than moving the file.

**Troubleshooting and limitations**

- If Python is missing, install Python 3.12 with the launcher option, then try again. `py -0p` lists available Python installations. Python 3.13/3.14 alone is not sufficient for this launcher.
- If installation fails, check the pip error, internet connection and any corporate proxy restrictions, then double-click again. An unsuccessful install is retried, not marked complete. No administrator privileges or PowerShell execution-policy changes are required.
- If `.venv` is damaged, was moved from another machine/folder, or uses another Python version, **rename `.venv`** (for example to `.venv.backup`) and double-click again. This does not remove your inputs or reports. Manually removing packages from an existing environment is not detected by the requirements cache; recreate the environment if packages are missing.
- Errors keep the console open so you can read them. If port **8501** is already in use, stop the other RingBlast/Streamlit instance before trying again. Do not launch two copies at once, especially during initial setup.
- This is a local Windows launcher, not a standalone executable or offline installer. It listens only on **127.0.0.1**, and usage statistics are disabled. Your browser/Windows policies may prevent automatic browser opening; use the URL above instead. Windows CI exercises the real launcher, but cannot verify your computer's antivirus, permissions or browser settings.

## Installation Windows — PowerShell (manual alternative)

Prérequis : **Git** et **Python 3.12 64 bits** installés. Les commandes ci-dessous n'exigent pas l'activation de l'environnement virtuel et évitent les restrictions PowerShell sur `Activate.ps1`.

```powershell
git clone https://github.com/jeshurun01/RingBlast.git
cd RingBlast
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

Ouvrir **http://localhost:8501** si le navigateur ne s'ouvre pas automatiquement. Arrêter avec `Ctrl+C`. Pour les lancements suivants, se placer dans `RingBlast` et relancer uniquement la dernière commande. Si `py` est introuvable, installer Python avec le lanceur Windows, puis rouvrir PowerShell. Vérifier avec `py -0p` que Python 3.12 est disponible.

Pour un **ancien clone**, sauvegarder ses modifications avant toute mise à jour ; ne pas écraser son dossier pour le remplacer. Pour un nouveau clone, choisir un dossier de destination vide.

## Installation Linux / macOS

```sh
git clone https://github.com/jeshurun01/RingBlast.git
cd RingBlast
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

## Utilisation de l'interface

1. Importer un ou plusieurs fichiers `.xml` / `.XML` iRedes DRPPlan. Décompresser les archives **avant** l'import : l'import ZIP natif n'est pas implémenté.
2. Sélectionner les plans à traiter et la vue de dessus ou de dessous. Vérifier les coordonnées, diamètres et noms des trous.
3. Vérifier les paramètres et les tableaux éditables (diamètre, bourrage, délais). Pour les grands plans, utiliser **Update preview** pour actualiser l'aperçu.
4. Cliquer sur **Generate blast report**, puis télécharger les PDF/CSV ou le ZIP. Pour plusieurs plans, le nom du PDF combiné est personnalisable et identique dans le téléchargement et l'archive.

Les diamètres XML positifs sont conservés, y compris leurs décimales. Un diamètre nul, vide ou absent utilise un **secours de 89 mm**, signalé dans l'interface et dans la synthèse CLI. Un override positif remplace tous les diamètres. Un nom de trou répété est désambiguïsé pour l'affichage sans modifier son nom/identifiant source.

**Attention métier :** un diamètre de secours ne prouve pas qu'un trou doit être chargé ni qu'il s'agit d'un reamer. Les paramètres et résultats sont à valider par le responsable compétent avant tout usage opérationnel. La correction des collets est désactivée par défaut ; ne l'activer qu'après contrôle du plan source. Les XML d'entrée ne sont pas réécrits.

## Traitement par lots — Windows

Placer ses XML privés dans `inputs` (dossier non versionné). Utiliser un **nouveau dossier de sortie par lot** : les sorties existantes peuvent être remplacées et la génération n'est pas atomique.

```powershell
.\.venv\Scripts\python.exe scripts\generate_batch_reports.py "inputs\*.XML" -o "generated_reports\mon_lot"
```

Les guillemets permettent au programme de développer lui-même le motif, également sous PowerShell. On peut aussi passer plusieurs chemins XML explicites, ou consulter toutes les options :

```powershell
.\.venv\Scripts\python.exe scripts\generate_batch_reports.py --help
```

Sous Linux/macOS :

```sh
.venv/bin/python scripts/generate_batch_reports.py 'inputs/*.XML' -o generated_reports/mon_lot
```

Le lot produit :

- `<LOT>_Combined_RingBlast_Report.pdf` : rapports fusionnés ; `--combined-name` permet de changer ce nom ;
- `<LOT>_Top_View_All_Rings.pdf` : synthèse des collets, une page A3 paysage vectorielle ;
- `<LOT>_RingBlast_Report_Package.zip` : rapports individuels, CSV, PDF combiné, synthèse et `generation_summary.json`.

Le nom du lot est dérivé des noms XML ou des identifiants de plans. Les suffixes `R1`, `R2`, `R10` et `SLOT1`, `SLOT2`, `SLOT10` sont triés numériquement. La CLI refuse les noms de sortie en double, même avec une casse différente.

**Limite de la synthèse :** les collets de chaque plan sont normalisés dans une colonne indépendante. Ce dessin ne représente ni la position relative réelle des plans ni une échelle métrique commune.

## Tests et vérification

Installation des outils de test (PowerShell) :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest tests -q --tb=short
```

Sous Linux/macOS, remplacer `.\.venv\Scripts\python.exe` par `.venv/bin/python`.

Les tests publiés utilisent des données synthétiques, sans documents de chantier ni chemins locaux requis. Ils couvrent notamment le parseur, les diamètres, les projections, la pagination PDF, le nommage, l'intégrité ZIP/CSV, le démarrage Streamlit et la génération via `AppTest`. Ce dernier injecte un état déjà parsé : il ne pilote pas le sélecteur de fichiers d'un navigateur.

Le workflow GitHub Actions teste Python 3.12 sur **Ubuntu et Windows**. Voir les résultats réels dans l'onglet [Actions](https://github.com/jeshurun01/RingBlast/actions) ; sa présence seule ne prouve pas que les contrôles passent. Une CI Windows ne remplace pas un essai interactif sur votre ordinateur.

## Confidentialité

Ce dépôt est public. Ne pas y ajouter de plans de chantier, documents clients, coordonnées réelles, rapports générés, mots de passe ou secrets. `inputs/`, `generated*/`, les dossiers de travail agents et les secrets locaux sont exclus par `.gitignore`. Ces exclusions ne remplacent pas la vérification de `git diff --cached` avant publication.

Lancement local : les fichiers importés sont traités par le processus Streamlit local et ses caches ; les résultats sont téléchargés depuis l'interface. Ne pas exposer ce serveur sur le réseau sans protection adaptée. Aucun jeu de données opérationnel n'est fourni dans le clone.
