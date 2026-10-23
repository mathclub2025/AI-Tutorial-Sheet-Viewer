"use client";

import ChatView from "@/components/ChatView";
import NameDialog from "@/components/NameDialog";
import SearchModal from "@/components/SearchModal";
import SettingsModal from "@/components/SettingsModal";
import Sidebar from "@/components/Sidebar";
import { AppProvider, useApp } from "@/lib/store";

function Toast() {
  const { toast } = useApp();
  if (!toast) return null;
  return (
    <div role="status" aria-live="polite" className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 rounded-lg bg-ink px-4 py-2.5 text-sm text-surface">
      {toast}
    </div>
  );
}

function Shell() {
  return (
    <div className="flex h-dvh gap-0 overflow-hidden bg-bg lg:p-3 lg:pl-0">
      <Sidebar />
      <main className="flex min-w-0 flex-1 lg:ml-0">
        <ChatView />
      </main>
      <SettingsModal />
      <SearchModal />
      <NameDialog />
      <Toast />
    </div>
  );
}

export default function Page() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
