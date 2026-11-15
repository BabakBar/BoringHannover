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
    const calendar = /^\/special\/([a-z0-9-]+)\/calendar\/(\d{4}-\d{2}-\d{2})\.ics$/.exec(r.uri);
    const match = calendar || /^\/special\/([a-z0-9-]+)(?:\/|\/index\.html|\.html)?$/.exec(r.uri);
    const deadline = match && deadlines[match[1]];
    const now = Date.now();
    if (!deadline || !Number.isFinite(deadline.endedAt) ||
        !Number.isFinite(deadline.expiresAt) || deadline.endedAt >= deadline.expiresAt ||
        now >= deadline.expiresAt) {
        notFound(r);
        return;
    }
    if (calendar) {
        const expiresAt = deadline.calendar && deadline.calendar[calendar[2]];
        if (!Number.isFinite(expiresAt) || now >= expiresAt) {
            notFound(r);
            return;
        }
        r.headersOut['Content-Type'] = 'text/calendar; charset=utf-8';
        r.headersOut['Content-Disposition'] = 'attachment; filename="' + calendar[1] + '-' + calendar[2] + '.ics"';
        r.headersOut['X-Robots-Tag'] = 'noindex, follow';
        return;
    }
    if (now >= deadline.endedAt) r.headersOut['X-Robots-Tag'] = 'noindex, follow';
    const canonical = '/special/' + match[1] + '/';
    if (r.uri !== canonical) r.return(301, canonical + query);
}

export default { guard, notFound };
