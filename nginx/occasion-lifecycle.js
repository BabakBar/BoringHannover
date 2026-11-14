import deadlines from '/usr/share/nginx/html/occasion-lifecycle.js';

function noStore(r) {
    r.headersOut['Cache-Control'] = 'no-store';
    r.headersOut['CDN-Cache-Control'] = 'no-store';
    r.headersOut['Cloudflare-CDN-Cache-Control'] = 'no-store';
}

function notFound(r) {
    noStore(r);
    r.headersOut['X-Robots-Tag'] = 'noindex, follow';
    r.headersOut['Content-Type'] = 'text/plain; charset=utf-8';
    r.return(404, 'Not found\n');
}

function guard(r) {
    noStore(r);
    if (r.uri === '/special/') return;
    const query = r.variables.is_args + r.variables.args;
    if (r.uri === '/special/index.html') {
        r.return(301, '/special/' + query);
        return;
    }
    const match = /^\/special\/([a-z0-9-]+)(?:\/|\/index\.html|\.html)?$/.exec(r.uri);
    const deadline = match && deadlines[match[1]];
    const now = Date.now();
    if (!deadline || !Number.isFinite(deadline.endedAt) ||
        !Number.isFinite(deadline.expiresAt) || deadline.endedAt >= deadline.expiresAt ||
        now >= deadline.expiresAt) {
        notFound(r);
        return;
    }
    if (now >= deadline.endedAt) r.headersOut['X-Robots-Tag'] = 'noindex, follow';
    const canonical = '/special/' + match[1] + '/';
    if (r.uri !== canonical) r.return(301, canonical + query);
}

export default { guard, notFound };
