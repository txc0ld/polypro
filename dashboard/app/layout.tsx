import type { Metadata } from "next";
import { TopNav } from "@/components/TopNav";
import { currentIncidentState } from "@/lib/log";
import "./globals.css";

export const metadata: Metadata = {
  title: "POLYFLOW Dashboard",
  description: "Read-only operational view of the POLYFLOW runtime",
};

export const dynamic = "force-dynamic";

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const state = await currentIncidentState();
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-ink">
        <TopNav state={state} />
        <main className="mx-auto max-w-7xl p-6">{children}</main>
      </body>
    </html>
  );
}
