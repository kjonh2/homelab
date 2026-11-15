import type { Metadata } from "next";
import { InviteAcceptForm } from "@/components/iku/invite-accept-form";

export const metadata: Metadata = { title: "Ativar conta — Iku" };
export const dynamic = "force-dynamic";

export default function InvitePage() {
  return <InviteAcceptForm />;
}
