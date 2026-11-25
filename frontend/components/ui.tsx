import { cva } from "class-variance-authority";
import { clsx, type ClassValue } from "clsx";
import type { ComponentProps } from "react";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const buttonVariants = cva(
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition-colors disabled:opacity-50",
  { variants: { variant: {
    primary: "bg-indigo-700 text-white hover:bg-indigo-800",
    outline: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
  } }, defaultVariants: { variant: "primary" } },
);

export function Button({ className, variant, ...props }: ComponentProps<"button"> & { variant?: "primary" | "outline" }) {
  return <button className={cn(buttonVariants({ variant }), className)} {...props} />;
}

export function Card({ className, ...props }: ComponentProps<"section">) {
  return <section className={cn("rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:p-6", className)} {...props} />;
}


