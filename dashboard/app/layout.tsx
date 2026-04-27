import type { Metadata } from "next";
import { AutoRefresh } from "@/components/AutoRefresh";
import { TopBar } from "@/components/TopBar";
import { loadRuntimeStatus } from "@/lib/runtime";
import "./globals.css";

export const metadata: Metadata = {
  title: "POLYFLOW",
  description: "Operational dashboard for the POLYFLOW autonomous trading runtime",
};

export const dynamic = "force-dynamic";
export const revalidate = 0;

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const status = await loadRuntimeStatus();
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-ink antialiased">
        <AutoRefresh intervalMs={10_000} />
        <TopBar status={status} />
        <main className="mx-auto max-w-[1440px] px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
