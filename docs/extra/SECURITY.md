# KinoWeek Security, Privacy & Accessibility Plan

> **Status:** Draft
> **Last Updated:** 2025-11-23
> **Last Reviewed:** 2025-11-23 (Gemini review incorporated)
> **Scope:** Python scraper backend + Astro static frontend
> **Deployment:** Hetzner VPS (backend cron) + Cloudflare/Static hosting (frontend)

This document consolidates security vulnerabilities, privacy requirements, accessibility gaps, and remediation strategies for the KinoWeek (BoringHannover) project.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Backend Security](#backend-security)
3. [Frontend Security](#frontend-security)
4. [German Legal Compliance](#german-legal-compliance)
5. [Accessibility (WCAG 2.1 AA)](#accessibility-wcag-21-aa)
6. [Infrastructure Hardening](#infrastructure-hardening)
7. [Data Integrity & Monitoring](#data-integrity--monitoring)
8. [Implementation Checklist](#implementation-checklist)

---

## Executive Summary

### Risk Profile

| Area | Current State | Risk Level |
|------|---------------|------------|
| XSS from scraped data | No sanitization | **High** |
| URL injection | No validation | **High** |
| German legal compliance | No Impressum/Datenschutz | **High** |
| Security headers | None configured | **Medium** |
| Accessibility | Partial (missing landmarks, time semantics) | **Medium** |
| Rate limiting | None | **Low** |
| Telegram token exposure | Potential log leakage | **Low** |

### Key Findings

- **Scraped data flows directly to frontend without sanitization** - primary XSS vector
- **No URL scheme validation** - `javascript:` URLs could execute in user browsers
- **Missing German legal pages** - Impressum and Datenschutzerklärung required by law
- **No CSP headers** - XSS attacks have full DOM access if they occur
- **Accessibility gaps** - missing time semantics, skip links, proper heading hierarchy

---

## Backend Security

### BS-1: Input Sanitization (Poisoned Source Defense)

**Severity: High**

Scraped HTML from external sites (ZAG Arena, Capitol, etc.) could contain malicious content. If a source site is compromised, `<script>` tags in event titles would flow through to the frontend.

**Current State:**
- `models.py` uses plain `dataclass` without validation
- `BeautifulSoup.get_text()` strips tags but doesn't escape special characters
- No sanitization before JSON export

**Remediation:**

1. **Install nh3 for HTML sanitization:**

> ⚠️ **Note:** Do NOT use `bleach`. It was [deprecated by Mozilla in January 2023](https://github.com/mozilla/bleach/issues/698) due to its dependency on the unmaintained `html5lib`. Use `nh3` instead—a Python binding to the Rust [Ammonia](https://github.com/rust-ammonia/ammonia) crate that is actively maintained and ~20x faster.

```bash
uv add nh3
```

2. **Create sanitization utility** (`src/kinoweek/sanitize.py`):
```python
"""Text sanitization for untrusted scraped content."""
import re
from typing import Final

import nh3

# Maximum lengths to prevent data corruption attacks
MAX_TITLE_LENGTH: Final[int] = 200
MAX_VENUE_LENGTH: Final[int] = 100
MAX_URL_LENGTH: Final[int] = 500
MAX_DESCRIPTION_LENGTH: Final[int] = 1000

def sanitize_text(text: str | None, max_length: int = 500) -> str:
    """Remove all HTML and limit length."""
    if not text:
        return ""
    # nh3 is faster and safer than deprecated bleach
    # tags=set() ensures ALL tags are stripped
    cleaned = nh3.clean(text, tags=set())
    # Normalize whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Enforce length limit
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length - 3] + "..."
    return cleaned

def sanitize_url(url: str | None) -> str:
    """Validate URL scheme is http/https only."""
    if not url:
        return ""
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        return ""
    # Only allow http/https schemes
    if not url.startswith(('http://', 'https://')):
        return ""
    return url
```

3. **Apply in scrapers** (e.g., `zag_arena.py`):
```python
from kinoweek.sanitize import sanitize_text, sanitize_url

title = sanitize_text(title_elem.get_text(strip=True), MAX_TITLE_LENGTH)
event_url = sanitize_url(link_elem.get("href"))
```

4. **Apply in exporters** (`exporters.py`) as defense-in-depth:
```python
from kinoweek.sanitize import sanitize_text, sanitize_url

# In export_web_json():
"title": sanitize_text(event.title),
"url": sanitize_url(event.url),
```

---

### BS-2: Data Schema Validation (Circuit Breaker)

**Severity: Medium**

If a source website changes its HTML structure, scrapers may grab garbage data (e.g., 5MB of CSS instead of a date). This bloats JSON and could crash the frontend.

**Current State:**
- `Event` dataclass has no field validation
- No length limits on any fields
- No type coercion for metadata

**Remediation:**

Option A: **Add Pydantic validation** (recommended for new code):
```python
from pydantic import BaseModel, field_validator, HttpUrl
from datetime import datetime

class ValidatedEvent(BaseModel):
    title: str
    date: datetime
    venue: str
    url: HttpUrl | str
    category: str
    metadata: dict = {}

    @field_validator('title')
    @classmethod
    def title_must_be_sane(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Title too long - possible scraper error")
        if len(v) < 2:
            raise ValueError("Title too short")
        return v.strip()

    @field_validator('venue')
    @classmethod
    def venue_must_be_sane(cls, v: str) -> str:
        if len(v) > 100:
            raise ValueError("Venue name too long")
        return v.strip()
```

Option B: **Add validation in existing dataclass** (minimal change):
```python
def __post_init__(self) -> None:
    if len(self.title) > 200:
        raise ValueError(f"Title too long: {len(self.title)} chars")
    if not self.title.strip():
        raise ValueError("Empty title")
```

---

### BS-3: Telegram Token Security

**Severity: Medium**

The bot token is embedded in URL strings (`notifier.py:116`). If httpx raises an exception containing the URL, the token could leak to logs.

**Current State:**
```python
url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
# If this fails, exception message may contain the URL
```

**Remediation:**

```python
# notifier.py - Updated send_telegram_message()
def send_telegram_message(message: str) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")

    try:
        with httpx.Client(
            base_url="https://api.telegram.org",
            timeout=30
        ) as client:
            response = client.post(
                f"/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
            )
            response.raise_for_status()
            return response.json().get("ok", False)

    except httpx.RequestError as exc:
        # Log error type only - never log the exception directly
        logger.error("Telegram request failed: %s", type(exc).__name__)
        return False
    except httpx.HTTPStatusError as exc:
        logger.error("Telegram API error: %d", exc.response.status_code)
        return False
```

---

### BS-4: Rate Limiting for Scrapers

**Severity: Low**

Scrapers fire requests without delays. Could trigger IP blocks or be perceived as abuse.

**Current State:**
- No delay between requests
- No retry logic for transient failures

**Remediation:**

1. **Add delay configuration** (`config.py`):
```python
SCRAPE_DELAY_SECONDS: Final[float] = 1.0
SCRAPE_MAX_RETRIES: Final[int] = 2
```

2. **Implement in aggregator** (`aggregator.py`):
```python
import time
from kinoweek.config import SCRAPE_DELAY_SECONDS

for i, source_cls in enumerate(sources):
    if i > 0:
        time.sleep(SCRAPE_DELAY_SECONDS)
    try:
        events.extend(source_cls().fetch())
    except Exception as e:
        logger.warning("Source %s failed: %s", source_cls.source_name, e)
```

3. **Add retry transport** (`sources/base.py`):
```python
from httpx import HTTPTransport

def create_http_client() -> httpx.Client:
    transport = HTTPTransport(retries=2)
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
```

---

## Frontend Security

### FS-1: URL Injection Prevention

**Severity: High**

`MovieCard.astro` and `ConcertCard.astro` render `href={url}` directly. Malicious `javascript:` or `data:` URLs would execute code.

**Current State:**
```astro
<a href={url} target="_blank" rel="noopener noreferrer">
```

**Remediation:**

1. **Create URL sanitizer utility** (`web/src/utils/sanitize.ts`):
```typescript
/**
 * Sanitize URL to prevent javascript: and data: injection
 */
export function sanitizeUrl(url?: string): string {
  if (!url) return '#';

  const trimmed = url.trim();
  if (trimmed.length === 0) return '#';

  // Block dangerous protocols
  const lower = trimmed.toLowerCase();
  if (lower.startsWith('javascript:') ||
      lower.startsWith('data:') ||
      lower.startsWith('vbscript:')) {
    return '#';
  }

  // Only allow http/https
  if (!lower.startsWith('http://') && !lower.startsWith('https://')) {
    return '#';
  }

  return trimmed;
}
```

2. **Apply in components** (`MovieCard.astro`):
```astro
---
import { sanitizeUrl } from '../utils/sanitize';

const safeUrl = sanitizeUrl(url);
---
<a href={safeUrl} target="_blank" rel="noopener noreferrer">
```

---

### FS-2: Content Security Policy

**Severity: Medium**

No CSP headers configured. Any XSS vulnerability has full DOM access.

**Current State:**
- No `_headers` file
- No security headers in Astro config
- Project uses Astro 4.16.0

**The Astro CSP Challenge:**

> ⚠️ **Important:** Astro 4.x bundles component scripts inline by default, which requires `script-src 'unsafe-inline'` in CSP. This weakens XSS protection since injected `<script>` tags would execute. See [Astro issue #6407](https://github.com/withastro/astro/issues/6407).

**Options:**

1. **Astro 5.9+ Experimental CSP** (recommended if upgrading):
   ```js
   // astro.config.mjs
   export default defineConfig({
     experimental: {
       csp: true  // Auto-generates SHA-256 hashes for inline scripts
     }
   });
   ```
   This eliminates `unsafe-inline` by generating hashes automatically.

2. **Astro 4.x with `unsafe-inline`** (current version):
   Since full CSP requires Astro 5.9+, use `unsafe-inline` for now but ensure backend sanitization is robust.

**Remediation (Astro 4.x):**

Create `web/public/_headers`:
```
/*
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https: data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
```

> **Note:** `style-src 'unsafe-inline'` is acceptable when `script-src` is controlled. The primary XSS vector is script injection, not style injection.

**For Cloudflare Pages**, this file is automatically respected.

**For Nginx** (if self-hosting):
```nginx
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' https: data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none';" always;
add_header X-Frame-Options "DENY" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

**Future Improvement:** Upgrade to Astro 5.9+ and enable experimental CSP to remove `unsafe-inline`.

---

### FS-3: External Font Security

**Severity: Low**

Google Fonts loaded via external `@import` without integrity verification.

**Current State:**
```css
@import url('https://fonts.googleapis.com/css2?family=Inter...');
```

**Remediation Options:**

**Option A: Self-host fonts** (recommended):
```bash
cd web && npm install @fontsource/inter @fontsource/space-mono
```

```css
/* global.css */
@import '@fontsource/inter/400.css';
@import '@fontsource/inter/500.css';
@import '@fontsource/inter/600.css';
@import '@fontsource/space-mono/400.css';
```

**Option B: Add preconnect hints** (`Base.astro`):
```html
<link rel="preconnect" href="https://fonts.googleapis.com" crossorigin>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
```

---

## German Legal Compliance

Operating a public website in Germany requires compliance with DDG (Digitale-Dienste-Gesetz), MStV (Medienstaatsvertrag), and DSGVO.

### GL-1: Impressum (Required)

**Severity: High (Legal)**

Per § 5 DDG (replaced TMG as of May 2024) and § 18 MStV, a publicly accessible website must have an Impressum.

**Requirements:**
- Name and address (no P.O. Box)
- Contact information enabling "schnelle elektronische Kontaktaufnahme und unmittelbare Kommunikation" (quick electronic contact and direct communication)
- For journalistic-editorial content (which KinoWeek is): responsible person per § 18 Abs. 2 MStV

**Phone Number Clarification:**

> Per [ECJ ruling 2008](https://www.e-recht24.de/impressum/1023-impressum-telefonnummer.html), a phone number is **not strictly mandatory** if another direct communication channel exists (e.g., responsive email). However:
> - Email responses should be within 24-48 hours
> - For **online retailers**, phone IS mandatory (Verbraucherrechterichtlinie)
> - For hobby/informational sites like KinoWeek, email alone is legally sufficient
>
> **Optional but recommended:** A SIP number (Sipgate, Satellite App) adds legal safety and user trust.

**Remediation:**

Create `web/src/pages/impressum.astro`:
```astro
---
import Base from '../layouts/Base.astro';
---
<Base title="Impressum - boringhannover">
  <main id="main-content" class="prose prose-invert">
    <h1>Impressum</h1>

    <h2>Angaben gemäß § 5 DDG</h2>
    <p>
      [Your Full Name]<br>
      [Street Address]<br>
      [Postal Code] [City]<br>
      Germany
    </p>

    <h2>Kontakt</h2>
    <p>
      E-Mail: [your-email]@[domain].de
    </p>

    <h2>Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV</h2>
    <p>
      [Your Full Name]<br>
      [Street Address]<br>
      [Postal Code] [City]
    </p>

    <h2>Haftungsausschluss (Disclaimer)</h2>

    <h3>Haftung für Inhalte</h3>
    <p>
      Die Inhalte unserer Seiten wurden mit größter Sorgfalt erstellt.
      Für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte
      können wir jedoch keine Gewähr übernehmen.
    </p>

    <h3>Haftung für Links</h3>
    <p>
      Unser Angebot enthält Links zu externen Webseiten Dritter, auf deren
      Inhalte wir keinen Einfluss haben. Deshalb können wir für diese
      fremden Inhalte auch keine Gewähr übernehmen. Für die Inhalte der
      verlinkten Seiten ist stets der jeweilige Anbieter oder Betreiber
      der Seiten verantwortlich.
    </p>
  </main>
</Base>
```

---

### GL-2: Datenschutzerklärung (Privacy Policy)

**Severity: High (Legal)**

DSGVO requires informing users about data processing.

**Key Advantage:** If you use NO cookies, NO analytics, and NO user tracking, you can skip the cookie consent banner.

**Remediation:**

Create `web/src/pages/datenschutz.astro`:
```astro
---
import Base from '../layouts/Base.astro';
---
<Base title="Datenschutzerklärung - boringhannover">
  <main id="main-content" class="prose prose-invert">
    <h1>Datenschutzerklärung</h1>

    <h2>1. Datenschutz auf einen Blick</h2>

    <h3>Allgemeine Hinweise</h3>
    <p>
      Die folgenden Hinweise geben einen einfachen Überblick darüber,
      was mit Ihren personenbezogenen Daten passiert, wenn Sie diese
      Website besuchen.
    </p>

    <h3>Datenerfassung auf dieser Website</h3>
    <p>
      <strong>Wir verwenden keine Cookies und kein User-Tracking.</strong>
      Es findet keine Speicherung personenbezogener Daten auf Ihrem
      Endgerät statt, die über die technisch notwendige Verarbeitung
      hinausgeht.
    </p>

    <h2>2. Hosting</h2>
    <p>
      Diese Website wird extern gehostet. Die personenbezogenen Daten,
      die auf dieser Website erfasst werden, werden auf den Servern des
      Hosters gespeichert. Hierbei kann es sich v.a. um IP-Adressen,
      Kontaktanfragen, Meta- und Kommunikationsdaten, Vertragsdaten,
      Kontaktdaten, Namen, Websitezugriffe und sonstige Daten, die über
      eine Website generiert werden, handeln.
    </p>

    <h2>3. Allgemeine Hinweise und Pflichtinformationen</h2>

    <h3>Datenschutz</h3>
    <p>
      Die Betreiber dieser Seiten nehmen den Schutz Ihrer persönlichen
      Daten sehr ernst. Wir behandeln Ihre personenbezogenen Daten
      vertraulich und entsprechend den gesetzlichen Datenschutzvorschriften
      sowie dieser Datenschutzerklärung.
    </p>

    <h3>Hinweis zur verantwortlichen Stelle</h3>
    <p>
      Die verantwortliche Stelle für die Datenverarbeitung auf dieser
      Website ist:<br><br>
      [Your Full Name]<br>
      [Street Address]<br>
      [Postal Code] [City]<br>
      E-Mail: [your-email]@[domain].de
    </p>

    <h2>4. Datenerfassung auf dieser Website</h2>

    <h3>Server-Log-Dateien</h3>
    <p>
      Der Provider der Seiten erhebt und speichert automatisch Informationen
      in so genannten Server-Log-Dateien, die Ihr Browser automatisch an uns
      übermittelt. Dies sind:
    </p>
    <ul>
      <li>Browsertyp und Browserversion</li>
      <li>verwendetes Betriebssystem</li>
      <li>Referrer URL</li>
      <li>Hostname des zugreifenden Rechners</li>
      <li>Uhrzeit der Serveranfrage</li>
      <li>IP-Adresse</li>
    </ul>
    <p>
      Eine Zusammenführung dieser Daten mit anderen Datenquellen wird
      nicht vorgenommen. Die Erfassung dieser Daten erfolgt auf Grundlage
      von Art. 6 Abs. 1 lit. f DSGVO.
    </p>

    <h2>5. Externe Links</h2>
    <p>
      Diese Website enthält Links zu externen Websites (Ticketshops,
      Veranstaltungsorte). Für den Datenschutz auf diesen externen
      Seiten sind die jeweiligen Betreiber verantwortlich.
    </p>
  </main>
</Base>
```

---

### GL-3: Footer Links

Add links to legal pages in `Footer.astro`:
```astro
<footer class="mt-12 pt-6 border-t border-border text-center">
  <!-- existing content -->

  <nav class="mt-4 font-display text-xs text-text-muted">
    <a href="/impressum" class="hover:text-text-secondary">Impressum</a>
    <span class="mx-2">&middot;</span>
    <a href="/datenschutz" class="hover:text-text-secondary">Datenschutz</a>
  </nav>
</footer>
```

---

## Accessibility (WCAG 2.1 AA)

### A-1: Time Element Semantics

**Severity: Medium**

Dates displayed as plain text cannot be parsed by screen readers or search engines.

**Current State:**
```astro
<div class="font-display text-sm">{date}</div>  <!-- "29 Nov" -->
```

**Remediation:**

1. **Add ISO date to data model** (`web_events.json`):
```json
{
  "date": "29 Nov",
  "isoDate": "2025-11-29T20:00:00",
  ...
}
```

2. **Update ConcertCard.astro**:
```astro
---
interface Props {
  date: string;
  isoDate?: string;  // ISO 8601 format
  // ...
}
---
<time datetime={isoDate} class="font-display text-sm text-text-secondary">
  {date}
</time>
```

---

### A-2: Skip Navigation Link

**Severity: Medium**

Keyboard users must tab through header on every page.

**Remediation:**

Add to `Base.astro` after `<body>`:
```astro
<body class="bg-bg-primary min-h-screen">
  <a
    href="#main-content"
    class="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:bg-bg-primary focus:px-4 focus:py-2 focus:text-accent focus:outline focus:outline-2 focus:outline-accent"
  >
    Skip to content
  </a>
  <!-- rest of body -->
</body>
```

Add `id="main-content"` to main content in `index.astro`:
```astro
<Base title="...">
  <main id="main-content">
    <Header ... />
    <!-- sections -->
  </main>
</Base>
```

---

### A-3: Section Landmarks and Heading Hierarchy

**Severity: Medium**

Sections lack `aria-labelledby` and proper heading structure.

**Remediation:**

Update `SectionHeader.astro`:
```astro
---
interface Props {
  title: string;
  id?: string;
}
const { title, id } = Astro.props;
---
<h2 id={id} class="font-display text-sm font-bold uppercase tracking-wide text-text-secondary mb-4">
  {title}
</h2>
```

Update `index.astro`:
```astro
<section aria-labelledby="movies-heading" class="mb-10">
  <SectionHeader title="Movies This Week" id="movies-heading" />
  <!-- content -->
</section>

<section aria-labelledby="concerts-heading" class="mb-10">
  <SectionHeader title="Events On The Radar" id="concerts-heading" />
  <!-- content -->
</section>
```

---

### A-4: Theme Toggle State

**Severity: Low**

Toggle doesn't announce current state to screen readers.

**Remediation:**

Update `Header.astro` button:
```astro
<button
  id="theme-toggle"
  type="button"
  aria-label="Toggle theme"
  aria-pressed="false"
  class="..."
>
```

Update script:
```javascript
toggle?.addEventListener('click', () => {
  const isDark = document.documentElement.classList.toggle('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  toggle.setAttribute('aria-pressed', isDark.toString());
  // ...
});

// Set initial state
const isDark = document.documentElement.classList.contains('dark');
toggle?.setAttribute('aria-pressed', isDark.toString());
```

---

### A-5: Focus Indicators

**Severity: Low**

Card focus states not visible for keyboard navigation.

**Remediation:**

Add to `global.css`:
```css
/* Focus indicators for keyboard navigation */
.card-hover:focus-visible {
  @apply outline-2 outline-offset-2 outline-accent;
}

a:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
```

---

### A-6: Color Contrast

**Severity: Low**

`--text-muted: #999999` on light background has ~2.8:1 ratio (needs 4.5:1).

**Remediation:**

Update `global.css`:
```css
:root {
  /* Improved contrast for muted text */
  --text-muted: #666666;  /* ~6:1 ratio on #fafaf9 */
}

:root.dark {
  --text-muted: #888888;  /* ~5:1 ratio on #0a0a0a */
}
```

---

### A-7: Reduced Motion (Already Implemented)

**Status: Compliant**

The codebase already includes proper `prefers-reduced-motion` support in `global.css`:

```css
@media (prefers-reduced-motion: reduce) {
  .stagger-item,
  .section-fade,
  .card-hover {
    animation: none;
    transition: none;
    opacity: 1;
    transform: none;
  }
}
```

---

### A-8: Font Fallback for "Nothing" Aesthetic

**Severity: Low**

Dot matrix or stylized fonts may have poor legibility at small sizes or fail to load.

**Remediation:**

Ensure graceful font degradation in `tailwind.config.mjs` or `global.css`:
```css
/* Ensure dot-matrix/display fonts fall back to readable monospace */
.font-display {
  font-family: 'Space Mono', 'Courier New', Courier, monospace;
}

/* Body text should fall back to system sans-serif */
.font-body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```

This preserves the "tech" aesthetic while ensuring readability if custom fonts fail.

---

## Infrastructure Hardening

### IH-1: Cloudflare WAF Configuration

For Cloudflare free plan, add these rules:

**Bot Fight Mode:** Enable in Security > Bots

**Geo-Blocking Rule** (optional, for DACH-only content):
```
(ip.geoip.country ne "DE" and ip.geoip.country ne "AT" and ip.geoip.country ne "CH")
→ Action: Managed Challenge
```

---

### IH-2: Nginx Rate Limiting

If self-hosting on Hetzner with Nginx:

```nginx
# In http block
limit_req_zone $binary_remote_addr zone=static_limit:10m rate=30r/m;

# In server block
location / {
    limit_req zone=static_limit burst=50 nodelay;
    # ...
}

# Stricter limit for data endpoint
location /data/ {
    limit_req zone=static_limit burst=10 nodelay;
    add_header Cache-Control "public, max-age=300";
}
```

---

## Data Integrity & Monitoring

### DI-1: Atomic JSON Writes

**Issue:** If scraper crashes mid-write, `web_events.json` could be corrupted.

**Remediation:**

Update `exporters.py`:
```python
import tempfile
import shutil

def export_web_json(...) -> None:
    json_path = output_path / "web_events.json"

    # Write to temp file first
    # CRITICAL: dir=output_path ensures temp file is on the SAME filesystem
    # as the target. This makes shutil.move() a true atomic rename() syscall.
    # Without this, Docker volume mounts would cause copy+delete (non-atomic).
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        dir=output_path,  # DO NOT REMOVE - required for atomicity
        delete=False,
        encoding='utf-8'
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = tmp.name

    # Validate temp file has content
    if Path(tmp_path).stat().st_size < 100:
        Path(tmp_path).unlink()
        raise ValueError("Generated JSON too small - possible scraper failure")

    # Atomic rename (only works if source and dest are on same filesystem)
    shutil.move(tmp_path, json_path)
```

> ⚠️ **Docker Note:** `shutil.move()` is only atomic if source and destination are on the **same filesystem**. If your Docker container writes to `/tmp` (overlay FS) and moves to `/app/output` (mounted volume), it performs a copy-delete which is NOT atomic. The `dir=output_path` parameter above ensures the temp file is created on the mounted volume, making the move a true atomic `rename()` syscall.

---

### DI-2: Dead Link Monitoring

Create a weekly GitHub Action or cron job:

```python
# scripts/check_links.py
import httpx
import json
from pathlib import Path

# Use a proper User-Agent - ticket providers often block Python's default
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; KinoWeekBot/1.0; +https://boringhannover.de)"
}

def check_links():
    data = json.loads(Path("output/web_events.json").read_text())
    dead_links = []

    with httpx.Client(
        timeout=10,
        follow_redirects=True,
        headers=HEADERS
    ) as client:
        for concert in data.get("concerts", []):
            url = concert.get("url")
            if url:
                try:
                    resp = client.head(url)
                    if resp.status_code >= 400:
                        dead_links.append((concert["title"], url, resp.status_code))
                except httpx.RequestError:
                    dead_links.append((concert["title"], url, "ERROR"))

    if dead_links:
        print("Dead links found:")
        for title, url, status in dead_links:
            print(f"  - {title}: {url} ({status})")
        return 1
    return 0
```

---

## Implementation Checklist

### Phase 1: Critical Security (Week 1) ✅ COMPLETED

- [x] **BS-1:** Install `nh3`, create `sanitize.py`, apply to all scrapers
- [x] **FS-1:** Create `web/src/utils/sanitize.ts`, update card components
- [x] **FS-2:** Create `web/public/_headers` with CSP
- [x] **GL-1:** Create `impressum.astro` with legal information
- [x] **GL-2:** Create `datenschutz.astro` privacy policy
- [x] **GL-3:** Add footer links to legal pages

### Phase 2: Accessibility (Week 2) ✅ COMPLETED

- [x] **A-2:** Add skip navigation link to `Base.astro`
- [x] **A-3:** Update `SectionHeader.astro` with proper `<h2>` and IDs
- [x] **A-4:** Add `aria-pressed` to theme toggle
- [x] **A-5:** Add focus-visible styles to `global.css`
- [x] **A-6:** Fix color contrast for muted text (light: #767676, dark: #9ca3af)

### Phase 3: Hardening (Week 3) ✅ COMPLETED

- [x] **BS-2:** Add dataclass validation (`__post_init__` in `models.py`)
- [x] **BS-3:** Refactor Telegram token handling (base_url pattern in `notifier.py`)
- [x] **BS-4:** Add rate limiting and retry logic (`aggregator.py`, `config.py`)
- [x] **DI-1:** Implement atomic JSON writes (`exporters.py` with tempfile)
- [ ] **FS-3:** Self-host fonts (optional - deferred)

### Phase 4: Monitoring (Week 4)

- [ ] **DI-2:** Create dead link checker script
- [ ] **IH-1:** Configure Cloudflare WAF rules
- [ ] Set up error alerting (optional)

---

## References

### Security
- [OWASP Top 10 Web Application Security Risks](https://owasp.org/www-project-top-ten/)
- [nh3 - Python HTML Sanitizer](https://github.com/messense/nh3) (replacement for deprecated bleach)
- [Ammonia - Rust HTML Sanitizer](https://github.com/rust-ammonia/ammonia)
- [Bleach Deprecation Notice (Jan 2023)](https://github.com/mozilla/bleach/issues/698)

### Astro & CSP
- [Astro CSP Issue #6407](https://github.com/withastro/astro/issues/6407)
- [Astro 5.9 Experimental CSP](https://docs.astro.build/en/reference/experimental-flags/csp/)
- [Astro Security Headers](https://docs.astro.build/en/guides/troubleshooting/)

### German Legal
- [§ 5 DDG - Allgemeine Informationspflichten](https://www.gesetze-im-internet.de/ddg/__5.html)
- [§ 18 MStV - Informationspflichten](https://dr-dsgvo.de/18-mstv-informationspflichten-und-auskunftsrechte/)
- [Impressum Phone Requirement (ECJ Ruling)](https://www.e-recht24.de/impressum/1023-impressum-telefonnummer.html)
- [Medienstaatsvertrag Overview](https://www.e-recht24.de/online-marketing/12436-medienstaatsvertrag.html)
- [DSGVO Compliance](https://dsgvo-gesetz.de/)

### Accessibility
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/)

---

## Review Notes

### Verification Summary (2025-11-23)

This document was reviewed against external feedback. Key verifications:

| Claim | Verification | Source |
|-------|--------------|--------|
| `bleach` is deprecated | ✅ Confirmed (Jan 2023) | [GitHub Issue #698](https://github.com/mozilla/bleach/issues/698) |
| `nh3` is recommended replacement | ✅ Confirmed (~20x faster) | [PyPI](https://pypi.org/project/nh3/), [GitHub](https://github.com/messense/nh3) |
| Astro 4.x requires `unsafe-inline` | ✅ Confirmed | [Astro Issue #6407](https://github.com/withastro/astro/issues/6407) |
| Astro 5.9+ has experimental CSP | ✅ Confirmed | [Astro Docs](https://docs.astro.build/en/reference/experimental-flags/csp/) |
| Phone mandatory for Impressum | ❌ Overstated | [ECJ 2008 ruling](https://www.e-recht24.de/impressum/1023-impressum-telefonnummer.html) - email sufficient for non-retailers |
| `shutil.move` atomicity on Docker | ⚠️ Nuanced | Requires `dir=` on same filesystem |

### Changes Made
1. Replaced `bleach` with `nh3` throughout document
2. Added Astro CSP nuance (4.x vs 5.9+)
3. Clarified phone number requirement (not mandatory for non-commercial sites)
4. Added Docker atomicity warning for `shutil.move()`
5. Added User-Agent recommendation for dead link checker
6. Added font fallback accessibility section (A-8)
