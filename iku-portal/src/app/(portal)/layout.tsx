import { PortalShell } from "@/components/iku/portal-shell";

export default function PortalLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <PortalShell>{children}</PortalShell>;
}
