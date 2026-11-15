import { ArrowUpRight, AudioLines, Boxes, Cloud, Cpu, Server } from "lucide-react";
import type { getServiceStatus } from "@/lib/services";

type Services = Awaited<ReturnType<typeof getServiceStatus>>;

const icons = { nextcloud: Cloud, n8n: Boxes, lfm3: Cpu } as const;

export function ServiceCards({ services }: { services: Services }) {
  return (
    <div className="service-grid">
      {services.map((service) => {
        const Icon = icons[service.id];
        const online = service.state === "online";
        return (
          <article className="service-card" key={service.id}>
            <div className="service-card-top">
              <span className="service-icon"><Icon size={19} /></span>
              <span className={`status-tag ${online ? "online" : "offline"}`}>
                <span className="status-dot" />{online ? "Disponível" : "Sem resposta"}
              </span>
            </div>
            <h3>{service.name}</h3>
            <p>{service.description}</p>
            <div className="card-divider" />
            <a className="service-card-foot service-card-link" href={service.url} target="_blank" rel="noreferrer">
              {service.label}<ArrowUpRight size={14} />
            </a>
          </article>
        );
      })}
      <article className="service-card local-agent-card">
        <div className="service-card-top"><span className="service-icon"><AudioLines size={19} /></span><span className="status-tag pending"><span className="status-dot" />Estado local</span></div>
        <h3>Drisa no portátil</h3>
        <p>Gateway de voz e modelos locais. O estado não é sondado pela VPS.</p>
        <div className="card-divider" />
        <span className="service-card-foot">Usa a app Iku no telemóvel <Server size={14} /></span>
      </article>
    </div>
  );
}
