import type { Metadata } from "next";
import { Source_Serif_4, Outfit, JetBrains_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import { MathCanvasBackground } from "@/components/ui/MathCanvasBackground";
import "./globals.css";

const sourceSerif = Source_Serif_4({
  variable: "--font-serif",
  subsets: ["latin"],
  weight: ["600", "700"],
  display: "swap",
});

const outfit = Outfit({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Maths Club Admin | Question Review & Ingestion Desk",
  description: "Maths Club Question Review, Ingestion Pipeline and Sheet Management",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${sourceSerif.variable} ${outfit.variable} ${jetbrainsMono.variable} h-full antialiased dark`}
      style={{ colorScheme: "dark" }}
      data-theme="dark"
    >
      <body className="min-h-full flex flex-col relative bg-transparent text-zinc-100 selection:bg-zinc-800 selection:text-zinc-100">
        <MathCanvasBackground />
        {children}
        <Toaster
          theme="dark"
          toastOptions={{
            style: {
              background: "#121215",
              border: "1px solid rgba(255, 255, 255, 0.1)",
              color: "#F4F0EA",
            },
          }}
        />
      </body>
    </html>
  );
}

