import type { Metadata } from "next";
import { DM_Sans, DM_Mono } from "next/font/google";
import { AppProvider } from "@/lib/studentStore";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

const dmMono = DM_Mono({
  variable: "--font-dm-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "MathsClub Practice · VIT Chennai",
  description:
    "Topic-wise maths practice from tutorial sheets and PYQs, with step-by-step solutions you can trust.",
  icons: { icon: "/logo.png" },
};

export default function StudentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className={`${dmSans.variable} ${dmMono.variable} student-portal relative min-h-screen bg-bg text-ink antialiased`}
      style={{ fontFamily: "var(--font-dm-sans), var(--font-sans), sans-serif" }}
    >
      <AppProvider>
        {children}
      </AppProvider>
    </div>
  );
}
