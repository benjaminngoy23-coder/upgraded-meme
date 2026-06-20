# FundFlow — déploiement Dokploy corrigé

## Cause exacte de l'ancienne erreur

Dokploy affichait seulement :

```text
.git/
SOLUTION_FUNDFLOW_DOKPLOY_SANS_NIXPACKS/
```

Il ne trouvait donc ni `app.py`, ni `requirements.txt`, ni `Dockerfile` à la racine. Cette archive a été corrigée : à son ouverture, `app.py` et `Dockerfile` sont directement visibles.

## Étape 1 — GitHub

1. Décompressez `FundFlow_DOKPLOY_FINAL_CORRIGE.zip` sur votre ordinateur.
2. Ouvrez le dossier décompressé.
3. Dans le dépôt GitHub, supprimez l'ancien dossier `SOLUTION_FUNDFLOW_DOKPLOY_SANS_NIXPACKS` s'il existe.
4. Téléversez **le contenu du dossier décompressé**, pas le fichier ZIP et pas un dossier parent supplémentaire.
5. Vérifiez sur la page principale du dépôt que vous voyez directement :

```text
app.py
Dockerfile
requirements.txt
nixpacks.toml
docker-compose.yml
.github/
```

Tant que `app.py` n'est pas visible directement sur la page principale du dépôt, ne lancez pas Dokploy.

## Étape 2 — Nouvelle application Dokploy

Créez une nouvelle application, par exemple `FundFlow-Corrige`. Ne réutilisez pas l'ancien service qui contient encore la configuration Nixpacks erronée.

Dans la source GitHub :

```text
Repository : votre dépôt FundFlow
Branch : main
Build Path : /
Build Type : Dockerfile
Dockerfile Path : Dockerfile
```

Enregistrez puis déployez.

Le journal correct doit afficher une construction Docker. Il ne doit plus commencer par `Starting nixpacks build...`.

## Étape 3 — Variables

Dans Environment Variables :

```env
PORT=8000
DATA_DIR=/app/data
DB_FILE=fundflow_stable.db
PUBLIC_URL=https://app.gestionflux.fun
```

`PUBLIC_URL` peut être laissé vide tant que le domaine n'est pas prêt.

## Étape 4 — Données persistantes

Dans Advanced > Mounts, créez un **Volume Mount** avec :

```text
Mount Path : /app/data
```

Ne stockez pas la base SQLite dans `/app` sans volume, sinon les données peuvent disparaître lors d'un redéploiement.

## Étape 5 — Domaine

Dans Domains :

```text
Host : app.gestionflux.fun
Path : /
Container Port : 8000
HTTPS : ON
Certificate : Let's Encrypt
```

Le port `8000` est le port interne du conteneur. Il n'est pas nécessaire de publier manuellement ce port dans Advanced > Ports.

## Contrôle final

Ouvrez :

```text
https://app.gestionflux.fun/health
```

Le résultat attendu ressemble à :

```json
{"ok": true, "time": "..."}
```

Ensuite ouvrez `/login`.

## Si Dokploy lance encore Nixpacks

Cela signifie que l'ancien service est toujours utilisé ou que `Build Type` n'a pas été changé. Deux possibilités :

1. Revenir dans General et choisir `Dockerfile`.
2. Garder Nixpacks temporairement : le fichier `nixpacks.toml` fourni force Python 3.12 et la commande `python app.py --no-browser`.

Cependant, la configuration recommandée pour ce paquet est **Dockerfile**.

## Solution sans construction sur le VPS

Le workflow `.github/workflows/build-ghcr.yml` construit également une image dans GitHub Actions. Après une exécution verte, l'image est :

```text
ghcr.io/UTILISATEUR_GITHUB/NOM_DU_DEPOT:latest
```

Vous pouvez alors créer une application Dokploy avec :

```text
Source Type : Docker
Docker Image : ghcr.io/UTILISATEUR_GITHUB/NOM_DU_DEPOT:latest
Container Port : 8000
```

Si le package GHCR est privé, rendez-le public ou ajoutez dans Dokploy un identifiant GitHub et un token autorisé à lire les packages.
