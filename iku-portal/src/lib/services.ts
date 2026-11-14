export type ServiceState = "online" | "offline";

export type MonitoredService = {
  id: "nextcloud" | "n8n" | "lfm3";
  name: string;
  description: string;
  url: string;
  probeUrl: string;
  label: string;
};

const services: MonitoredService[] = [
  {
    id: "nextcloud",
    name: "Nextcloud",
    description: "Ficheiros e espaço pessoal",
    url: "https://vps-4e5174e4.tail2931da.ts.net:8444/",
    probeUrl: process.env.NEXTCLOUD_HEALTH_URL ?? "http://nextcloud.iku.svc.cluster.local/status.php",
    label: "Abrir ficheiros",
  },
  {
    id: "n8n",
    name: "n8n",
    description: "Workflows e automações",
    url: "https://vps-4e5174e4.tail2931da.ts.net:8443/",
    probeUrl: process.env.N8N_HEALTH_URL ?? "http://n8n.iku.svc.cluster.local:5678/healthz",
    label: "Abrir automações",
  },
  {
    id: "lfm3",
    name: "Modelos LFM3",
    description: "Inferência de texto e áudio na VPS",
    url: "https://vps-4e5174e4.tail2931da.ts.net:8445/",
    probeUrl: process.env.LFM3_HEALTH_URL ?? "http://lfm3-api.iku.svc.cluster.local:8080/health",
    label: "Abrir API de modelos",
  },
];

export async function getServiceStatus() {
  return Promise.all(services.map(async (service) => {
    try {
      const response = await fetch(service.probeUrl, {
        cache: "no-store",
        signal: AbortSignal.timeout(2500),
      });
      return { ...service, state: response.ok ? "online" as const : "offline" as const };
    } catch {
      return { ...service, state: "offline" as const };
    }
  }));
}
