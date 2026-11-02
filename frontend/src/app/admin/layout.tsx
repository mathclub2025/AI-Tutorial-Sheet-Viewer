"use client";

import * as React from "react";
import { usePathname } from "next/navigation";
import { AdminSidebar } from "@/components/admin/AdminSidebar";
import { AdminHeader } from "@/components/admin/AdminHeader";

function AdminLayoutInner({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/admin/login" || pathname?.startsWith("/admin/login");

  // Ensure admin section maintains its dark chalkboard theme
  React.useEffect(() => {
    document.documentElement.classList.add("dark");
  }, []);

  // Keep /admin/login completely free from the dashboard sidebar and navigation
  if (isLoginPage) {
    return <div className="relative min-h-screen bg-transparent">{children}</div>;
  }

  return (
    <div className="relative min-h-screen bg-transparent flex flex-col md:flex-row text-zinc-100 selection:bg-zinc-800 selection:text-zinc-100">
      <AdminSidebar />
      <div className="flex-1 md:pl-60 min-w-0 flex flex-col">
        <AdminHeader />
        <div className="flex-1 flex flex-col">
          {children}
        </div>
      </div>
    </div>
  );
}

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <React.Suspense
      fallback={
        <div className="relative min-h-screen bg-transparent flex flex-col md:flex-row text-zinc-100">
          <div className="flex-1 md:pl-60 min-w-0 flex flex-col">
            {children}
          </div>
        </div>
      }
    >
      <AdminLayoutInner>{children}</AdminLayoutInner>
    </React.Suspense>
  );
}

