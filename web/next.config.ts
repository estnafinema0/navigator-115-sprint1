import type { NextConfig } from "next";

// В разработке запросы /api проксируются на FastAPI (порт 8115).
// Сборка: статический экспорт в out/, его раздаёт тот же FastAPI (docker compose: api, db, ollama).
const isDev = process.env.NODE_ENV === "development";

const config: NextConfig = {
  trailingSlash: true,
  images: { unoptimized: true },
  ...(isDev
    ? {
        async rewrites() {
          return [{ source: "/api/:path*", destination: "http://127.0.0.1:8115/api/:path*" }];
        },
      }
    : { output: "export" as const }),
};

export default config;
