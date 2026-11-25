import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "HorarioGen | Planificación académica",
  description: "Optimización genética de horarios académicos",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}

