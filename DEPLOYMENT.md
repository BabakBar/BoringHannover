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
                              ────────────────▶│  │   Port 80       │    │
                                               │  └─────────────────┘    │
                                               │                         │
                                               │  ┌─────────────────┐    │
                              Cron (Mon 9AM)   │  │ Backend (Python)│    │
                              ────────────────▶│  │   Scheduled     │    │
                                               │  └─────────────────┘    │
                                               └─────────────────────────┘
```

## Prerequisites

- Hetzner VPS with Coolify installed
- Namecheap domain
- Cloudflare account (free tier works)
- GitHub repository with Actions enabled
- Telegram bot token and chat ID

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
| A | @ | your-vps-ip | ✅ Proxied | Auto |
| A | www | your-vps-ip | ✅ Proxied | Auto |

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

## 3. Coolify Setup

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
   | Port Mapping | `80:80` |
   | Domain | `yourdomain.com` |

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
   | Schedule | `0 9 * * 1` (Every Monday at 9 AM) |

3. **Environment Variables** (add in Coolify):
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
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

## 4. GitHub Actions Secrets

Add these secrets to your GitHub repository:

| Secret Name | Description |
|-------------|-------------|
| `COOLIFY_TOKEN` | API token from Coolify |
| `COOLIFY_WEBHOOK_BACKEND` | Backend deploy webhook URL |
| `COOLIFY_WEBHOOK_FRONTEND` | Frontend deploy webhook URL |

### How to Add Secrets

1. Go to GitHub repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add each secret

---

## 5. Container Registry Setup

### Enable GitHub Container Registry

1. Go to GitHub repo → **Settings** → **Actions** → **General**
2. Under **Workflow permissions**, select:
   - **Read and write permissions**
   - Enable **Allow GitHub Actions to create and approve pull requests**

### First-time Push

After the first deploy workflow runs, make packages public:

1. Go to your GitHub profile → **Packages**
2. Find `kinoweek/backend` and `kinoweek/frontend`
3. Go to **Package settings** → Change visibility to **Public**

---

## 6. Verify Deployment

### Check CI/CD Pipeline

1. Push to `main` branch
2. Go to **Actions** tab in GitHub
3. Verify all jobs pass:
   - ✅ Backend tests
   - ✅ Frontend build
   - ✅ Docker build
   - ✅ Deploy to Coolify

### Verify Services

1. **Frontend**: Visit `https://yourdomain.com`
   - Should see KinoWeek homepage
   - Check `/health` returns `OK`

2. **Backend**: Check Coolify logs
   - Go to backend service → Logs
   - Verify scheduled execution works

3. **Telegram**: Send test message
   ```bash
   docker compose run --rm backend-prod
   ```

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

### Backup Strategy

1. **Database**: N/A (stateless application)
2. **Configuration**: Stored in Git
3. **Output files**: Consider mounting a volume in Coolify

---

## Local Development

### Run Services Locally

```bash
# Build and run frontend
docker compose up frontend

# Run backend in local mode (no Telegram)
docker compose up backend

# Run backend in production mode
docker compose --profile production run --rm backend-prod
```

### Access Points

- Frontend: http://localhost:8080
- Frontend dev (hot reload): http://localhost:4321

---

## Troubleshooting

### Frontend Issues

**Problem**: Hydration mismatch errors
**Solution**: Disable Auto Minify in Cloudflare

**Problem**: 502 Bad Gateway
**Solution**: Check container health in Coolify, verify port mapping

### Backend Issues

**Problem**: Telegram message not sent
**Solution**: Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in Coolify environment

**Problem**: Scraping failures
**Solution**: Check logs for rate limiting, verify source websites are accessible

### Deployment Issues

**Problem**: Webhook fails
**Solution**: Verify `COOLIFY_TOKEN` has deploy permissions, check webhook URL

**Problem**: Docker push fails
**Solution**: Ensure workflow permissions allow package writes

---

## Security Checklist

- [ ] Cloudflare proxy enabled (orange cloud)
- [ ] SSL set to Full (strict)
- [ ] Auto Minify disabled
- [ ] Bot Fight Mode enabled
- [ ] Telegram credentials stored in Coolify secrets (not env files)
- [ ] GitHub secrets configured (not hardcoded)
- [ ] Container runs as non-root user
- [ ] Health checks enabled

---

## Quick Reference

### Cron Syntax

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sunday=0)
│ │ │ │ │
│ │ │ │ │
0 9 * * 1  ← Every Monday at 9:00 AM
```

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
```

### URLs

- Production: `https://yourdomain.com`
- Coolify: `https://coolify.your-server.com`
- GitHub Actions: `https://github.com/BabakBar/KinoWeek/actions`
