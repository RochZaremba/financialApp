import type { Metadata, Viewport } from "next";
import "@fontsource-variable/manrope";
import "./globals.css";
import { Application } from "@/components/application";
export const metadata: Metadata = {
  title: "Razem. · spokojny budżet domowy",
  description: "Wspólny dom. Wspólny plan. Prosty budżet Rocha i Kai.",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "Razem." },
  icons: { icon: "/icon.svg", apple: "/icon-192.png" },
};
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#216650",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pl">
      <body>
        <Application>{children}</Application>
      </body>
    </html>
  );
}
