import "../styles/globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Omega Mission Control v18.0",
  description: "Standalone Next.js dashboard for Omega Daemon v18.0 artifacts",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">{children}</div>
      </body>
    </html>
  );
}
