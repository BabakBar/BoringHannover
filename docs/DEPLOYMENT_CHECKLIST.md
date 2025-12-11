# BoringHannover Coolify Deployment Checklist

**Status**: ✅ Deployed to production | Last updated: 2025-12-11

---

## Quick Start: 5 Steps to Production

### ✅ Step 0: DNS (Already Done)
- [x] Cloudflare DNS pointing to Hetzner VPS
- [x] SSL/TLS configured

### ✅ Step 1: GitHub Container Registry Setup (Completed)

#### 1.1 Enable Workflow Permissions
1. Go to https://github.com/BabakBar/BoringHannover/settings/actions
2. Scroll to **Workflow permissions**
3. Select:
   - ✅ **Read and write permissions**
   - ✅ **Allow GitHub Actions to create and approve pull requests**
4. Click **Save**

#### 1.2 Trigger Initial Build
```bash
# Push to trigger the deploy workflow
git commit --allow-empty -m "chore: trigger initial GHCR build"
git push origin master
```

Or manually trigger via GitHub UI:
- Go to https://github.com/BabakBar/BoringHannover/actions/workflows/deploy.yml
- Click **Run workflow** → **Run workflow**

#### 1.3 Make Docker Images Public
After the workflow completes:

1. Go to https://github.com/BabakBar?tab=packages
2. Find and click on `boringhannover/backend`
   - Click **Package settings** (gear icon in top right)
   - Scroll to **Danger Zone** → **Change visibility**
   - Select **Public** → Confirm
3. Repeat for `boringhannover/frontend`

> **Why?** Coolify needs to pull these images. Public packages work without credentials.

---

### ✅ Step 2: Create Coolify Services (Completed)

#### 2.1 Frontend Service
In your Coolify dashboard:

1. Go to Projects → Create or select project "BoringHannover"
2. Click **Add Resource** → **Docker Image**
3. Fill in:
   - **Name**: `boringhannover-frontend`
   - **Image**: `ghcr.io/babakbar/boringhannover/frontend:latest`
   - **Port Mapping**: `8080:8080`
   - **Domain**: `boringhannover.de`
   - **Health Check Path**: `/health`
   - **Health Check Interval**: `30s`
4. Click **Save** → **Deploy**

#### 2.2 Backend Service (Scheduled)
1. Click **Add Resource** → **Docker Image**
2. Fill in:
   - **Name**: `boringhannover-backend`
   - **Image**: `ghcr.io/babakbar/boringhannover/backend:latest`
   - **Type**: ⚠️ **Scheduled** (not "Always Running")
   - **Schedule**: `0 17 * * 1` (Every Monday at 5 PM CET)

3. **Environment Variables** (click Add Variable for each):
   ```
   GITHUB_TOKEN=<create Personal Access Token - see below>
   GITHUB_REPO=BabakBar/BoringHannover
   TZ=Europe/Berlin
   LOG_LEVEL=INFO
   ```

   **Optional - Telegram notifications** (can be added later):
   ```
   TELEGRAM_BOT_TOKEN=<get from @BotFather on Telegram>
   TELEGRAM_CHAT_ID=<your Telegram chat ID>
   ```

4. Click **Save** → **Deploy**

**How to get tokens:**

**TELEGRAM_BOT_TOKEN**:
1. Open Telegram → search for `@BotFather`
2. Send `/newbot` and follow prompts
3. Copy the token provided

**TELEGRAM_CHAT_ID**:
1. Send a message to your bot
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Find `"chat":{"id":123456789}` in the JSON response

**GITHUB_TOKEN** (for committing data updates):
1. Go to https://github.com/settings/tokens?type=beta
2. Click **Generate new token**
3. Configure:
   - **Name**: BoringHannover Data Sync
   - **Expiration**: 1 year
   - **Repository access**: Only select `BabakBar/BoringHannover`
   - **Permissions** → **Contents**: Read and write
4. Click **Generate token** → **Copy it immediately**

#### 2.3 Get Webhook URLs
For **each service** (frontend and backend):

1. Click on the service in Coolify
2. Go to **Webhooks** tab
3. Copy the **Deploy Webhook URL** 
   - Example: `https://coolify.your-vps.com/api/v1/deploy/webhooks/abc-123-def`
4. Save both URLs for Step 3

#### 2.4 Generate Coolify API Token
1. Coolify → **Settings** → **API Tokens**
2. Click **Create Token**
3. Name: `GitHub Actions Deploy`
4. Permissions: ✅ **Deploy**
5. Click **Create** → **Copy token immediately** (you can't see it again)

---

### ✅ Step 3: Configure GitHub Secrets (Completed)

Add secrets to your repository:

1. Go to https://github.com/BabakBar/BoringHannover/settings/secrets/actions
2. Click **New repository secret**
3. Add these three secrets:

| Name | Value | Where to get it |
|------|-------|-----------------|
| `COOLIFY_TOKEN` | Token from Step 2.4 | Coolify Settings → API Tokens |
| `COOLIFY_WEBHOOK_BACKEND` | Backend webhook URL | Coolify backend service → Webhooks |
| `COOLIFY_WEBHOOK_FRONTEND` | Frontend webhook URL | Coolify frontend service → Webhooks |

---

### ✅ Step 4: Test Deployment (Completed)

#### 4.1 Trigger Deploy
```bash
git commit --allow-empty -m "test: verify full deployment pipeline"
git push origin master
```

#### 4.2 Monitor Progress
1. **GitHub Actions**: https://github.com/BabakBar/BoringHannover/actions
   - Watch for green checkmarks:
     - ✅ Build Images
     - ✅ Deploy to Coolify

2. **Coolify Dashboard**: Check both services show "Deploying..."

#### 4.3 Verify Live Site
1. Visit your domain: `https://boringhannover.de` ✅
2. Check `/health` endpoint: `https://boringhannover.de/health` ✅
3. Verify events appear (may be mock data on first deploy)

#### 4.4 Generate Initial Data
The frontend will show mock data until backend runs. To fix:

1. In Coolify, go to backend service
2. Click **Run Once** or **Execute** to run the task immediately
3. Watch logs - should see:
   - "Scraping events..."
   - "Committing to GitHub..."
   - "Pushing to repository..."
4. Check GitHub repo - new commit with updated `web/output/web_events.json`
5. Frontend will auto-deploy (triggered by the commit)
6. Refresh website - real events should now appear!

---

### 🔄 Step 5: Verify Weekly Update Pipeline

The most important flow:

```
Monday 17:00 CET:
┌─────────────────────┐
│ Coolify runs cron   │
│ Backend scrapes web │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Commits to GitHub   │
│ web_events.json     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ GitHub Actions      │
│ triggered by commit │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Coolify deploys     │
│ new frontend        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Users see fresh     │
│ event data! 🎉      │
└─────────────────────┘
```

**Test this now (don't wait for Monday)**:
1. Manually run backend in Coolify (Step 4.4)
2. Verify GitHub commit appears
3. Verify GitHub Actions runs
4. Verify frontend redeploys
5. Verify website shows updated data

---

## Troubleshooting

### ❌ Coolify can't pull images (401 Unauthorized)
- **Fix**: Make packages public (Step 1.3)
- **Alternative**: Configure GHCR credentials in Coolify Settings → Docker Registries

### ❌ Frontend shows mock data forever
- **Fix**: Run backend once manually (Step 4.4)
- **Check**: Verify `GITHUB_TOKEN` has write permission
- **Verify**: `web/output/web_events.json` was committed to repo

### ❌ Backend doesn't run on schedule
- **Check**: Service type is "Scheduled" not "Always Running"
- **Check**: Cron syntax is `0 17 * * 1`
- **Check**: `TZ=Europe/Berlin` is set in environment variables

### ❌ Deployment webhook fails
- **Fix**: Regenerate `COOLIFY_TOKEN` in Coolify
- **Fix**: Copy fresh webhook URLs from Coolify
- **Check**: Coolify API is accessible from internet

### ❌ GitHub commit fails
- **Fix**: Regenerate `GITHUB_TOKEN` with Contents: Read and write
- **Check**: Token hasn't expired
- **Check**: Token has access to correct repository

---

## Success Checklist

After completing all steps, verify:

- [x] Website loads at your domain with HTTPS
- [x] `/health` endpoint returns "OK"
- [ ] Events show current dates (not mock data) - **Run backend manually to generate**
- [x] Backend service visible in Coolify with cron schedule
- [x] Frontend service running and healthy in Coolify
- [x] GitHub Actions workflow runs successfully on push
- [ ] Manual backend run commits to GitHub and triggers redeploy - **Test next**
- [ ] Telegram message received after backend runs - **Optional, not configured**

---

## What Happens Every Monday?

1. **17:00 CET**: Coolify triggers backend container
2. **Backend scrapes**: Cinema websites, concert venues, etc.
3. **Formats data**: Creates `web_events.json`
4. **Commits to GitHub**: Pushes updated file to repository
5. **GitHub Actions triggers**: Detects commit, runs deploy workflow
6. **Builds images**: Fresh frontend with new data
7. **Coolify deploys**: Pulls new images and restarts services
8. **Telegram notifies**: Sends weekly digest (if configured)
9. **Users see updates**: Fresh events on the website! 🎉

---

## Files Reference

- GitHub workflow: `.github/workflows/deploy.yml`
- Frontend Dockerfile: `Dockerfile.web`
- Backend Dockerfile: `Dockerfile`
- Full deployment guide: `docs/DEPLOYMENT.md`

---

## Next Steps After Deployment

1. **Monitor first scheduled run** (Monday evening)
2. **Set calendar reminders**:
   - GitHub PAT expires in 1 year
   - Review Coolify token annually
3. **Optimize Cloudflare**:
   - Cache `/assets/*` for 1 year
   - Verify compression enabled
4. **Monitor resources**:
   - Disk usage in Coolify
   - Memory usage of services
5. **Backup**: Commits to GitHub = automatic backup of all event data

---

**Need help?** Check `docs/DEPLOYMENT.md` for detailed troubleshooting and architecture docs.
