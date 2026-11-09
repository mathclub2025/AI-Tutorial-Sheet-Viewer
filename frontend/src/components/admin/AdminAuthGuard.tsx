"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, messageOf, type Staff } from "@/lib/api";
const StaffContext = createContext<Staff | null>(null);
export const useStaff = () => useContext(StaffContext);
export function AdminAuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const parent = useStaff();
  const [user, setUser] = useState<Staff | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (parent) return;
    let active = true;
    const expired = () => { setUser(null); router.replace("/admin/login"); };
    window.addEventListener("mathclub-session-expired", expired);
    api<Staff>("auth/me").then(u => { if (active) setUser(u); }).catch(e => {
      if (!active) return;
      if (e instanceof ApiError && e.status === 401) expired(); else setError(messageOf(e));
    });
    return () => { active = false; window.removeEventListener("mathclub-session-expired", expired); };
  }, [parent, router]);
  if (parent) return <>{children}</>;
  if (!user) return <div className="p-6" role="status">{error || "Checking your session…"}{error && <button className="ml-4 underline" onClick={() => location.reload()}>Retry</button>}</div>;
  return <StaffContext.Provider value={user}>{children}</StaffContext.Provider>;
}
export default AdminAuthGuard;
