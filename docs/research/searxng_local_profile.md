# Local SearXNG research profile

Elysia's governed public-web research path uses a user-owned SearXNG service bound to loopback. SearXNG is optional and is not part of Core. Installing it does not turn Internet ON, grant approval, or allow private Project/Memory context outward.

```bash
scripts/manage_searxng.sh install
scripts/manage_searxng.sh status
scripts/manage_searxng.sh verify
scripts/manage_searxng.sh stop
scripts/manage_searxng.sh start
```

The explicit `install` action acquires the official SearXNG container image through Podman (preferred for rootless use) or an already accessible Docker service. It creates owner-only configuration, data, state, and a local worker override under XDG locations. The service binds only to `127.0.0.1:8888`; it is not exposed to the LAN.

Successful installation must complete an actual JSON search before the worker is enabled. Health can probe loopback without sending a query. A real Research action still requires Internet ON and sends only the user's public-safe bounded query terms through the worker. Those terms and network metadata may reach upstream public search engines. Elysia does not append private sources, Memory, journals, credentials, or hidden context.

Stopping the service preserves the user's SearXNG configuration and state. Elysia then reports the dependency as unavailable rather than inventing evidence.
