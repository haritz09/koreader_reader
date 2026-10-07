import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KOReader Reader",
  description: "Knowledge graph para ebooks",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es">
      <body className="antialiased">{children}</body>
    </html>
  );
}
