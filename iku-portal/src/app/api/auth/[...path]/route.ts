import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const routes = new Map<string, string>([
  ["GET oidc/.well-known/openid-configuration", "oidc/.well-known/openid-configuration"],
  ["GET oidc/jwks", "oidc/jwks"],
  ["GET oidc/authorize", "oidc/authorize"],
  ["GET oidc/userinfo", "oidc/userinfo"],
  ["GET session", "session"],
  ["GET sessions", "sessions"],
  ["GET api-tokens", "api-tokens"],
  ["GET admin/users", "admin/users"],
  ["POST bootstrap", "bootstrap"],
  ["POST bootstrap/verify-mfa", "bootstrap/verify-mfa"],
  ["POST firebase/exchange", "firebase/exchange"],
  ["POST oidc/token", "oidc/token"],
  ["POST login", "login"],
  ["POST refresh", "refresh"],
  ["POST logout", "logout"],
  ["POST sessions/revoke", "sessions/revoke"],
  ["POST api-tokens", "api-tokens"],
  ["POST api-tokens/revoke", "api-tokens/revoke"],
  ["POST admin/invites", "admin/invites"],
  ["POST admin/invites/revoke", "admin/invites/revoke"],
  ["POST admin/users/status", "admin/users/status"],
  ["POST invites/accept", "invites/accept"],
]);

function sessionCookie(request: NextRequest): string | undefined {
  const value = request.cookies.get("iku_session")?.value;
  return value ? `iku_session=${value}` : undefined;
}

async function proxy(request: NextRequest, path: string): Promise<Response> {
  const base = (process.env.IKU_AUTH_URL ?? "http://iku-auth.iku.svc.cluster.local:8080").replace(/\/$/, "");
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  const origin = request.headers.get("origin");
  const authorization = request.headers.get("authorization");
  const cookie = sessionCookie(request);
  if (contentType) headers.set("content-type", contentType);
  if (origin) headers.set("origin", origin);
  if (authorization?.toLowerCase().startsWith("bearer ") || (path === "oidc/token" && authorization?.toLowerCase().startsWith("basic "))) {
    headers.set("authorization", authorization);
  }
  if (cookie) headers.set("cookie", cookie);

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/v1/auth/${path}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body: request.method === "GET" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(8_000),
    });
  } catch {
    return Response.json({ detail: "auth_unavailable" }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }

  const responseHeaders = new Headers({
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);
  const location = upstream.headers.get("location");
  if (location) responseHeaders.set("location", location);
  for (const cookieValue of upstream.headers.getSetCookie()) responseHeaders.append("set-cookie", cookieValue);
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

type RouteContext = { params: Promise<{ path: string[] }> };

async function dispatch(request: NextRequest, method: "GET" | "POST", context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const name = routes.get(`${method} ${path.join("/")}`);
  if (!name) return Response.json({ detail: "not_found" }, { status: 404, headers: { "Cache-Control": "no-store" } });
  return proxy(request, name);
}

export function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return dispatch(request, "GET", context);
}

export function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return dispatch(request, "POST", context);
}
