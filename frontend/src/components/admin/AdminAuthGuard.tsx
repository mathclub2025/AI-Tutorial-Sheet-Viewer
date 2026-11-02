"use client";

import * as React from "react";

interface AdminAuthGuardProps {
  children: React.ReactNode;
}

export function AdminAuthGuard({ children }: AdminAuthGuardProps) {
  // Password requirement removed; ensure admin access is immediately granted
  React.useEffect(() => {
    try {
      localStorage.setItem("admin_authed", "true");
      document.cookie = "admin_authed=true; path=/; max-age=86400";
    } catch {}
  }, []);

  return <>{children}</>;
}

export default AdminAuthGuard;
