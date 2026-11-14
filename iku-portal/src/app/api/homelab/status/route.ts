import { NextResponse } from "next/server";
import { getServiceStatus } from "@/lib/services";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ") || authorization.length > 4096) {
    return NextResponse.json({ detail: "not_authenticated" }, { status: 401 });
  }

  const authBase = (process.env.IKU_AUTH_URL ?? "http://iku-auth.iku.svc.cluster.local:8080").replace(/\/$/, "");
  let session: Response;
  try {
    session = await fetch(`${authBase}/v1/auth/session`, {
      headers: { Authorization: authorization },
      cache: "no-store",
      signal: AbortSignal.timeout(4_000),
    });
  } catch {
    return NextResponse.json({ detail: "auth_service_unavailable" }, {
      status: 503,
      headers: { "Cache-Control": "no-store" },
    });
  }
  if (!session.ok) {
    await session.body?.cancel();
    const status = session.status === 401 ? 401 : session.status === 403 ? 403 : 503;
    return NextResponse.json(
      { detail: status === 401 ? "not_authenticated" : status === 403 ? "access_denied" : "auth_service_unavailable" },
      { status, headers: { "Cache-Control": "no-store" } },
    );
  }
  await session.body?.cancel();

  const services = await getServiceStatus();
  return NextResponse.json({
    checked_at: new Date().toISOString(),
    services: services.map(({ id, name, description, url, label, state }) => ({
      id, name, description, url, label, state,
    })),
  }, { headers: { "Cache-Control": "no-store" } });
}
