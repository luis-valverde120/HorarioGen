const backend = process.env.HORARIOGEN_BACKEND ?? "http://127.0.0.1:8000";
export default {
  async rewrites() {
    return [{ source: "/api/:path*", destination: backend + "/api/:path*" }];
  },
};

