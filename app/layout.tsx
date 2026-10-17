import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "冷杉更新研究室 · 样方与环境分析",
  description: "从原始样方观测到可复现的种群更新与环境关联分析。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        {children}
      </body>
    </html>
  );
}
