/**
 * API Gateway - Routing and aggregation layer
 */
import express, { Request, Response } from "express";
import { createProxyMiddleware } from "http-proxy-middleware";

const app = express();

const AUTH_SERVICE_URL = process.env.AUTH_SERVICE_URL || "http://auth-service:3001";
const USER_SERVICE_URL = process.env.USER_SERVICE_URL || "http://user-service:3002";

app.use(express.json());

export interface ServiceHealth {
  service: string;
  status: "healthy" | "unhealthy";
  latency: number;
}

/**
 * Health check endpoint
 */
app.get("/api/health", async (req: Request, res: Response) => {
  const services: ServiceHealth[] = [];
  
  // Check auth service
  try {
    const start = Date.now();
    await fetch(`${AUTH_SERVICE_URL}/health`);
    services.push({ service: "auth", status: "healthy", latency: Date.now() - start });
  } catch {
    services.push({ service: "auth", status: "unhealthy", latency: 0 });
  }
  
  // Check user service
  try {
    const start = Date.now();
    await fetch(`${USER_SERVICE_URL}/health`);
    services.push({ service: "user", status: "healthy", latency: Date.now() - start });
  } catch {
    services.push({ service: "user", status: "unhealthy", latency: 0 });
  }
  
  res.json({ gateway: "healthy", services });
});

/**
 * Proxy auth requests
 */
app.use("/api/auth", createProxyMiddleware({
  target: AUTH_SERVICE_URL,
  changeOrigin: true,
}));

/**
 * Proxy user requests
 */
app.use("/api/users", createProxyMiddleware({
  target: USER_SERVICE_URL,
  changeOrigin: true,
}));

/**
 * Aggregate user with auth status
 */
app.get("/api/me", async (req: Request, res: Response) => {
  const token = req.headers.authorization;
  
  // Validate with auth service
  const authResponse = await fetch(`${AUTH_SERVICE_URL}/api/auth/validate`, {
    headers: { Authorization: token || "" }
  });
  
  if (!authResponse.ok) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  
  const { user: authUser } = await authResponse.json();
  
  // Get full profile from user service
  const userResponse = await fetch(`${USER_SERVICE_URL}/api/users/${authUser.userId}`, {
    headers: { Authorization: token || "" }
  });
  
  const profile = await userResponse.json();
  
  res.json({ ...profile, role: authUser.role });
});

export default app;
