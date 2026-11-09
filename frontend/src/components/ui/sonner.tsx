"use client"

import { useTheme } from "next-themes"
import { Toaster as Sonner } from "sonner"

type ToasterProps = React.ComponentProps<typeof Sonner>

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme()

  return (
    <Sonner
      theme={props.theme || (theme as ToasterProps["theme"])}
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-[#121215] group-[.toaster]:text-zinc-100 group-[.toaster]:border group-[.toaster]:border-white/[0.08] group-[.toaster]:shadow-2xl group-[.toaster]:shadow-black/70 rounded-xl",
          description: "group-[.toast]:text-zinc-400",
          actionButton:
            "group-[.toast]:bg-[#F4F0EA] group-[.toast]:text-[#0A0A0C] group-[.toast]:font-semibold",
          cancelButton:
            "group-[.toast]:bg-zinc-800 group-[.toast]:text-zinc-300",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
