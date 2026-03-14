/**
 * Auth Service Types
 */

export enum UserRole {
  ADMIN = "admin",
  USER = "user",
  GUEST = "guest",  // Different from user-service
}

export interface User {
  id: string;
  email: string;
  passwordHash: string;
  role: UserRole;
  createdAt: Date;
}

export interface AuthToken {
  token: string;
  expiresIn: number;
  refreshToken: string;
}

export const API_VERSION = "v1";
export const MAX_CONNECTIONS = 100;
