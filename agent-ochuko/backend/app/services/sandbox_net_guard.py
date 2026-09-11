# app/services/sandbox_net_guard.py
"""
Sandbox egress allowlist — Phase 5 (item #12).

`SANDBOX_NET_ALLOWLIST` (comma-separated host globs, e.g.
"*.adobe.io, api.github.com, registry.npmjs.org"). Empty/unset = allow-all
(backward compatible). When set, a DNS/socket guard shim is injected into the
sandbox so Python AND Node subprocesses are limited to the configured hosts.
The terminal tool inherits the same perimeter automatically (it runs through
the same executor).

Pure decision logic lives in host_allowed(); the shims are small stdlib-only
files written into the sandbox src/ dir and activated via PYTHONPATH
(sitecustomize) / NODE_OPTIONS (--require).
"""
import os
from typing import Dict, List, Optional

_IMPLICIT_ALLOWED = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "metadata?"}

PYTHON_SHIM_NAME = "sitecustomize.py"
NODE_SHIM_NAME = "_net_guard.js"

_PYTHON_SHIM_TEMPLATE = """# Auto-generated sandbox egress guard (SANDBOX_NET_ALLOWLIST) — do not edit.
import os as _os
import socket as _socket

_ALLOWED = [h.strip().lower().rstrip('.') for h in
            _os.environ.get('SANDBOX_NET_ALLOWLIST', '').split(',') if h.strip()]
_ALWAYS = {'localhost', '127.0.0.1', '::1', '0.0.0.0'}


def _host_allowed(host):
    if not _ALLOWED:
        return True
    host = str(host or '').lower().rstrip('.')
    if host in _ALWAYS:
        return True
    for pat in _ALLOWED:
        if pat.startswith('*.'):
            base = pat[2:]
            if host == base or host.endswith('.' + base):
                return True
        elif host == pat:
            return True
    return False


class _EgressBlocked(RuntimeError):
    pass


_orig_create = _socket.create_connection
_orig_gai = _socket.getaddrinfo


def _extract_host(address):
    host = address
    if isinstance(host, (tuple, list)):
        host = host[0]
    return host if isinstance(host, str) else None


def _guarded_create(address, *args, **kwargs):
    host = _extract_host(address)
    if host and not _host_allowed(host):
        raise _EgressBlocked('Blocked by SANDBOX_NET_ALLOWLIST: ' + host)
    return _orig_create(address, *args, **kwargs)


def _guarded_getaddrinfo(host, *args, **kwargs):
    if isinstance(host, str) and not _host_allowed(host):
        raise _EgressBlocked('Blocked by SANDBOX_NET_ALLOWLIST: ' + host)
    return _orig_gai(host, *args, **kwargs)


_socket.create_connection = _guarded_create
_socket.getaddrinfo = _guarded_getaddrinfo
"""

_NODE_SHIM_TEMPLATE = """// Auto-generated sandbox egress guard (SANDBOX_NET_ALLOWLIST) — do not edit.
const ALLOWED = (process.env.SANDBOX_NET_ALLOWLIST || '')
  .split(',').map(s => s.trim().toLowerCase().replace(/\\.$/, '')).filter(Boolean);
const ALWAYS = new Set(['localhost', '127.0.0.1', '::1', '0.0.0.0']);

function hostAllowed(host) {
  if (!ALLOWED.length) return true;
  host = String(host || '').toLowerCase().replace(/\\.$/, '');
  if (ALWAYS.has(host)) return true;
  return ALLOWED.some(p => p.startsWith('*.')
    ? (host === p.slice(2) || host.endsWith('.' + p.slice(2)))
    : host === p);
}

if (ALLOWED.length) {
  const dns = require('dns');
  const origLookup = dns.lookup.bind(dns);
  dns.lookup = function (host, ...rest) {
    if (!hostAllowed(host)) {
      const cb = rest[rest.length - 1];
      const err = new Error('Blocked by SANDBOX_NET_ALLOWLIST: ' + host);
      if (typeof cb === 'function') return process.nextTick(() => cb(err));
      throw err;
    }
    return origLookup(host, ...rest);
  };
}
"""


def parse_allowlist(raw: Optional[str]) -> List[str]:
    """Comma-separated globs → clean lowercase pattern list."""
    return [h.strip().lower().rstrip(".") for h in (raw or "").split(",") if h.strip()]


def host_allowed(host: str, patterns: List[str]) -> bool:
    """Pure decision: empty patterns = allow-all; implicit local hosts always pass."""
    host = (host or "").lower().rstrip(".")
    if not patterns:
        return True
    if host in _IMPLICIT_ALLOWED:
        return True
    for pat in patterns:
        if pat.startswith("*."):
            base = pat[2:]
            if host == base or host.endswith("." + base):
                return True
        elif host == pat:
            return True
    return False


def apply_net_guard(src_dir: str, allowlist_raw: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Writes the shims into src_dir when an allowlist is configured.
    Returns {'python_shim': path|None, 'node_shim': path|None} for the caller
    to activate via PYTHONPATH / NODE_OPTIONS. No allowlist → no files written.
    """
    patterns = parse_allowlist(allowlist_raw)
    if not patterns:
        return {"python_shim": None, "node_shim": None}
    os.makedirs(src_dir, exist_ok=True)
    py_shim = os.path.join(src_dir, PYTHON_SHIM_NAME)
    node_shim = os.path.join(src_dir, NODE_SHIM_NAME)
    with open(py_shim, "w", encoding="utf-8") as f:
        f.write(_PYTHON_SHIM_TEMPLATE)
    with open(node_shim, "w", encoding="utf-8") as f:
        f.write(_NODE_SHIM_TEMPLATE)
    return {"python_shim": py_shim, "node_shim": node_shim}
