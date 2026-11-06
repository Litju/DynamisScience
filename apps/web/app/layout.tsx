import type { Metadata } from "next";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "reactflow/dist/style.css";
import "./globals.css";
import "./performance.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Dynamis Performance OS",
  description: "Local sports-science operating system: squad command, monitoring, testing, research and evidence-linked reports.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
