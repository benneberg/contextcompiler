/**
 * User Service - User Management
 */
import express, { Request, Response } from "express";
import { PrismaClient } from "@prisma/client";

const app = express();
const prisma = new PrismaClient();

app.use(express.json());

const AUTH_SERVICE_URL = process.env.AUTH_SERVICE_URL || "http://auth-service:3001";

export interface UserProfile {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  createdAt: Date;
}

export interface CreateUserRequest {
  email: string;
  password: string;
  name: string;
}

export interface UpdateUserRequest {
  name?: string;
  avatar?: string;
}

/**
 * Middleware to validate auth token
 */
async function authMiddleware(req: Request, res: Response, next: Function) {
  const token = req.headers.authorization;
  
  // Call auth service to validate
  const response = await fetch(`${AUTH_SERVICE_URL}/api/auth/validate`, {
    headers: { Authorization: token || "" }
  });
  
  if (!response.ok) {
    return res.status(401).json({ error: "Unauthorized" });
  }
  
  const { user } = await response.json();
  (req as any).user = user;
  next();
}

/**
 * Get user profile
 */
app.get("/api/users/:userId", authMiddleware, async (req: Request, res: Response) => {
  const { userId } = req.params;
  
  const user = await prisma.user.findUnique({
    where: { id: userId },
    select: { id: true, email: true, name: true, avatar: true, createdAt: true }
  });
  
  if (!user) {
    return res.status(404).json({ error: "User not found" });
  }
  
  res.json(user);
});

/**
 * Create user
 */
app.post("/api/users", async (req: Request<{}, {}, CreateUserRequest>, res: Response) => {
  const { email, password, name } = req.body;
  
  const user = await prisma.user.create({
    data: { email, passwordHash: password, name }
  });
  
  // Notify other services
  await fetch("http://notification-service:3003/api/notifications/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      type: "welcome",
      userId: user.id,
      email: user.email
    })
  });
  
  res.status(201).json(user);
});

/**
 * Update user profile
 */
app.patch("/api/users/:userId", authMiddleware, async (req: Request, res: Response) => {
  const { userId } = req.params;
  const updates = req.body as UpdateUserRequest;
  
  const user = await prisma.user.update({
    where: { id: userId },
    data: updates
  });
  
  res.json(user);
});

/**
 * Delete user
 */
app.delete("/api/users/:userId", authMiddleware, async (req: Request, res: Response) => {
  const { userId } = req.params;
  
  await prisma.user.delete({ where: { id: userId } });
  
  res.status(204).send();
});

/**
 * List all users (admin only)
 */
app.get("/api/users", authMiddleware, async (req: Request, res: Response) => {
  const users = await prisma.user.findMany({
    select: { id: true, email: true, name: true, createdAt: true }
  });
  
  res.json(users);
});

export default app;
