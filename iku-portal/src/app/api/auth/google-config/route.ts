import { readFile } from "node:fs/promises";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type GoogleServicesConfig = {
  project_info?: { project_id?: string };
  client?: Array<{
    api_key?: Array<{ current_key?: string }>;
    oauth_client?: Array<{ client_id?: string; client_type?: number }>;
  }>;
};

export async function GET(): Promise<Response> {
  try {
    const configPath = process.env.IKU_FIREBASE_CONFIG_PATH ?? "/run/iku-firebase/google-services.json";
    const config = JSON.parse(await readFile(/* turbopackIgnore: true */ configPath, "utf8")) as GoogleServicesConfig;
    const clients = config.client ?? [];
    const apiKey = clients.flatMap((client) => client.api_key ?? []).find((key) => key.current_key)?.current_key;
    const webClientId = clients.flatMap((client) => client.oauth_client ?? [])
      .find((client) => client.client_type === 3)?.client_id;
    const projectId = config.project_info?.project_id;

    if (!apiKey || !webClientId || !projectId) {
      return Response.json({ configured: false }, { status: 503, headers: { "Cache-Control": "no-store" } });
    }

    // These are public Firebase web-client values. Never return the complete
    // Android configuration file or its unrelated app identifiers.
    return Response.json(
      { configured: true, apiKey, clientId: webClientId, projectId },
      { headers: { "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" } },
    );
  } catch {
    return Response.json({ configured: false }, { status: 503, headers: { "Cache-Control": "no-store" } });
  }
}
