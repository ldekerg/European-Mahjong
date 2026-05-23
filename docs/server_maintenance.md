# Server Maintenance

## Rotation de la SECRET_KEY

La `SECRET_KEY` est utilisée pour :
- Signer les cookies de session admin (`SessionMiddleware`)
- Signer les cookies `human_verified` du captcha Turnstile (liés à l'IP, expiration 24h)
- Authentifier le backend SQLAdmin

### Quand la faire tourner ?

- Après tout incident de sécurité suspecté (fuite de config, accès non autorisé)
- Si un admin quitte le projet
- En bonne pratique : une fois par an

### Conséquences d'une rotation

- Tous les cookies `human_verified` existants sont invalidés → les utilisateurs repassent le captcha une fois
- Toutes les sessions admin sont invalidées → les admins doivent se reconnecter
- Aucun impact sur les données

### Procédure

**1. Générer une nouvelle clé**

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**2. Mettre à jour le `.env` sur le serveur**

```bash
nano /chemin/vers/.env
# Remplacer la ligne :
# SECRET_KEY=ancienne_valeur
# Par :
# SECRET_KEY=nouvelle_valeur_générée
```

**3. Redémarrer l'application**

```bash
sudo systemctl restart ema-ranking
# ou selon la config :
# pm2 restart ema-ranking
```

**4. Vérifier**

- Accéder à `/manage/` → doit redemander le login
- Accéder à une page publique → doit redemander le captcha si Turnstile est configuré

---

## Variables d'environnement requises

| Variable | Description | Exemple |
|---|---|---|
| `SECRET_KEY` | Clé de signature sessions + cookies | `a3f8c2...` (32 bytes hex) |
| `TURNSTILE_SECRET` | Clé secrète Cloudflare Turnstile | (depuis dashboard Cloudflare) |
| `DATABASE_URL` | URL base de données (optionnel, SQLite par défaut) | `postgresql://...` |

---

## Rotation de la clé Turnstile

Si la clé Turnstile est compromise, la rotation se fait dans le dashboard Cloudflare :
1. Cloudflare Dashboard → Turnstile → ton site → **Rotate secret key**
2. Mettre à jour `TURNSTILE_SECRET` dans le `.env`
3. Redémarrer l'application
