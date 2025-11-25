# KinoWeek Production Deployment Guide

Complete guide for deploying KinoWeek to production using Hetzner VPS, Coolify, Cloudflare, and Namecheap.

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────────────┐
│   Namecheap     │───▶│   Cloudflare     │───▶│     Hetzner VPS         │
│   (Domain)      │    │ (DNS/CDN/SSL)    │    │      (Coolify)          │
└─────────────────┘    └──────────────────┘    │                         │
                                               │  ┌─────────────────┐    │
                              HTTPS            │  │ Frontend (nginx)│    │
                              ────────────────▶│  │   Port 8080     │    │
                                               │  └─────────────────┘    │
                                               │                         │
                                               │  ┌─────────────────┐    │
                              Cron (Mon 9AM)   │  │ Backend (Python)│    │
                              ────────────────▶│  │   Scheduled     │    │
                                               │  └─────────────────┘    │
                                               └─────────────────────────┘
```

### Data Update Pipeline (Critical)

The frontend is a **static site** built at image creation time. For weekly data updates to reach users, the following pipeline runs:

```
Monday 17:00 PM CET:
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Coolify runs    │────▶│ Backend commits │────▶│ Push triggers   │
│ backend cron    │     │ web_events.json │     │ deploy.yml      │
│                 │     │ to GitHub repo  │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
┌─────────────────┐     ┌─────────────────┐              │
│ Users see fresh │◀────│ Coolify deploys │◀─────────────┘
│ event data      │     │ new frontend    │
└─────────────────┘     └─────────────────┘
```

**Without this pipeline, the frontend shows stale/mock data forever.**

---

## Prerequisites

- Hetzner VPS with Coolify installed
- Namecheap domain
- Cloudflare account (free tier works)
- GitHub repository with Actions enabled
- Telegram bot token and chat ID
- GitHub Personal Access Token (PAT) with `contents:write` scope

---

## 1. Namecheap DNS Setup

### Change Nameservers to Cloudflare

1. Log into Namecheap dashboard
2. Go to **Domain List** → Select your domain → **Manage**
3. Under **Nameservers**, select **Custom DNS**
4. Enter Cloudflare nameservers (provided when you add site to Cloudflare):
   ```
   ns1.cloudflare.com
   ns2.cloudflare.com
   ```
5. Save changes (propagation takes 24-48 hours)

---

## 2. Cloudflare Configuration

### Add Your Site

1. Log into Cloudflare dashboard
2. Click **Add a Site** → Enter your domain
3. Select **Free** plan
4. Cloudflare will scan existing DNS records

### DNS Records

Add these records (replace `your-vps-ip` with your Hetzner IP):

| Type | Name | Content | Proxy | TTL |
|------|------|---------|-------|-----|
| A | @ | 168.119.102.249 | ✅ Proxied | Auto |
| A | www | 168.119.102.249 | ✅ Proxied | Auto |

### SSL/TLS Settings

1. Go to **SSL/TLS** → **Overview**
2. Set encryption mode to **Full (strict)**
3. Go to **Edge Certificates**:
   - Enable **Always Use HTTPS**
   - Enable **Automatic HTTPS Rewrites**
   - Set **Minimum TLS Version** to 1.2

### Performance Settings

1. Go to **Speed** → **Optimization**
2. **DISABLE Auto Minify** (prevents Astro hydration issues)
3. Enable **Brotli** compression

### Caching Rules

1. Go to **Caching** → **Cache Rules**
2. Create rule for static assets:
   ```
   Name: Cache Static Assets
   Expression: (http.request.uri.path contains "/assets/")
   Cache eligibility: Eligible for cache
   Edge TTL: 1 year
   Browser TTL: 1 year
   ```

### Security Settings

1. Go to **Security** → **Settings**
2. Set **Security Level** to Medium
3. Enable **Bot Fight Mode**
4. Consider enabling **WAF** rules for additional protection

---

## 3. GitHub Container Registry Setup

> **Important**: Complete this section BEFORE configuring Coolify. GHCR packages default to private, and Coolify will fail to pull images (401 Unauthorized) without proper setup.

### Enable GitHub Container Registry

1. Go to GitHub repo → **Settings** → **Actions** → **General**
2. Under **Workflow permissions**, select:
   - **Read and write permissions**
   - Enable **Allow GitHub Actions to create and approve pull requests**

### Initial Image Push

Before configuring Coolify, push initial images:

1. Trigger the deploy workflow manually:
   - Go to **Actions** → **Deploy** → **Run workflow**
   - Or push any commit to `master` branch

2. Make packages public (required for Coolify without credentials):
   - Go to your GitHub profile → **Packages**
   - Find `kinoweek/backend` and `kinoweek/frontend`
   - Go to **Package settings** → Change visibility to **Public**

### Alternative: Private Registry with Credentials

If you prefer private packages, configure Coolify with GHCR credentials:

1. Create a GitHub PAT with `read:packages` scope
2. In Coolify, go to **Settings** → **Docker Registries**
3. Add registry:
   - URL: `ghcr.io`
   - Username: your GitHub username
   - Password: the PAT token

---

## 4. GitHub Secrets Configuration

Add these secrets to your GitHub repository (for CI/CD deployment):

| Secret Name | Description | Required For |
|-------------|-------------|--------------|
| `COOLIFY_TOKEN` | API token from Coolify | Deployment |
| `COOLIFY_WEBHOOK_BACKEND` | Backend deploy webhook URL | Deployment |
| `COOLIFY_WEBHOOK_FRONTEND` | Frontend deploy webhook URL | Deployment |

### Creating the GitHub Data Sync Token

The backend needs a GitHub PAT to commit `web_events.json` to the repository. This token is configured in **Coolify** (not GitHub secrets):

1. Go to GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
2. Click **Generate new token**
3. Configure:
   - Name: `KinoWeek Data Sync`
   - Expiration: 1 year (set reminder to rotate)
   - Repository access: Select `KinoWeek` only
   - Permissions:
     - Contents: **Read and write**
4. Copy the token - you'll add it as `GITHUB_TOKEN` in Coolify backend env vars (Section 5)

### How to Add GitHub Secrets

1. Go to GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add each secret from the table above

---

## 5. Coolify Setup

### Access Coolify Dashboard

1. Navigate to your Coolify instance: `https://coolify.your-server.com`
2. Log in with admin credentials

### Create Project

1. Click **New Project**
2. Name: `KinoWeek`
3. Description: `Weekly event aggregator for Hannover`

### Configure Frontend Service

1. In KinoWeek project, click **Add Resource** → **Docker Image**
2. Configuration:

   | Setting | Value |
   |---------|-------|
   | Name | `kinoweek-frontend` |
   | Image | `ghcr.io/babakbar/kinoweek/frontend:latest` |
   | Port Mapping | `8080:8080` |
   | Domain | `yourdomain.com` |

   > **Note**: Frontend runs on port 8080 (non-root). Cloudflare/Coolify handles HTTPS termination.

3. **Health Check**:
   - Path: `/health`
   - Interval: 30s

4. Save and deploy

### Configure Backend Service (Scheduled Task)

1. Click **Add Resource** → **Docker Image**
2. Configuration:

   | Setting | Value |
   |---------|-------|
   | Name | `kinoweek-backend` |
   | Image | `ghcr.io/babakbar/kinoweek/backend:latest` |
   | Type | **Scheduled** |
   | Schedule | `0 7 * * 1` (Mon 7:00 UTC = 9:00 CET) |

   > **Timezone Note**: Coolify cron runs in UTC. For 9:00 AM Hannover time:
   > - Winter (CET): `0 8 * * 1` (UTC+1)
   > - Summer (CEST): `0 7 * * 1` (UTC+2)
   > - Or set `TZ=Europe/Berlin` in container env vars

3. **Environment Variables** (add in Coolify):
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   GITHUB_TOKEN=your_data_sync_pat
   GITHUB_REPO=BabakBar/KinoWeek
   TZ=Europe/Berlin
   LOG_LEVEL=INFO
   ```

4. Save and deploy

### Configure Webhooks for CI/CD

1. Go to each service → **Webhooks**
2. Copy the **Deploy Webhook URL**
3. Note the **UUID** for each service

### Generate API Token

1. Go to **Settings** → **API Tokens**
2. Create new token with **Deploy** permission
3. Save the token securely

---

## 6. Verify Deployment

### Check CI/CD Pipeline

1. Push to `master` branch
2. Go to **Actions** tab in GitHub
3. Verify all jobs pass:
   - ✅ Backend tests
   - ✅ Frontend build
   - ✅ Docker build
   - ✅ Deploy to Coolify (both webhooks must succeed)

> **Important**: If deployment webhooks fail, the job will fail (not silently continue). Check Coolify logs for details.

### Verify Services

1. **Frontend**: Visit `https://yourdomain.com`
   - Should see KinoWeek homepage
   - Check `/health` returns `OK`
   - Verify data is not mock data (check dates are current)

2. **Backend**: Check Coolify logs
   - Go to backend service → Logs
   - Verify scheduled execution works
   - Confirm GitHub commit appears after scrape

3. **Data Pipeline**: Trigger manual backend run
   ```bash
   # In Coolify, trigger backend manually or wait for cron
   # Then verify:
   # 1. New commit appears in GitHub with updated web_events.json
   # 2. Deploy workflow triggers automatically
   # 3. Frontend shows fresh data after deploy completes
   ```

4. **Telegram**: Verify message sent
   - Check your Telegram channel/chat for the weekly digest

---

## 7. Monitoring & Maintenance

### Coolify Monitoring

- Enable **Auto Cleanup** for Docker images (Settings → Cleanup)
- Set cleanup schedule: `0 3 * * *` (Daily at 3 AM)
- Monitor disk usage regularly

### Cloudflare Analytics

- Check **Analytics** → **Traffic** for visitor stats
- Monitor **Security** → **Events** for blocked threats
- Set up **Notifications** for security events

### Log Management

Backend logs are available in:
- Coolify dashboard → Service → Logs
- Container stdout/stderr

### Token Rotation

Set calendar reminders to rotate tokens before expiry:
- `GITHUB_TOKEN` (in Coolify): Check PAT expiration date in GitHub
- `COOLIFY_TOKEN`: Rotate annually as best practice

### Backup Strategy

1. **Database**: N/A (stateless application)
2. **Configuration**: Stored in Git
3. **Event Data**: Committed to repo (`web/output/web_events.json`)

---

## Local Development

### Run Services Locally

```bash
# Build and run frontend
docker compose up frontend

# Run backend in local mode (no Telegram, no GitHub sync)
docker compose up backend

# Run backend in production mode
docker compose --profile production run --rm backend-prod
```

### Access Points

- Frontend: http://localhost:8080
- Frontend dev (hot reload): http://localhost:4321

---

## Troubleshooting

### Data Not Updating

**Problem**: Frontend shows stale or mock data after cron runs

**Diagnosis**:
1. Check backend logs in Coolify - did scrape succeed?
2. Check GitHub repo - was `web_events.json` committed?
3. Check GitHub Actions - did deploy workflow trigger?
4. Check Coolify - did frontend redeploy?

**Solutions**:
- Verify `GITHUB_TOKEN` and `GITHUB_REPO` env vars in Coolify
- Check token has `contents:write` permission
- Manually trigger deploy workflow to test

### Frontend Issues

**Problem**: Hydration mismatch errors
**Solution**: Disable Auto Minify in Cloudflare

**Problem**: 502 Bad Gateway
**Solution**: Check container health in Coolify, verify port 8080 mapping

**Problem**: Shows mock data on first deploy
**Solution**: Run backend once to generate initial data, then redeploy frontend

### Backend Issues

**Problem**: Telegram message not sent
**Solution**: Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in Coolify environment

**Problem**: Scraping failures
**Solution**: Check logs for rate limiting, verify source websites are accessible

**Problem**: GitHub commit fails
**Solution**: Verify `GITHUB_TOKEN` has `contents:write` scope and hasn't expired

### Deployment Issues

**Problem**: Webhook fails with 401/403
**Solution**: Verify `COOLIFY_TOKEN` has deploy permissions, regenerate if needed

**Problem**: Docker push fails
**Solution**: Ensure workflow permissions allow package writes

**Problem**: GHCR pull fails (401)
**Solution**: Make packages public OR configure GHCR credentials in Coolify

---

## Security Considerations

### Checklist

- [ ] Cloudflare proxy enabled (orange cloud)
- [ ] SSL set to Full (strict)
- [ ] Auto Minify disabled
- [ ] Bot Fight Mode enabled
- [ ] Telegram credentials stored in Coolify secrets (not env files)
- [ ] GitHub secrets configured (not hardcoded)
- [ ] Frontend container runs as non-root user (nginx, port 8080)
- [ ] Backend container runs as non-root user (kinoweek)
- [ ] Health checks enabled
- [ ] Token rotation reminders set

### CSP Limitations

The current CSP includes `'unsafe-inline'` for scripts and styles due to Astro's inline theme handling. This is a known limitation:

```
script-src 'self' 'unsafe-inline';
style-src 'self' 'unsafe-inline';
```

To fully remove `unsafe-inline`:
1. Upgrade to Astro 5.9+ which supports CSP nonces
2. Or move theme script to bundled assets with hash-based CSP

This is tracked as a future improvement. The current setup still provides meaningful protection via other CSP directives (default-src, frame-ancestors, etc.) and Cloudflare WAF.

---

## Quick Reference

### Cron Syntax (UTC)

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sunday=0)
│ │ │ │ │
│ │ │ │ │
0 7 * * 1  ← Monday 7:00 UTC (9:00 CET summer)
0 8 * * 1  ← Monday 8:00 UTC (9:00 CET winter)
```

> With `TZ=Europe/Berlin` set, use `0 9 * * 1` directly.

### Environment Variables Reference

| Variable | Where | Purpose |
|----------|-------|---------|
| `TELEGRAM_BOT_TOKEN` | Coolify | Telegram authentication |
| `TELEGRAM_CHAT_ID` | Coolify | Target chat/channel |
| `GITHUB_TOKEN` | Coolify | Commit data to repo |
| `GITHUB_REPO` | Coolify | Repository (owner/repo) |
| `TZ` | Coolify | Timezone for cron/logs |
| `LOG_LEVEL` | Coolify | Logging verbosity |
| `COOLIFY_TOKEN` | GitHub Secrets | Deploy trigger auth |
| `COOLIFY_WEBHOOK_*` | GitHub Secrets | Deploy endpoints |

### Useful Commands

```bash
# Test backend locally
docker compose up backend

# View logs
docker compose logs -f backend

# Rebuild images
docker compose build --no-cache

# Run tests
uv run pytest tests/ -v

# Format code
uv run ruff format src/ tests/

# Manually trigger data update (local)
uv run kinoweek --local
```

### URLs

- Production: `https://yourdomain.com`
- Coolify: `https://coolify.your-server.com`
- GitHub Actions: `https://github.com/BabakBar/KinoWeek/actions`
