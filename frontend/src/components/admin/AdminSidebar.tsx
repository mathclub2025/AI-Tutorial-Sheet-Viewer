"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Upload,
  Layers,
  Menu,
  X,
  LogOut,
  Compass,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  isActive: boolean;
}

interface NavLinksProps {
  onItemClick?: () => void;
}

function NavLinks({ onItemClick }: NavLinksProps) {
  const pathname = usePathname();

  const navItems: NavItem[] = [
    {
      label: "Upload",
      href: "/admin/upload",
      icon: Upload,
      isActive: pathname === "/admin/upload" || pathname?.startsWith("/admin/upload"),
    },
    {
      label: "Review",
      href: "/admin/review",
      icon: Layers,
      isActive: pathname?.startsWith("/admin/review"),
    },
  ];

  return (
    <nav className="flex-1 px-3 py-4 space-y-1.5" aria-label="Admin Navigation">
      {navItems.map((item) => {
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onItemClick}
            className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all cursor-pointer ${
              item.isActive
                ? "bg-white/[0.08] text-white font-medium border border-white/[0.1] shadow-xs"
                : "text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.04] border border-transparent font-normal"
            }`}
          >
            <Icon
              className={`h-4 w-4 shrink-0 ${
                item.isActive ? "text-white" : "text-zinc-400"
              }`}
            />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function AdminSidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = React.useState<boolean>(false);

  // Close mobile drawer on route changes
  React.useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Handle Escape key to close mobile drawer
  React.useEffect(() => {
    if (!mobileOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mobileOpen]);

  // Prevent background scrolling when mobile drawer is open
  React.useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  const handleSignOut = () => {
    router.push("/");
  };

  return (
    <>
      {/* 1. Mobile Top Header */}
      <header className="md:hidden sticky top-0 z-30 flex items-center justify-between h-14 px-4 bg-[#0D0D10]/90 backdrop-blur-md text-white border-b border-white/[0.07] shadow-sm">
        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation menu"
            aria-expanded={mobileOpen}
            className="h-8 w-8 text-zinc-300 hover:text-white hover:bg-white/[0.04] rounded-md cursor-pointer"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-zinc-800/80 border border-white/[0.08] flex items-center justify-center text-zinc-200 shadow-2xs">
              <Compass className="h-4 w-4 text-zinc-200" />
            </div>
            <span className="font-semibold text-sm text-white">
              Maths Club
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={handleSignOut}
          className="p-1.5 text-zinc-400 hover:text-rose-400 hover:bg-rose-950/20 rounded-md transition-colors cursor-pointer"
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </header>

      {/* 2. Accessible Mobile Drawer with Backdrop */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-xs transition-opacity"
            onClick={() => setMobileOpen(false)}
            aria-hidden="true"
          />

          <div
            role="dialog"
            aria-modal="true"
            aria-label="Mobile Navigation Menu"
            className="fixed inset-y-0 left-0 w-60 max-w-[80vw] bg-[#0D0D10]/98 backdrop-blur-xl text-zinc-100 border-r border-white/[0.07] z-50 flex flex-col shadow-2xl"
          >
            <div className="p-4 border-b border-white/[0.07] flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-zinc-800/80 border border-white/[0.08] flex items-center justify-center text-zinc-200 shadow-2xs">
                  <Compass className="h-4 w-4 text-zinc-200" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-white leading-tight">
                    Maths Club
                  </h2>
                  <span className="text-[11px] text-zinc-400">Admin</span>
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setMobileOpen(false)}
                aria-label="Close navigation menu"
                className="h-8 w-8 text-zinc-400 hover:text-white hover:bg-white/[0.04] rounded-md cursor-pointer"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <React.Suspense
              fallback={
                <nav className="flex-1 p-3 space-y-1">
                  <div className="h-9 bg-zinc-800/50 rounded-md animate-pulse" />
                  <div className="h-9 bg-zinc-800/50 rounded-md animate-pulse" />
                </nav>
              }
            >
              <NavLinks onItemClick={() => setMobileOpen(false)} />
            </React.Suspense>

            <div className="p-4 border-t border-white/[0.07]">
              <button
                type="button"
                onClick={() => {
                  setMobileOpen(false);
                  handleSignOut();
                }}
                className="flex items-center gap-2 w-full px-3 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.04] active:scale-[0.98] rounded-md transition-all cursor-pointer"
                aria-label="Exit to Home"
              >
                <LogOut className="h-4 w-4" />
                <span>Exit to Home</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. Fixed Desktop Sidebar */}
      <aside className="hidden md:flex md:w-60 md:flex-col md:fixed md:inset-y-0 bg-[#0D0D10]/90 backdrop-blur-md text-zinc-100 border-r border-white/[0.07] z-30 shadow-sm">
        {/* Brand Header */}
        <div className="p-4 border-b border-white/[0.07] flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-800/80 border border-white/[0.08] flex items-center justify-center text-zinc-200 shrink-0 shadow-2xs">
            <Compass className="h-4 w-4 text-zinc-200" />
          </div>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-white tracking-tight leading-tight">
              Maths Club
            </h2>
            <span className="text-xs text-zinc-400 block mt-0.5">
              Admin
            </span>
          </div>
        </div>

        <React.Suspense
          fallback={
            <nav className="flex-1 p-3 space-y-1">
              <div className="h-9 bg-zinc-800/50 rounded-md animate-pulse" />
              <div className="h-9 bg-zinc-800/50 rounded-md animate-pulse" />
            </nav>
          }
        >
          <NavLinks />
        </React.Suspense>

        {/* Footer: Exit to Home */}
        <div className="p-4 border-t border-white/[0.07]">
          <button
            type="button"
            onClick={handleSignOut}
            className="flex items-center gap-2 w-full px-3 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-100 hover:bg-white/[0.04] active:scale-[0.98] rounded-md transition-all cursor-pointer"
            aria-label="Exit to Home"
          >
            <LogOut className="h-4 w-4" />
            <span>Exit to Home</span>
          </button>
        </div>
      </aside>
    </>
  );
}


export default AdminSidebar;

