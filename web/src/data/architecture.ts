import type { Side } from '../utils/diagram';

export type Host = 'outside' | 'github' | 'vps';


export interface Node {
  id: string;
  /** Short prefix for the replay terminal. */
  tag: string;
  title: string;
  tech: string;
  /** File, workflow or setting to read next. */
  ref?: string;
  host: Host;
  x: number;
  y: number;
  /** What it does, in one or two sentences. */
  role: string;
  /** The engineering reason it looks the way it does. */
  why: string;
}

export interface Flow {
  id: 'run' | 'deploy' | 'visit';
  label: string;
}

export interface Edge {
  id: string;
  flow: Flow['id'];
  step: number;
  from: string;
  to: string;
  fromSide: Side;
  toSide: Side;
  fromAt?: number;
  toAt?: number;
  via?: [number, number][];
  protocol: string;
  summary: string;
  /** What travels along the edge, shown on the moving packet. */
  payload: string;
  /** Lines the replay terminal prints when the packet arrives. */
  log: { node: string; text: string }[];
  optional?: boolean;
}

export const VIEWBOX = { width: 1200, height: 700 } as const;

export const nodes: Node[] = [
  { id: 'maintainer', tag: 'git', title: 'Maintainer', tech: 'git push · PRs', ref: '.github/dependabot.yml', host: 'outside', x: 40, y: 60, role: 'Pushes to master and opens PRs. CI runs on every PR, and Dependabot PRs merge on their own once the checks pass.', why: 'Every change goes through CI. Dependency updates arrive as PRs and merge on their own once the checks pass.' },
  { id: 'repo', tag: 'github', title: 'GitHub repo', tech: 'master · web_events.json', ref: 'github_sync.py', host: 'github', x: 270, y: 60, role: 'Holds the code and the data file. The scraper commits web_events.json straight to master, and any push to master can start a deploy.', why: 'One home for the code and the data. Publishing is a plain git commit, so every update is versioned and can be rolled back.' },
  { id: 'ci', tag: 'actions', title: 'GitHub Actions', tech: 'buildx · Trivy · attest', ref: '.github/workflows/deploy.yml', host: 'github', x: 500, y: 60, role: 'Lints, type-checks and tests every PR. On master it works out which image changed, builds only that one with an SBOM and provenance, scans it with Trivy, pushes it and calls the deploy hook.', why: 'Only the image that changed gets rebuilt. Each one ships with an SBOM and a provenance attestation, and a vulnerability scan has to pass before anything deploys.' },
  { id: 'registry', tag: 'ghcr', title: 'GHCR', tech: 'backend · frontend images', ref: 'ghcr.io', host: 'github', x: 730, y: 60, role: 'Where the backend and frontend images live. The VPS pulls from here, and nothing is ever built on the server.', why: 'Images are built once, in CI, and pulled to the server. Nothing is compiled on the VPS.' },
  { id: 'venues', tag: 'venue', title: 'Venue sites', tech: 'HTML · JSON · iCal', ref: 'sources/', host: 'outside', x: 40, y: 240, role: 'The venues\' own websites, ticket APIs and calendars. Each one has a small parser of its own under sources/.', why: 'Every venue gets its own small parser, so one site changing its markup never touches the others.' },
  { id: 'backend', tag: 'backend', title: 'Backend', tech: 'Python 3.14 · httpx · uv', ref: 'boringhannover.main', host: 'vps', x: 270, y: 240, role: 'A Python container that sits idle. Coolify\'s scheduled task runs the scrape inside it: fetch, keep the next 14 days, export, back up, publish.', why: 'Stateless by design. All it produces is files, and each production run is backed up as a verified snapshot.' },
  { id: 'coolify', tag: 'coolify', title: 'Coolify', tech: 'scheduler · deploy API', host: 'vps', x: 500, y: 240, role: 'The deploy tool on the VPS. It owns the scrape schedule, takes the webhook from CI, pulls the new image and swaps the container once its health check passes.', why: 'A deploy is a webhook plus a health-checked container swap, so a new version only takes over once it\'s healthy.' },
  { id: 'storage', tag: 's3', title: 'Object storage', tech: 'S3 API · write-once', ref: 'backup.py', host: 'outside', x: 40, y: 420, role: 'S3-compatible storage. Each production run\'s output goes in as a write-once snapshot with a sha256 manifest.', why: 'Write-once and sha256-verified, so earlier runs can\'t be changed after the fact.' },
  { id: 'umami', tag: 'umami', title: 'Umami', tech: 'analytics · Postgres', ref: 'nginx.conf', host: 'vps', x: 270, y: 420, role: 'Self-hosted analytics with its own Postgres. The browser never talks to it directly; nginx forwards /s/ for it.', why: 'Analytics stay first-party. nginx proxies the tracker, so visitors never make a request to a third party.' },
  { id: 'frontend', tag: 'nginx', title: 'Frontend', tech: 'nginx :8080 · Astro static', ref: 'Dockerfile.web', host: 'vps', x: 500, y: 420, role: 'nginx serving the built Astro site on :8080. Static files, a /health endpoint, and the /s/ forwarding for analytics.', why: 'Plain static files behind nginx, with a /health endpoint. Quick to serve and cheap to run.' },
  { id: 'caddy', tag: 'caddy', title: 'Caddy', tech: 'reverse proxy · TLS', ref: 'Coolify proxy', host: 'vps', x: 730, y: 420, role: 'The reverse proxy Coolify sets up. It handles TLS at the origin and routes each hostname to its container.', why: 'TLS and routing come from the platform\'s labels, so there\'s no hand-written proxy config to maintain.' },
  { id: 'edge', tag: 'cloudflare', title: 'Cloudflare', tech: 'DNS · TLS · cache', host: 'outside', x: 960, y: 420, role: 'DNS, TLS and caching in front of the origin. You don\'t need it: a fork can point DNS straight at the VPS.', why: 'An optional layer for DNS, TLS and caching. A fork can skip it and point DNS straight at the VPS.' },
  { id: 'visitors', tag: 'browser', title: 'Visitors', tech: 'browsers', host: 'outside', x: 960, y: 590, role: 'Browsers. The pages are plain static HTML, with no account and no tracking cookies.', why: 'Just HTML. No account to create and no tracking cookies.' },
];

export const flows: Flow[] = [
  { id: 'run', label: 'Data update' },
  { id: 'deploy', label: 'Deploy' },
  { id: 'visit', label: 'Visitor request' },
];

export const edges: Edge[] = [
  { id: 'start', flow: 'run', step: 1, from: 'coolify', to: 'backend', fromSide: 'l', toSide: 'r', protocol: 'scheduled exec', summary: 'Coolify\'s scheduled task runs python -m boringhannover.main inside the backend container.', payload: 'exec', log: [{ node: 'coolify', text: 'scheduled task fired' }, { node: 'coolify', text: 'docker exec backend python -m boringhannover.main' }] },
  { id: 'scrape', flow: 'run', step: 2, from: 'backend', to: 'venues', fromSide: 'l', toSide: 'r', protocol: 'HTTPS GET', summary: 'Each source fetches its venue, one request at a time with a 1 s pause. The aggregator then keeps the next 14 days and the exporter writes CSV, JSON and Markdown.', payload: 'GET', log: [{ node: 'backend', text: 'Starting BoringHannover scraper' }, { node: 'backend', text: 'Fetching events from all registered sources...' }, { node: 'backend', text: 'Exporting data...' }] },
  { id: 'backup', flow: 'run', step: 3, from: 'backend', to: 'storage', fromSide: 'b', toSide: 't', fromAt: 0.2, via: [[308, 365], [135, 365]], protocol: 'S3 PUT', summary: 'On production runs the output is copied to storage outside the server, write-once and checked against a sha256. Local runs skip it.', payload: 'archive', log: [{ node: 'backend', text: 'Backed up run as snapshot <timestamp>-<sha256 prefix>' }] },
  { id: 'commit', flow: 'run', step: 4, from: 'backend', to: 'repo', fromSide: 't', toSide: 'b', protocol: 'GitHub Contents API', summary: 'PUTs web_events.json to master through the GitHub Contents API.', payload: 'web_events.json', log: [{ node: 'backend', text: 'Syncing data to GitHub...' }, { node: 'backend', text: 'GitHub sync completed - frontend rebuild triggered' }] },
  { id: 'push', flow: 'deploy', step: 1, from: 'maintainer', to: 'repo', fromSide: 'r', toSide: 'l', protocol: 'git push', summary: 'Any push to master starts a deploy, including the scraper\'s own data commit (run step 4).', payload: 'master', log: [{ node: 'maintainer', text: 'push to master' }] },
  { id: 'trigger', flow: 'deploy', step: 2, from: 'repo', to: 'ci', fromSide: 'r', toSide: 'l', protocol: 'push event', summary: 'The Deploy workflow checks whether backend or frontend files changed and builds only what did.', payload: 'push event', log: [{ node: 'ci', text: 'job: Detect Changes' }, { node: 'ci', text: 'job: Build Images' }] },
  { id: 'build', flow: 'deploy', step: 3, from: 'ci', to: 'registry', fromSide: 'r', toSide: 'l', protocol: 'docker push', summary: 'buildx with an SBOM and a provenance attestation, then a Trivy scan, then push. The digest that was deployed goes into the run summary.', payload: 'image + SBOM', log: [{ node: 'ci', text: 'Build and push frontend' }, { node: 'ci', text: 'Attest frontend provenance' }, { node: 'ci', text: 'Scan published images' }] },
  { id: 'hook', flow: 'deploy', step: 4, from: 'ci', to: 'coolify', fromSide: 'b', toSide: 't', protocol: 'POST webhook', summary: 'One authenticated POST per changed image.', payload: 'POST', log: [{ node: 'ci', text: 'Trigger frontend deployment' }, { node: 'ci', text: 'Deployment summary' }] },
  { id: 'pull', flow: 'deploy', step: 5, from: 'registry', to: 'coolify', fromSide: 'b', toSide: 'r', via: [[825, 275]], protocol: 'docker pull', summary: 'The VPS pulls the image. Nothing gets built on it.', payload: 'layers', log: [{ node: 'coolify', text: 'pulling frontend image from ghcr.io' }] },
  { id: 'replace', flow: 'deploy', step: 6, from: 'coolify', to: 'frontend', fromSide: 'b', toSide: 't', protocol: 'replace container', summary: 'The new container has to pass /health before the old one is removed.', payload: 'container', log: [{ node: 'coolify', text: 'new container healthy: GET /health 200' }, { node: 'coolify', text: 'old container removed' }] },
  { id: 'visit', flow: 'visit', step: 1, from: 'visitors', to: 'edge', fromSide: 't', toSide: 'b', protocol: 'HTTPS', summary: 'Cloudflare terminates TLS and serves cached files where it can.', payload: 'GET /', log: [{ node: 'visitors', text: 'GET https://boringhannover.de/' }] },
  { id: 'origin', flow: 'visit', step: 2, from: 'edge', to: 'caddy', fromSide: 'l', toSide: 'r', fromAt: 0.5, protocol: 'HTTPS to origin', summary: 'Proxied to the VPS on 443.', payload: 'GET /', log: [{ node: 'edge', text: 'TLS terminated, forwarding to origin' }] },
  { id: 'route', flow: 'visit', step: 3, from: 'caddy', to: 'frontend', fromSide: 'l', toSide: 'r', protocol: 'HTTP :8080', summary: 'Caddy matches the hostname to the frontend container by its labels. nginx serves files that were built ahead of time.', payload: 'GET /', log: [{ node: 'caddy', text: 'host matched, routing to frontend :8080' }] },
  { id: 'beacon', flow: 'visit', step: 4, from: 'frontend', to: 'umami', fromSide: 'l', toSide: 'r', protocol: '/s/ proxy', optional: true, summary: 'The analytics beacon goes to the frontend\'s own /s/ path and nginx forwards it to Umami, so the browser never makes a third-party request.', payload: 'POST /s/api/send', log: [{ node: 'frontend', text: '/s/ forwarded to the analytics upstream' }] },
];
