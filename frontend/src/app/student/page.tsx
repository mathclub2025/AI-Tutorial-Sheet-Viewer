"use client";

import ChatView from "@/components/student/ChatView";
import NameDialog from "@/components/student/NameDialog";
import SearchModal from "@/components/student/SearchModal";
import SettingsModal from "@/components/student/SettingsModal";
import Sidebar from "@/components/student/Sidebar";
import { useApp } from "@/lib/studentStore";

function Toast() {
  const { toast } = useApp();
  if (!toast) return null;
  return (
    <div role="status" aria-live="polite" className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 rounded-lg bg-ink px-4 py-2.5 text-sm text-surface shadow-lg">
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

export default function StudentPage() {
  return <Shell />;
}
