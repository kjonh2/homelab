import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Iku — o teu espaço digital",
  description: "Um ponto de entrada privado para os teus serviços, dispositivos e assistentes.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-PT">
      <body>{children}</body>
    </html>
  );
}
