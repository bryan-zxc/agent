import * as React from "react"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        "file:text-foreground placeholder:text-gray-500 dark:placeholder:text-gray-400 flex h-9 w-full rounded-md bg-gray-100 dark:bg-gray-800 px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:bg-gray-50 dark:focus-visible:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
}

export { Input }