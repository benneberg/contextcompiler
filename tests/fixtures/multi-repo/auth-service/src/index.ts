/**
 * Auth Service - Authentication and Authorization
 */
import express, { Request, Response } from "express";
import { PrismaClient } from "@prisma/client";
import jwt from "jsonwebtoken";
import bcrypt from "bcrypt";

const app = express();
const prisma = new PrismaClient();

app.use(express.json());

export interface User {
  id: string;
  email: string;
  role: "admin" | "user" | "guest";
}

export interface AuthToken {
  token: string;
  expiresIn: number;
  refreshToken: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

/**
 * Login endpoint
 */
app.post("/api/auth/login", async (req: Request<{}, {}, LoginRequest>, res: Response) => {
  const { email, password } = req.body;
  
  const user = await prisma.user.findUnique({ where: { email } });
  
  if (!user || !await bcrypt.compare(password, user.passwordHash)) {
    return res.status(401).json({ error: "Invalid credentials" });
  }
  
  const token = jwt.sign({ userId: user.id, role: user.role }, process.env.JWT_SECRET!);
  
  res.json({ token, expiresIn: 3600 });
});

/**
 * Validate token endpoint - called by other services
 */
app.get("/api/auth/validate", async (req: Request, res: Response) => {
  const token = req.headers.authorization?.replace("Bearer ", "");
  
  if (!token) {
    return res.status(401).json({ valid: false });
  }
  
  try {
    const decoded = jwt.verify(token, process.env.JWT_SECRET!) as User;
    res.json({ valid: true, user: decoded });
  } catch {
    res.status(401).json({ valid: false });
  }
});

/**
 * Refresh token endpoint
 */
app.post("/api/auth/refresh", async (req: Request, res: Response) => {
  // Implementation
  res.json({ token: "new-token", expiresIn: 3600 });
});

/**
 * Logout endpoint
 */
app.post("/api/auth/logout", async (req: Request, res: Response) => {
  // Invalidate session
  res.json({ success: true });
});

export default app;
