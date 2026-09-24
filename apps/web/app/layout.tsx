import type { Metadata } from "next";
import "reactflow/dist/style.css";

export const metadata: Metadata = {
  title: "DynamisScience · Scientific computation layer",
  description: "Local deterministic scientific computing and evidence workspace for human performance.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
